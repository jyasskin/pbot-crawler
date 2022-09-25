import hashlib
import os.path
from enum import Enum, auto
from pathlib import Path
from typing import Dict

import requests

from util import is_good_html_response


class Cache:
    """Represents the cache of previously fetched pages within a single origin.

    Represents an HTTP cache of crawled pages, with fresh pages stored in the
    "current" crawl's subdirectory, stale pages loaded from the "previous"
    crawl's subdirectory, and the actual contents of pages in a
    content-addressed object store, addressed by the SHA-256 digest of the
    content. To limit the size of the object store subdirectories, an object is
    stored in digest[:2]/digest[2:].

    Each page is represented as a directory that contains #status, #headers, and
    #content files. This allows us to represent a URL structure with both /foo
    and /foo/bar resources without risking collisions, since '#' can't appear in
    a URL. We don't currently escape any characters.
    """

    def __init__(self, origin: str, cache_root: Path, current_crawl: Path, prev_crawl: Path):
        self.origin = origin
        self.cache_root = cache_root
        self.current_crawl = current_crawl
        self.prev_crawl = prev_crawl
        self.object_store = cache_root/"objects"

    def response_for(self, url: str) -> 'CachedResponse':
        """Loads url from the cache into a CachedResponse."""
        return CachedResponse(self, url)


class CacheState(Enum):
    # The response is not in the cache.
    ABSENT = auto()
    # The response is in previous crawl, and will be validated before use.
    STALE = auto()
    # The response is in current crawl, and will not be re-fetched.
    FRESH = auto()


class CachedResponse:
    def __init__(self, cache: Cache, url: str):
        """Loads a response from a path where it was previously crawled.

        The status code is read from path/#status; the headers from path/#headers; and the body from path/#content.

        Records the file size of the cached response.
        """
        self.cache = cache
        self.url = url
        self.file_size = 0
        self.status_code = 0
        self.headers: Dict[str, str] = {}
        self.content = None

        assert url.startswith(cache.origin), url
        self.url_path = url[len(cache.origin):].lstrip('/')

        path = cache.current_crawl / self.url_path

        if (path/'#status').exists():
            self.state = CacheState.FRESH
        else:
            path = cache.prev_crawl / self.url_path
            if (path/'#status').exists():
                self.state = CacheState.STALE
            else:
                self.state = CacheState.ABSENT
                return

        with open(path/'#status', 'r') as status_file:
            self.status_code = int(status_file.read())

        # Treat cached errors in the previous crawl as missing entirely.
        if self.status_code >= 400:
            self.state = CacheState.ABSENT
            return

        self.file_size += (path/'#headers').stat().st_size
        with open(path/'#headers', 'r') as headers_file:
            self.headers = dict(line.strip().split(': ', 1)
                                for line in headers_file)

        if is_good_html_response(self):
            with open(path/'#content', 'rb') as content_file:
                self.content = content_file.read()
                self.file_size += len(self.content)
        print(
            f'{self.state.name}: status {self.status_code}; {len(self.content or "")} bytes')

    def fetch(self, session: requests.Session) -> None:
        """Freshens this resource from the network if necessary, and writes it to the cache.
        """
        if self.state == CacheState.FRESH:
            return
        headers = None
        if self.state == CacheState.STALE:
            if 'etag' in self.headers:
                headers = {'If-None-Match': self.headers['etag']}
            elif 'last-modified' in self.headers:
                headers = {'If-Modified-Since': self.headers['last-modified']}

        # Fetch the URL for either STALE or ABSENT resources.
        with session.get(self.url, headers=headers, stream=True, allow_redirects=False) as response:
            if response.status_code == 304 and self.state == CacheState.STALE:
                self.status_code = 200
                # Update stored headers as described by https://httpwg.org/specs/rfc9111.html#rfc.section.3.2
                for header, value in response.headers.lower_items():
                    if header not in ['content-length', 'content-encoding', 'transfer-encoding']:
                        self.headers[header] = value
            else:
                self.status_code = response.status_code
                self.headers = dict(response.headers.lower_items())
                self.content = None
                # We don't need the content of non-HTML files or failed responses.
                if is_good_html_response(response):
                    self.content = response.content
            self.state = CacheState.FRESH
        self._write()

    def _write(self) -> None:
        """Write a response to the current crawl's directory, making sure the
        content is in the content-addressed store.
        """
        path = self.cache.current_crawl / self.url_path
        path.mkdir(parents=True, exist_ok=True)

        file_size = 0

        with open(path/'#status', 'w') as status:
            print(self.status_code, file=status)
        with open(path/'#headers', 'w') as headers:
            for name, value in self.headers.items():
                file_size += headers.write(f'{name}: {value}\n')
        if self.content:
            digest = hashlib.sha256(self.content).hexdigest()
            cas_file = self.cache.object_store/digest[:2]/digest[2:]
            cas_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(cas_file, 'xb') as content_file:
                    file_size += content_file.write(self.content)
            except FileExistsError:
                # Don't bother rewriting an identical file into the CAS.
                pass
            content_path = path/'#content'
            content_path.symlink_to(os.path.relpath(cas_file, path))

        self.file_size = file_size
