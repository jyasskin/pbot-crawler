import json
import logging
import os
import re
import urllib.parse
from asyncio import get_running_loop
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, AsyncIterator, Callable, Coroutine, Optional, Union

from google.auth.transport import requests
from google.cloud import bigquery
from google.cloud.bigquery.table import Row, RowIterator
from google.oauth2.id_token import verify_token
from python_http_client.exceptions import HTTPError
from quart import (Markup, Quart, abort, render_template, request,
                   stream_template, url_for)
from quart.utils import run_sync
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.routing import BaseConverter, ValidationError

from sendgrid_util import SendGrid

logging.basicConfig(level=logging.INFO)

# Default to a test list.
SENDGRID_PBOT_LIST_ID = os.environ.get(
    "SENDGRID_PBOT_LIST_ID", "d3d77092-4188-4d3d-82ce-6aa8a09daf93"
)

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


@app.template_filter()
def web_archive(url: str, latest_date: date | None = None) -> str:
    if latest_date is None:
        date_param = "*"
    else:
        date_param = (latest_date + timedelta(days=1)).strftime("%Y%m%d%H%M%S")
    return f"https://web.archive.org/web/{date_param}/{url}"


@app.template_filter()
def render_diff(diff: Union[str, Markup]) -> Markup:
    diff = Markup.escape(diff)

    def color(line: Markup) -> Markup:
        if line.startswith("+") and not line.startswith("+++"):
            return Markup(f"<code>+</code><ins>{line[1:]}</ins>")
        if line.startswith("-") and not line.startswith("---"):
            return Markup(f"<code>-</code><del>{line[1:]}</del>")
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
    crawl_link = f"<a href='{url_for('root_page', crawl_date=crawl_date)}'>{crawl_date} crawl</a>"
    db_change, title, archive_date = {
        "new": ("ADD", f"New pages in the {crawl_link}", crawl_date),
        "removed": (
            "DEL",
            f"Removed pages in the {crawl_link}",
            None,
        ),
        "modified": (
            "CHANGE",
            f"Modified pages in the {crawl_link}",
            None,
        ),
    }[change]

    crawl_dates: CrawlDates = await find_crawl_dates(crawl_date)

    changed_pages = get_pages_with_change(
        current_crawl=crawl_dates.current_crawl, change=db_change
    )

    return await stream_template(
        "page_change_detail.html.j2",
        title=Markup(title),
        crawl_dates=crawl_dates,
        pages=changed_pages,
        archive_date=archive_date,
    )


@app.route("/send_mail", methods=["GET", "POST"])
async def send_mail():
    crawl_dates = await find_crawl_dates()
    current_crawl = crawl_dates.current_crawl
    prev_crawl = crawl_dates.prev_crawl

    new_pages = get_pages_with_change(current_crawl=current_crawl, change="ADD")

    removed_pages = get_pages_with_change(current_crawl=current_crawl, change="DEL")

    modified_pages = get_pages_with_change(current_crawl=current_crawl, change="CHANGE")

    def interesting(row: Row) -> bool:
        return (
            re.search(
                "|".join(
                    [
                        r"^https://www.portland.gov/transportation/news",
                        "/documents",
                        "/meetings",
                        "/past",
                        "/services",
                    ]
                )
                + r"(?:\?|$)",
                row.page,
            )
            is None
        )

    data = {
        "curr_crawl_date": current_crawl,
        "curr_crawl_link": f"https://{request.host}{url_for('root_page', crawl_date=current_crawl)}",
        "prev_crawl_date": prev_crawl,
        "new": [page for page in (await new_pages()).pages if interesting(page)],
        "removed": [
            page for page in (await removed_pages()).pages if interesting(page)
        ],
        "modified_link": f"https://{request.host}{url_for('page_change_detail_page', crawl_date=current_crawl, change='modified')}",
        "modified": [
            page for page in (await modified_pages()).pages if interesting(page)
        ],
    }

    if request.method == "POST":
        sendgrid_api_key = os.environ.get("SENDGRID_API_KEY", None)
        if sendgrid_api_key is None:
            await check_authorization(
                auth_header=request.headers.get("Authorization"),
                audience=f"https://{request.host}{url_for('send_mail')}",
                email="email-sender@pbot-site-crawler.iam.gserviceaccount.com",
            )
            with open("/etc/secrets/sendgrid/api_key") as f:
                sendgrid_api_key = f.read().strip()

        assert sendgrid_api_key is not None
        sg = SendGrid(sendgrid_api_key)

        subject = f"PBOT website changes from {prev_crawl} to {current_crawl}"

        try:
            unsubscribed = sg.remove_unsubscribed()
            to = sg.get_pbot_subscribers(
                list_id=SENDGRID_PBOT_LIST_ID, exclude=frozenset(unsubscribed)
            )
            if len(to) == 0:
                logging.error("Nobody to send email to.")
                return "Nobody to send email to.\n", 400

            response = sg.send_mail(
                to=to,
                sender_email="pbot-crawl-reports@yasskin.info",
                sender_name="Jeffrey Yasskin",
                subject=subject,
                html_content=await render_template("weekly_email.html.j2", **data),
                plain_content=await render_template("weekly_email.txt.j2", **data),
            )
        except HTTPError as e:
            messages = [error["message"] for error in e.to_dict["errors"]]
            for message in messages:
                app.logger.error(message)
            raise

        return f"Sent to {len(to)} people, with a result of:\n<xmp>{json.dumps(response, indent=2)}</xmp>\n"
    else:
        return await render_template("weekly_email.html.j2", **data)


async def check_authorization(
    *, auth_header: str | None, audience: str, email: str
) -> None:
    """
    Params:
        auth_header: request.headers.get("Authorization").
        audience: The expected JWT audience.
        email: The email identity expected to have signed the JWT.
    """
    www_auth = WWWAuthenticate("Bearer")
    if not auth_header:
        abort(401, www_authenticate=www_auth)

    # split the auth type and value from the header.
    auth_type, creds = auth_header.split(" ", 1)

    if auth_type.lower() != "bearer":
        abort(401, www_authenticate=www_auth)

    def verify(*, verify=True):
        return verify_token(
            creds,
            audience=audience,
            request=requests.Request(),
        )

    try:
        claims = await run_sync(verify)()
    except ValueError as e:
        app.logger.warning("Invalid JWT: %s, %r", e, creds)
        www_auth["error"] = "invalid_token"
        www_auth["error_description"] = str(e)
        abort(401, www_authenticate=www_auth)

    if claims["email"] != email:
        www_auth["error"] = "insufficient_scope"
        www_auth[
            "error_description"
        ] = f"{claims['email']} is not allowed to send emails"
        abort(401, www_authenticate=www_auth)


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
