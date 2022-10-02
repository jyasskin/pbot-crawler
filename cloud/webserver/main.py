import os
import urllib.parse
from asyncio import get_running_loop
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from google.cloud import bigquery
from google.cloud.bigquery.table import RowIterator
from quart import Quart, stream_template

client = bigquery.Client()

app = Quart(__name__)


def wrap_job(job):
    wrapped = get_running_loop().create_future()

    def on_ready(_):
        if wrapped.done():
            return
        try:
            result = job.result()
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


@app.template_filter()
def web_archive(url, latest_date: str) -> str:
    end_of_latest_date = latest_date+timedelta(days=1)
    return f"https://web.archive.org/web/{end_of_latest_date:%Y%m%d%H%M%S}/{url}"


@app.route("/")
async def hello_world():
    results = list(
        await wrap_job(
            client.query(
                """
                SELECT DISTINCT crawl
                FROM `pbot-site-crawler.crawl.changed-pages`
                ORDER BY crawl DESC
                LIMIT 2"""
            )
        )
    )
    current_crawl = results[0]["crawl"]
    prev_crawl = results[1]["crawl"]

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
        new_pages=new_pages,
        removed_pages=removed_pages,
        modified_pages=modified_pages,
    )


@dataclass
class PagesResult:
    pages: RowIterator
    more_available: bool


def get_pages_with_change(
    *,
    current_crawl: str,
    change: str,
    max_results: Optional[int] = None,
    page_size: Optional[int] = None,
) -> PagesResult:
    query = client.query(
        """
        SELECT page
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
        await wrap_job(query)
        results = query.result(max_results=max_results, page_size=page_size)
        more_available = False
        if max_results is not None and max_results < results.num_results:
            more_available = True
        if page_size is not None and page_size < results.num_results:
            more_available = True
        return PagesResult(pages=results, more_available=more_available)

    return result


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=int(os.environ.get("PORT", 8080)))
