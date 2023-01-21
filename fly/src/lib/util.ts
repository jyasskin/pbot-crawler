import debugModule from "debug";
import { Temporal } from "temporal-polyfill";

const debug = debugModule("pbotcrawl");

export function parse_crawl_date(crawl_date: string | undefined): Temporal.PlainDate | undefined {
  if (crawl_date === undefined) {
    return undefined;
  }
  if (!/^\d\d\d\d-\d\d-\d\d$/.test(crawl_date)) {
    debug("Invalid crawl date: %s", crawl_date);
    return undefined;
  }
  try {
    return Temporal.PlainDate.from(crawl_date);
  } catch (e) {
    debug("%O", e);
    return undefined;
  }
}
