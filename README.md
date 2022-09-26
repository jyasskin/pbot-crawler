# PBOT Crawler

We'd like to crawl the [PBOT website](https://www.portland.gov/transportation)
approximately weekly in order to identify new and changed pages. This shouldn't
put too much load on the site, which I approximate by limiting requests to
1/second.

`local/` has a crawler that runs on a single machine and dumps the crawl to the
local filesystem. It optimizes fetches by treating the previous crawl as a
cache, but it doesn't identify changed pages.


## Google Cloud design

I've tried to limit this to the free tier services. For sizing estimates, PBOT's
site has about 3500 pages taking about 200M for bodies and 60M for headers.

* [Cloud Scheduler](https://cloud.google.com/scheduler/docs) to kick off the
  crawl weekly, by queuing the root of the PBOT site.
* [Pub/Sub queue](https://cloud.google.com/pubsub/docs) to hold the list of
  to-be-crawled URLs. This queue will wind up with lots of duplicates that the
  next Function will need to deduplicate.
* A Function to do the actual crawl. See [below](#the-crawl-function) for its
  strategy.
* [Firestore](https://cloud.google.com/firestore/docs) to record the set of URLs
  crawled each week and the content of each URL, including its status, caching
  headers, and outbound links. See [below](#firestore-schema) for its schema.

### The crawl function

Uses an instance limit of 1 so we can use global variables to rate-limit
external fetches and to deduplicate fetch URLs. It would be cleaner to use
Memorystore or Firestore for both, but Memorystore isn't in the Cloud free tier,
and doing this in Firestore would risk exceeding the 20k/day free writes.

1. Receive a PubSub event with a URL to crawl.
1. Check the global set of crawled URLs to deduplicate.
1. Query the URL from the current crawl in Firestore to deduplicate more
   reliably. If it's there, we'll assume that its outbound URLs have been queued
   to PubSub.
1. Query the URL from the previous crawl in Firestore to use its
   [`ETag`](https://httpwg.org/specs/rfc9111.html) and discover whether the page
   is new or updated.
1. Fetch the URL from PBOT, with cache headers.
1. If it's new or changed, record that somewhere (TODO), and ask the Web Archive
   to archive it. Maybe this is another PubSub queue and Function?
1. Gather its outbound links, either from the previous crawl or using
   [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/).
1. Queue its outbound links to PubSub, deduplicating each one against the local
   set of crawled URLs.
1. Write the page to the current crawl in Firestore.
1. Report success!

### Firestore schema

* `/`
  * `content`
    * Document IDs are the SHA-256 of the resource body
      * `outbound_links`: array of outbound absolute URLs.
  * `crawl-YYYY-MM-DD` collection for each crawl.
    * Document IDs are SHA-256(URL).
      * `url`: The actual URL.
      * `new`: True if this document was new in this crawl.
      * `changed`: True if this document was changed in this crawl.
      * `status`: 200, etc.
      * `headers`: Lowercase map of a few HTTP response headers.
        * etag
        * last-modified
        * location
      * `content`: Reference into `content` collection.
