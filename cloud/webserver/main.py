import os
import urllib.parse
from asyncio import get_running_loop
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, AsyncIterator, Callable, Coroutine, Optional, Union

from google.cloud import bigquery
from google.cloud.bigquery.table import RowIterator
from quart import Markup, Quart, abort, stream_template, url_for
from werkzeug.routing import BaseConverter, ValidationError

client = bigquery.Client()

app = Quart(__name__)


class DateConverter(BaseConverter):
    regex = r"\d\d\d\d-\d\d-\d\d"

    def to_python(self, value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as e:
            raise ValidationError() from e

    def to_url(self, value: date) -> str:
        return value.isoformat()


app.url_map.converters["isodate"] = DateConverter


def wrap_job(job: bigquery.QueryJob, *result_args, **result_kwargs):
    wrapped = get_running_loop().create_future()

    def on_ready(_):
        if wrapped.done():
            return
        try:
            result = job.result(*result_args, **result_kwargs)
        except Exception as e:
            wrapped.set_exception(e)
            return
        wrapped.set_result(result)

    job.add_done_callback(on_ready)
    return wrapped


@app.template_filter()
def without_origin(url) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.query:
        return f"{parsed.path}?{parsed.query}"
    return parsed.path


@app.template_filter()  # type: ignore
def web_archive(url: str, latest_date: date) -> str:
    end_of_latest_date = latest_date + timedelta(days=1)
    return f"https://web.archive.org/web/{end_of_latest_date:%Y%m%d%H%M%S}/{url}"


@app.template_filter()
def render_diff(diff: Union[str, Markup]) -> Markup:
    diff = Markup.escape(diff)

    def color(line: Markup) -> Markup:
        if line.startswith("+"):
            return Markup(f"<ins>{line}</ins>")
        if line.startswith("-"):
            return Markup(f"<del>{line}</del>")
        return line

    return Markup("<br>\n").join(color(line) for line in diff.splitlines())


@app.route("/")
@app.route("/<isodate:crawl_date>/")
async def root_page(crawl_date: Optional[date] = None) -> AsyncIterator[str]:
    crawl_dates = await find_crawl_dates(crawl_date)
    current_crawl = crawl_dates.current_crawl
    prev_crawl = crawl_dates.prev_crawl

    new_pages = get_pages_with_change(
        current_crawl=current_crawl, change="ADD", max_results=10
    )

    removed_pages = get_pages_with_change(
        current_crawl=current_crawl, change="DEL", max_results=10
    )

    modified_pages = get_pages_with_change(
        current_crawl=current_crawl, change="CHANGE", max_results=10
    )

    return await stream_template(
        "index.html.j2",
        crawl_date=current_crawl,
        prev_crawl_date=prev_crawl,
        prev_crawl_link=url_for("root_page", crawl_date=prev_crawl),
        new_pages=new_pages,
        more_new_pages=url_for(
            "page_change_detail_page", crawl_date=current_crawl, change="new"
        ),
        removed_pages=removed_pages,
        more_removed_pages=url_for(
            "page_change_detail_page", crawl_date=current_crawl, change="removed"
        ),
        modified_pages=modified_pages,
        more_modified_pages=url_for(
            "page_change_detail_page", crawl_date=current_crawl, change="modified"
        ),
    )


@app.route("/<isodate:crawl_date>/<any(new,removed,modified):change>")
async def page_change_detail_page(crawl_date: date, change: str):
    db_change, title, old_archive, new_archive = {
        "new": ("ADD", f"New pages in the {crawl_date} crawl", None, "Archive"),
        "removed": (
            "DEL",
            f"Removed pages in the {crawl_date} crawl",
            "Old Archive",
            None,
        ),
        "modified": (
            "CHANGE",
            f"Modified pages in the {crawl_date} crawl",
            "Old",
            "New Archive",
        ),
    }[change]

    crawl_dates: CrawlDates = await find_crawl_dates(crawl_date)

    changed_pages = get_pages_with_change(
        current_crawl=crawl_dates.current_crawl, change=db_change
    )

    return await stream_template(
        "page_change_detail.html.j2",
        title=title,
        crawl_dates=crawl_dates,
        pages=changed_pages,
        old_archive=old_archive,
        new_archive=new_archive,
    )


@dataclass(kw_only=True)
class CrawlDates:
    current_crawl: date
    prev_crawl: date


async def find_crawl_dates(current_crawl: Optional[date] = None) -> CrawlDates:
    results = list(
        await wrap_job(
            client.query(
                """
                SELECT DISTINCT crawl
                FROM `pbot-site-crawler.crawl.changed-pages`
                WHERE @current_crawl is NULL OR crawl <= @current_crawl
                ORDER BY crawl DESC
                LIMIT 2""",
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter(
                            "current_crawl", "DATE", current_crawl
                        ),
                    ]
                ),
            )
        )
    )
    if len(results) != 2:
        abort(404)
    crawl_dates = CrawlDates(
        current_crawl=results[0]["crawl"], prev_crawl=results[1]["crawl"]
    )
    if current_crawl is not None and crawl_dates.current_crawl != current_crawl:
        abort(404)
    return crawl_dates


@dataclass
class PagesResult:
    pages: RowIterator
    more_available: bool
    total_rows: int


def get_pages_with_change(
    *,
    current_crawl: date,
    change: str,
    max_results: Optional[int] = None,
) -> Callable[[], Coroutine[Any, Any, PagesResult]]:
    query = client.query(
        """
        SELECT page, diff
        FROM `pbot-site-crawler.crawl.changed-pages`
        WHERE crawl = @current_crawl AND change = @change
        ORDER BY page
        """,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("current_crawl", "DATE", current_crawl),
                bigquery.ScalarQueryParameter("change", "STRING", change),
            ]
        ),
    )

    # We really only need this because Jinja doesn't await simple values, just
    # function call results.
    async def result():
        results = await wrap_job(query, max_results=max_results)
        more_available = False
        if max_results is not None and max_results < results.total_rows:
            more_available = True
        return PagesResult(
            pages=results, more_available=more_available, total_rows=results.total_rows
        )

    return result


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=int(os.environ.get("PORT", 8080)))
