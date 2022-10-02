import os
from asyncio import get_running_loop
from datetime import date

from google.cloud import bigquery
from quart import Quart, stream_template

client = bigquery.Client()

app = Quart(__name__)


def wrap_future(job_or_future):
    wrapped = get_running_loop().create_future()

    def on_ready(_):
        if wrapped.done():
            return
        try:
            result = job_or_future.result()
        except Exception as e:
            wrapped.set_exception(e)
            return
        wrapped.set_result(result)

    job_or_future.add_done_callback(on_ready)
    return wrapped


@app.template_filter()
def without_origin(url) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.query:
        return f"{parsed.path}?{parsed.query}"
    return parsed.path


@app.template_filter()
def web_archive(url, latest_date:str) -> str:
    latest = date.fromisoformat(latest_date)
    latest += timedelta(days=1)
    return f"https://web.archive.org/web/{latest:YYYYMMDD}/{url}"


@app.route("/")
async def hello_world():
    results = list(
        await wrap_future(
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

    new_pages = client.query(
        """
        SELECT page, change
        FROM `pbot-site-crawler.crawl.changed-pages`
        WHERE crawl = @current_crawl
        ORDER BY page
        """,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("current_crawl", "DATE", current_crawl),
            ]
        ),
    )

    return await stream_template(
        "index.html.j2",
        crawl_date=current_crawl,
        prev_crawl_date=prev_crawl,
        new_pages=[],
        more_new_pages=False,
        removed_pages=[],
        more_removed_pages=False,
        modified_pages=[],
        more_modified_pages=False,
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=int(os.environ.get("PORT", 8080)))
