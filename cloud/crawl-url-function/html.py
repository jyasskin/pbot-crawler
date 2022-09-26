import urllib.parse
from typing import Generator

import whatwg_url
from bs4 import BeautifulSoup


def scrape_links(content: bytes, base_url: str) -> Generator[str]:
    soup = BeautifulSoup(content, 'lxml')
    for link in soup.find_all('a', href=True):
        # Skip nofollow links. This isn't strictly required by the spec, but
        # nofollow links seem less valuable, so we can focus on the other
        # ones. We'll see if this misses anything important.
        if 'nofollow' in link.get('rel', []):
            continue
        try:
            href = urljoin(base_url, link['href'].strip())
        except whatwg_url.UrlParserError:
            continue
        yield clean_url(href).href


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
