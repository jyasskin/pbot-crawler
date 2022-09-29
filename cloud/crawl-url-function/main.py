import json
import logging
import os
import time
from concurrent import futures
from datetime import datetime, timedelta, timezone
from typing import Tuple
from urllib.robotparser import RobotFileParser

import functions_framework
import requests
from google.cloud import error_reporting, firestore, pubsub_v1

import config
from cache import Cache, CacheState

SESSION = requests.Session()
USER_AGENT = 'PBOT Crawler'
SESSION.headers.update({'user-agent': USER_AGENT})
next_fetch = datetime.now(timezone.utc)

crawled_urls = set()

robots = RobotFileParser(config.URL_ORIGIN + 'robots.txt')
robots.read()
crawl_delay = timedelta(seconds=robots.crawl_delay(USER_AGENT) or 1)

db = firestore.Client()
cache = Cache(db)

_error_reporting_client = error_reporting.Client(
) if 'GOOGLE_APPLICATION_CREDENTIALS' in os.environ else None


def report_exception():
    if _error_reporting_client is not None:
        _error_reporting_client.report_exception()
    else:
        logging.exception('Exception')


publisher = pubsub_v1.PublisherClient()
crawl_topic_path = publisher.topic_path(config.CLOUD_PROJECT, 'crawl')


@functions_framework.cloud_event
def crawl_url(cloud_event):
    """Crawl one URL, received from a PubSub queue."""
    try:
        do_crawl_url(cloud_event)
    except Exception:
        report_exception()


def do_crawl_url(cloud_event):
    logging.info('Invoked with %r', cloud_event.data)
    data = cloud_event.data
    current_crawl, prev_crawl = get_crawl(data)
    url = data['url']
    assert ok_to_crawl(url), url
    if url in crawled_urls:
        return

    publisher = OutboundLinkPublisher(prev_crawl, current_crawl)
    cached_response = cache.response_for(
        url=url, prev_crawl=prev_crawl, curr_crawl=current_crawl)
    if cached_response.state == CacheState.FRESH:
        return

    wait_for_next_fetch()
    fresh_response = cached_response.fetch(SESSION)

    if fresh_response.status_code//100 == 3:
        publisher.publish(cached_response.headers['location'])

    if fresh_response.links:
        for link in fresh_response.links:
            publisher.publish(link)
    publisher.wait()
    # After we've published all the links, we can mark the URL as crawled.
    logging.info('Writing %r to Firestore', fresh_response)
    fresh_response.write_to_firestore(db, current_crawl)


def get_crawl(data: dict) -> Tuple[str, str]:
    """Get the current and previous crawls from the PubSub message, or select
    them if they're not present."""
    current_crawl = data.get('crawl', None)
    if current_crawl is None:
        current_crawl = datetime.now(timezone.utc).date().isoformat()
    prev_crawl = data.get('prev_crawl', None)
    if prev_crawl is None:
        for collection in db.collections():
            if not collection.id.startswith('crawl-'):
                continue
            collection_date = collection.id.remove_prefix('crawl-')
            if collection_date < current_crawl and (prev_crawl is None or collection_date > prev_crawl):
                prev_crawl = collection_date

    return current_crawl, prev_crawl


def ok_to_crawl(url: str):
    return url.startswith('https://www.portland.gov/transportation') and robots.can_fetch(USER_AGENT, url)


def wait_for_next_fetch():
    """Wait until the next fetch is allowed."""
    global next_fetch
    now = datetime.now(timezone.utc)
    if now < next_fetch:
        time.sleep((next_fetch - now).total_seconds())
    next_fetch = datetime.now(timezone.utc) + crawl_delay


class OutboundLinkPublisher:
    """Publishes crawled outbound links to the PubSub queue.

    Call self.wait() before returning from the Cloud Function to be sure the
    publications make it up.
    """

    def __init__(self, prev_crawl: str, current_crawl: str):
        self.prev_crawl = prev_crawl
        self.current_crawl = current_crawl
        self.publish_futures = []

    def publish(self, url: str) -> None:
        if ok_to_crawl(url) and url not in crawled_urls:
            data = json.dumps(
                {'crawl': self.current_crawl, 'prev_crawl': self.prev_crawl, 'url': url})
            self.publish_futures.append(publisher.publish(
                crawl_topic_path, data.encode('utf-8')))

    def wait(self):
        futures.wait(self.publish_futures,
                     return_when=futures.ALL_COMPLETED)
