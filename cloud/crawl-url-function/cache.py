import copy
import os.path
from enum import Enum, auto
from hashlib import sha256
from typing import Callable, Dict, Optional, Sequence

import requests
from google.cloud import firestore

from htmlutil import scrape_links


def is_good_html_response(response):
    return response.status_code == 200 and response.headers.get('content-type', '').startswith('text/html')


class Cache:
    def __init__(self, db: firestore.Client):
        self.db = db

    def response_for(self, *, url: str, curr_crawl: str, prev_crawl: str) -> 'CachedResponse':
        """Loads url from the cache into a CachedResponse."""
        return CachedResponse(self.db, url, curr_crawl, prev_crawl)


class CacheState(Enum):
    # The response is not in the cache.
    ABSENT = auto()
    # The response is in previous crawl, and will be validated before use.
    STALE = auto()
    # The response is in current crawl, and will not be re-fetched.
    FRESH = auto()


class PresenceChange(Enum):
    # The resource is new since the last crawl.
    NEW = auto()
    # The resource didn't change since the last crawl.
    SAME = auto()
    # There's still a resource at this URL, but its content changed.
    CHANGED = auto()
    # The resource disappeared since the last crawl.
    REMOVED = auto()


RELEVANT_HEADERS = [
    'etag', 'last-modified', 'location', 'content-type']


class Response:
    url: str
    status_code: int
    headers: Dict[str, str]
    content_reference: Optional[firestore.DocumentReference] = None
    _links: Optional[Sequence[str]] = None

    @property
    def links(self):
        if self._links is None and self.content_reference is not None:
            self._links = self.content_reference.get().get('links')
        return self._links


class CachedResponse(Response):
    def __init__(self, db: firestore.Client, url: str, curr_crawl: str, prev_crawl: str):
        """Loads a response from the current or previous crawl in Firestore if
        it was previously crawled.
        """
        self.db = db
        self.url = url
        self.status_code = 0
        self.headers: Dict[str, str] = {}
        self.content_reference = None
        self.state = CacheState.ABSENT

        response_doc = read_one_firestore_doc(db.collection(
            f'crawl-{curr_crawl}').where('url', '==', self.url))

        print(repr(response_doc))

        if response_doc is not None:
            self.state = CacheState.FRESH
            return

        response_doc = read_one_firestore_doc(db.collection(
            f'crawl-{prev_crawl}').where('url', '==', self.url))
        print(repr(response_doc))
        if response_doc is not None:
            self.state = CacheState.STALE
        else:
            self.state = CacheState.ABSENT
            return

        self.status_code = response_doc.get('status_code')

        # Treat cached errors in the previous crawl as missing entirely.
        if self.status_code >= 400:
            self.state = CacheState.ABSENT
            return

        self.headers = response_doc.get('headers')

        if is_good_html_response(self):
            self.content_reference: firestore.DocumentReference = response_doc.get(
                'content')

    def fetch(self, session: requests.Session) -> 'FreshResponse':
        """Freshens this resource from the network."""
        assert self.state != CacheState.FRESH, "Shouldn't be trying to fetch fresh resources."

        result = FreshResponse(self.url)
        headers = None
        if self.state == CacheState.STALE:
            if 'etag' in self.headers:
                headers = {'If-None-Match': self.headers['etag']}
            elif 'last-modified' in self.headers:
                headers = {'If-Modified-Since': self.headers['last-modified']}

        # Fetch the URL for either STALE or ABSENT resources.
        with session.get(self.url, headers=headers, stream=True, allow_redirects=False) as response:
            if response.status_code == 304 and self.state == CacheState.STALE:
                result.status_code = 200
                # Update stored headers as described by https://httpwg.org/specs/rfc9111.html#rfc.section.3.2
                result.headers = self._update_relevant_headers(
                    copy.deepcopy(self.headers), response.headers)
                result.content_reference = self.content_reference
            else:
                result.status_code = response.status_code
                result.headers = self._update_relevant_headers(
                    {}, response.headers)
                result.content_reference = None
                # We don't need the content of non-HTML files or failed responses.
                if is_good_html_response(response):
                    result.content_reference = self.db.collection(
                        'content').document(sha256(response.content).hexdigest())
                    # Go ahead and write the links to the database. The
                    # content-addressed store isn't used for signaling any part
                    # of the crawl, and we'll definitely need the outbound links.
                    result._links = set_if_absent(result.content_reference, lambda: {
                        'links': list(scrape_links(
                            response.content, base_url=result.url))
                    })['links']

        return result

    @staticmethod
    def _update_relevant_headers(dst: Dict[str, str], src: Dict[str, str]) -> Dict[str, str]:
        """Copies keys in RELEVANT_HEADERS from src to dst.

        Returns dst.
        """
        for to_copy in RELEVANT_HEADERS:
            value = src.get(to_copy, None)
            if value is not None:
                dst.headers[to_copy] = value
        return dst


class FreshResponse(Response):
    def __init__(self, url: str):
        self.url = url
        self.status_code = 0
        self.headers = {}
        self.content_reference = None

    def write_to_firestore(self, db: firestore.Client, current_crawl: str) -> None:
        """Write a response to the current crawl's directory, making sure the
        content is in the content-addressed store.
        """
        db.collection(f'crawl-{current_crawl}').document(sha256(self.url).hexdigest).set({
            'url': self.url,
            'status_code': self.status_code,
            'headers': self.headers,
            'content': self.content_reference,
        })


def read_one_firestore_doc(query: firestore.Query) -> Optional[firestore.DocumentSnapshot]:
    """Reads one document from a Firestore query, or returns None if there are no documents."""
    return next(query.limit(1).stream(), None)


def set_if_absent(doc: firestore.DocumentReference, value_generator: Callable[[], dict]) -> dict:
    """Sets thea key in a Firestore document if it doesn't already exist.

    Returns the content of the document.
    """
    snapshot = doc.get()
    if snapshot.exists:
        return snapshot.to_dict()
    value = value_generator()
    doc.set(value)
    return value