import "temporal-polyfill/global";
import { Robots } from "./robots";

export const USER_AGENT =
  "PBOT Crawler v2 from github.com/jyasskin/pbot-crawler";

export const URL_PREFIX = new URL("https://www.portland.gov/transportation");

export const URL_ORIGIN = new URL(URL_PREFIX.origin);

export const robots = new Robots(URL_ORIGIN);

export function stripPrefix(url: string): string {
  const prefix = URL_PREFIX.href;
  if (url.startsWith(prefix)) {
    return url.slice(prefix.length);
  }
  return url;
}
