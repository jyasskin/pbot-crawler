import curses
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.robotparser import RobotFileParser

import requests
import whatwg_url
from bs4 import BeautifulSoup

URL_ORIGIN = 'https://www.portland.gov/'

SESSION = requests.Session()
USER_AGENT = 'PBOT Crawler'
SESSION.headers.update({'user-agent': USER_AGENT})


class Crawl:
    def __init__(self, out_dir: Path, roots: List[str], max_size: Optional[int] = None):
        """Represents the state of an active crawl.

        Args:
            out_dir: The directory to write the output to.
            roots: A list of root URLs to start the crawl with.
            max_size: The maximum size of the crawl in bytes. If None, the crawl will continue until there are no more pages to fetch.
        """
        self.out_dir = out_dir / datetime.now(timezone.utc).date().isoformat()
        self.pending = set(roots)
        self.complete = set()
        self.total_size = 0
        self.max_size = max_size
        self.robots = RobotFileParser(URL_ORIGIN + 'robots.txt')
        self.robots.read()
        self.crawl_delay = self.robots.crawl_delay(USER_AGENT)
        if self.crawl_delay is None:
            self.crawl_delay = 1
        self.crawl_delay = timedelta(seconds=self.crawl_delay)

        self.next_fetch = datetime.now(timezone.utc)

    def ok_to_crawl(self, url):
        return url.startswith('https://www.portland.gov/transportation') and self.robots.can_fetch(USER_AGENT, url)

    def wait_for_next_fetch(self):
        """Wait until the next fetch is allowed."""
        now = datetime.now(timezone.utc)
        if now < self.next_fetch:
            time.sleep((self.next_fetch - now).total_seconds())
        self.next_fetch = datetime.now(timezone.utc) + self.crawl_delay

    def is_complete(self):
        return len(self.pending) == 0 or (self.max_size is not None and self.total_size > self.max_size)

    def add_pending(self, url):
        if self.ok_to_crawl(url) and url not in self.complete:
            self.pending.add(url)


def fetch_one(crawl: Crawl, stdscr):
    """Fetch one URL from the crawl, and add its links back to the crawl.

    Args:
        crawl: The crawl to fetch from.
        stdscr: A curses window to write progress into
    """
    url = crawl.pending.pop()
    crawl.complete.add(url)

    describe_progress(url, crawl, stdscr)

    assert crawl.ok_to_crawl(url), url
    path = crawl.out_dir / url[len(URL_ORIGIN):].lstrip('/')

    response = CachedResponse(path)
    crawl.total_size += response.file_size  # 0 if the response wasn't cached.
    if response.status_code == 0:
        crawl.wait_for_next_fetch()
        with SESSION.get(url, stream=True, allow_redirects=False) as response:
            write_response(crawl, response, path)
    if response.status_code//100 == 3:
        crawl.add_pending(response.headers['location'])
        return

    if is_good_html_response(response):
        soup = BeautifulSoup(response.content, 'lxml')
        for link in soup.find_all('a', href=True):
            # Skip nofollow links. This isn't strictly required by the spec, but
            # nofollow links seem less valuable, so we can focus on the other
            # ones. We'll see if this misses anything important.
            if 'nofollow' in link.get('rel', []):
                continue
            href = urljoin(url, link['href'].strip())
            crawl.add_pending(href)


def is_good_html_response(response):
    return response.status_code == 200 and response.headers.get('content-type', '').startswith('text/html')


def write_response(crawl: Crawl, response: requests.Response, path: Path):
    """Write a response to the crawl's output directory.

    Args:
        crawl: The crawl to write to.
        response: The response to write.
        path: The path to write to.

    Returns: The content of HTML responses, or None for other content types.
    """
    path.mkdir(parents=True, exist_ok=True)
    with open(path/'#status', 'w') as status:
        print(response.status_code, file=status)
    with open(path/'#headers', 'w') as headers:
        for name, value in response.headers.lower_items():
            crawl.total_size += headers.write(f'{name}: {value}\n')
    # We don't need the content of non-HTML files or failed responses.
    if is_good_html_response(response):
        with open(path/'#content', 'wb') as content_file:
            content = response.content
            crawl.total_size += content_file.write(content)
            return content
    else:
        response.close()
    return None


def urljoin(base, relative):
    """Join a base URL and a relative URL, removing any fragments."""
    url = whatwg_url.parse_url(relative, base=base)
    url.fragment = None
    return url.href


class CachedResponse:
    def __init__(self, path: Path):
        """Loads a response from a path where it was previously crawled.

        The status code is read from path/#status; the headers from path/#headers; and the body from path/#content.

        Records the file size of the cached response.
        """
        self.file_size = 0
        self.status_code = 0
        self.headers = {}
        self.content = None

        try:
            print(f'Checking {path/"#status"} ... ', end='')
            with open(path/'#status', 'r') as status_file:
                self.status_code = int(status_file.read())
        except FileNotFoundError:
            print('Missing')
            return
        self.file_size += (path/'#headers').stat().st_size
        with open(path/'#headers', 'r') as headers_file:
            self.headers = dict(line.split(': ', 1)
                                for line in headers_file)
        if is_good_html_response(self):
            with open(path/'#content', 'rb') as content_file:
                self.content = content_file.read()
                self.file_size += len(self.content)
        print(
            f'Present: status {self.status_code}; {len(self.content) if self.content else 0} bytes')


def describe_progress(current_url: str, crawl: Crawl, stdscr):
    """Print a description of the current progress of the crawl."""
    if stdscr:
        maxy, maxx = stdscr.getmaxyx()
        stdscr.addnstr(maxy - 3, 0, f'Current URL: {current_url}', maxx-1)
        stdscr.addnstr(
            maxy - 2, 0, f'Crawled resources: {len(crawl.complete)}', maxx-1)
        stdscr.addnstr(maxy - 1, 0, f'Bytes used: {crawl.total_size}', maxx-1)
        stdscr.clrtoeol()
        stdscr.refresh()
    else:
        print(
            f'{len(crawl.pending)}/{len(crawl.complete)} resources left; {crawl.total_size} bytes; crawling {current_url}')


def main(stdscr=None):
    crawl = Crawl(Path('out'), [
                  'https://www.portland.gov/transportation'], max_size=1*1024*1024*1024)

    while not crawl.is_complete():
        fetch_one(crawl, stdscr)

    return crawl


if __name__ == '__main__':
    # Make space for the status display.
    crawl = main()  # curses.wrapper(main)
    print(
        f'Crawled {len(crawl.complete)} resources, using {crawl.total_size} bytes.')
