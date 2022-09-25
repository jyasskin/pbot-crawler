import curses
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Union
from urllib.robotparser import RobotFileParser

import requests
import whatwg_url
from bs4 import BeautifulSoup

from cache import Cache, CacheState

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
        self.current_crawl = out_dir / \
            datetime.now(timezone.utc).date().isoformat()
        self.prev_crawl = newest_subdirectory_except(
            out_dir, self.current_crawl)
        self.cache = Cache(URL_ORIGIN, out_dir,
                           self.current_crawl, self.prev_crawl)
        self.pending = set(roots)
        self.complete = set()
        self.total_size = 0
        self.max_size = max_size
        self.robots = RobotFileParser(URL_ORIGIN + 'robots.txt')
        self.robots.read()
        self.crawl_delay = timedelta(
            seconds=self.robots.crawl_delay(USER_AGENT) or 1)

        self.next_fetch = datetime.now(timezone.utc)

    def ok_to_crawl(self, url: str):
        return url.startswith('https://www.portland.gov/transportation') and self.robots.can_fetch(USER_AGENT, url)

    def wait_for_next_fetch(self):
        """Wait until the next fetch is allowed."""
        now = datetime.now(timezone.utc)
        if now < self.next_fetch:
            time.sleep((self.next_fetch - now).total_seconds())
        self.next_fetch = datetime.now(timezone.utc) + self.crawl_delay

    def is_complete(self):
        return len(self.pending) == 0 or (self.max_size is not None and self.total_size > self.max_size)

    def add_pending(self, url: str):
        if self.ok_to_crawl(url) and url not in self.complete:
            self.pending.add(url)


def newest_subdirectory_except(out_dir: Path, except_dir: Path) -> Union[Path, None]:
    """Find the newest subdirectory of a directory, excluding a specific directory.

    Only examines subdirectories in ISO date format.

    Args:
        out_dir: The directory to search.
        except_dir: The directory to exclude.

    Returns: The newest subdirectory, or None if there are no other subdirectories.
    """
    newest = None
    newest_date = None
    for sub_dir in out_dir.iterdir():
        try:
            sub_dir_date = date.fromisoformat(sub_dir.name)
        except ValueError:
            continue
        if sub_dir.is_dir() and sub_dir != except_dir and (
                newest_date is None or sub_dir_date > newest_date):
            newest = sub_dir
            newest_date = sub_dir_date
    return newest


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

    response = crawl.cache.response_for(url)
    if response.state != CacheState.FRESH:
        crawl.wait_for_next_fetch()
        response.fetch(SESSION)
    crawl.total_size += response.file_size

    if response.status_code//100 == 3:
        crawl.add_pending(response.headers['location'])
        return

    if response.content:
        soup = BeautifulSoup(response.content, 'lxml')
        for link in soup.find_all('a', href=True):
            # Skip nofollow links. This isn't strictly required by the spec, but
            # nofollow links seem less valuable, so we can focus on the other
            # ones. We'll see if this misses anything important.
            if 'nofollow' in link.get('rel', []):
                continue
            try:
                href = urljoin(url, link['href'].strip())
            except whatwg_url.UrlParserError:
                continue

            crawl.add_pending(clean_url(href).href)


def urljoin(base: str, relative: str) -> whatwg_url.Url:
    """Join a base URL and a relative URL, removing any fragments."""
    url = whatwg_url.parse_url(relative, base=base)
    url.fragment = None
    return url


def clean_url(url: whatwg_url.Url) -> whatwg_url.Url:
    """Removes query parameters that don't affect the resulting page."""
    query = urllib.parse.parse_qs(url.query)
    query.pop('utm_medium', None)
    query.pop('utm_source', None)
    url.query = urllib.parse.urlencode(query, doseq=True) or None
    return url


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
            f'{len(crawl.pending)}/{len(crawl.complete)} resources left; {crawl.total_size} bytes; crawling {current_url!a}')


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
