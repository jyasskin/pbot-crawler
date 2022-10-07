import base64
import json
import logging
import time
import traceback
from concurrent import futures
from datetime import date, datetime, timedelta, timezone
from typing import Tuple
from urllib.robotparser import RobotFileParser

import functions_framework
import google.auth.exceptions
import requests
from google.cloud import error_reporting, firestore
from google.cloud import logging as cloud_logging
from google.cloud import pubsub_v1

import config
from cache import Cache, CacheState, FreshResponse, PresenceChange

SESSION = requests.Session()
USER_AGENT = "PBOT Crawler"
SESSION.headers.update({"user-agent": USER_AGENT})
next_fetch = datetime.now(timezone.utc)

crawled_urls = set()

robots = RobotFileParser(config.URL_ORIGIN + "robots.txt")
robots.read()
crawl_delay = timedelta(seconds=float(robots.crawl_delay(USER_AGENT) or 1))

db = firestore.Client()
cache = Cache(db)

_error_reporting_client = None
try:
    _error_reporting_client = error_reporting.Client()
    logging_client = cloud_logging.Client()
    logging_client.setup_logging()
except google.auth.exceptions.DefaultCredentialsError:
    logging.basicConfig(level=logging.DEBUG)


def report_exception():
    if _error_reporting_client is not None:
        _error_reporting_client.report_exception()
    else:
        logging.exception("Exception")


batch_settings = pubsub_v1.types.BatchSettings(max_messages=1000)
publisher = pubsub_v1.PublisherClient(batch_settings)
crawl_topic_path = publisher.topic_path(config.CLOUD_PROJECT, "crawl")
changed_pages_topic_path = publisher.topic_path(config.CLOUD_PROJECT, "changed-pages")


@functions_framework.http
def start_crawl(request):
    """Start today's crawl."""
    try:
        if request.method != "POST":
            return "Method not allowed\n", 405
        do_start_crawl()
        return "Done\n", 200
    except Exception:
        report_exception()
        return traceback.format_exc(), 500


def do_start_crawl():
    current_crawl, prev_crawl = get_crawl({})
    logging.info(
        "Starting crawl %s; queuing existing pages from %s crawl.",
        current_crawl,
        prev_crawl,
    )
    sync_publisher = SynchronousPublisher(publisher)
    link_publisher = OutboundLinkPublisher(sync_publisher, prev_crawl, current_crawl)
    # Make sure the crawl is never empty.
    link_publisher.publish("https://www.portland.gov/transportation")
    # Check all known pages.
    for existing_page in (
        db.collection(f"crawl-{prev_crawl}")
        .where("status_code", "<", 400)
        .select(["url"])
        .stream()
    ):
        link_publisher.publish(existing_page.get("url"))
    logging.info("Waiting to publish %d existing pages.", len(sync_publisher))
    sync_publisher.wait()


@functions_framework.cloud_event
def crawl_url(cloud_event):
    """Crawl one URL, received from a PubSub queue."""
    try:
        do_crawl_url(cloud_event)
    except Exception:
        report_exception()


def do_crawl_url(cloud_event):
    try:
        data = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))
    except Exception as e:
        raise ValueError(
            f"Invalid input: {cloud_event.data!r}", cloud_event.data
        ) from e
    logging.info("Invoked with %r", data)
    current_crawl, prev_crawl = get_crawl(data)
    url = data["url"]
    assert ok_to_crawl(url), url
    if url in crawled_urls:
        return

    sync_publisher = SynchronousPublisher(publisher)
    link_publisher = OutboundLinkPublisher(sync_publisher, prev_crawl, current_crawl)
    cached_response = cache.response_for(
        url=url, prev_crawl=prev_crawl, curr_crawl=current_crawl
    )
    if cached_response.state == CacheState.FRESH:
        crawled_urls.add(url)
        return

    wait_for_next_fetch()
    fresh_response = cached_response.fetch(SESSION)

    publish_page_change(fresh_response, sync_publisher, current_crawl)

    if fresh_response.status_code // 100 == 3:
        location = fresh_response.headers["location"]
        logging.info("Redirected to %r", fresh_response.headers["location"])
        link_publisher.publish(location)

    if fresh_response.links:
        logging.info("Queuing crawls of %r", fresh_response.links)
        for link in fresh_response.links:
            link_publisher.publish(link)
    sync_publisher.wait()
    # After we've published all the links, we can mark the URL as crawled.
    crawled_urls.add(url)
    fresh_response.write_to_firestore(db, current_crawl)


def get_crawl(data: dict) -> Tuple[str, str]:
    """Get the current and previous crawls from the PubSub message, or select
    them if they're not present."""
    current_crawl = data.get("crawl", "")
    if current_crawl == "":
        current_crawl = datetime.now(timezone.utc).date().isoformat()
    prev_crawl = data.get("prev_crawl", "")
    if prev_crawl == "":
        for collection in db.collections():
            if not collection.id.startswith("crawl-"):
                continue
            collection_date = collection.id[6:]
            if collection_date < current_crawl and (
                prev_crawl is None or collection_date > prev_crawl
            ):
                prev_crawl = collection_date

    return current_crawl, prev_crawl


def ok_to_crawl(url: str):
    return url.startswith(
        "https://www.portland.gov/transportation"
    ) and robots.can_fetch(USER_AGENT, url)


def wait_for_next_fetch():
    """Wait until the next fetch is allowed."""
    global next_fetch
    now = datetime.now(timezone.utc)
    if now < next_fetch:
        time.sleep((next_fetch - now).total_seconds())
    next_fetch = datetime.now(timezone.utc) + crawl_delay


class SynchronousPublisher:
    def __init__(self, publisher: pubsub_v1.PublisherClient):
        self.publisher = publisher
        self.publish_futures = []

    def publish(self, topic_path: str, message: bytes):
        future = self.publisher.publish(topic_path, message)
        self.publish_futures.append(future)
        return future

    def __len__(self):
        return len(self.publish_futures)

    def wait(self):
        """Waits for all publications to finish."""
        for future in futures.as_completed(self.publish_futures, timeout=10):
            # Raise any exceptions.
            future.result()
        self.publish_futures = []


class OutboundLinkPublisher:
    """Publishes crawled outbound links to the PubSub queue."""

    def __init__(self, publisher, prev_crawl: str, current_crawl: str):
        self.publisher = publisher
        self.prev_crawl = prev_crawl
        self.current_crawl = current_crawl

    def publish(self, url: str) -> None:
        if ok_to_crawl(url) and url not in crawled_urls:
            data = json.dumps(
                {"url": url, "crawl": self.current_crawl, "prev_crawl": self.prev_crawl}
            )
            logging.info("Publishing %s to %r", data, crawl_topic_path)
            self.publisher.publish(crawl_topic_path, data.encode("utf-8"))


def publish_page_change(
    response: FreshResponse, publisher: SynchronousPublisher, current_crawl: str
):
    change_description = {
        "crawl": current_crawl,
        "page": response.url,
    }
    if response.change == PresenceChange.SAME:
        # Don't record pages that haven't changed.
        return
    if response.change == PresenceChange.NEW:
        change_description["change"] = "ADD"
    elif response.change == PresenceChange.REMOVED:
        change_description["change"] = "DEL"
    else:
        assert response.change == PresenceChange.CHANGED, response.change
        change_description["change"] = "CHANGE"
    logging.info("Publishing changed page: %s", json.dumps(change_description))
    publisher.publish(changed_pages_topic_path, json.dumps(change_description).encode())
    # And ask the Web Archive to save a copy of the page.
    archive_result = SESSION.get(
        "https://web.archive.org/save/" + response.url,
        # data={"url": response.url, "capture_all": "on"},
        allow_redirects=False,
    )
    if archive_result.status_code >= 400:
        logging.error(
            f"Failed to archive {response.url!r}: {archive_result.status_code}, {archive_result.headers!r}"
        )
    elif "location" in archive_result.headers:
        logging.info(f"Archived to {archive_result.headers['location']}")
    else:
        logging.warning(
            f"Something odd with archiving {response.url!r}: {archive_result.status_code}, {archive_result.headers!r}"
        )
