import debugModule from "debug";
import { Temporal } from "temporal-polyfill";

const debug = debugModule("pbotcrawl");

export function without_origin(url: string): string {
  const parsed = new URL(url);
  return `${parsed.pathname}${parsed.search}`;
}

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

export function web_archive(url: string, latest_date?: string | Temporal.PlainDate | undefined): string {
  function pad(n: number, digits: number): string {
    return String(n).padStart(digits, "0");
  }

  let date_param: string;
  if (latest_date === undefined) {
    date_param = "*";
  } else {
    if (typeof latest_date === 'string') {
      latest_date = Temporal.PlainDate.from(latest_date);
    }
    const d = latest_date.add({ days: 1 });
    date_param = `${pad(d.year, 4)}${pad(d.month, 2)}${pad(d.day, 2)}000000`;
  }
  return `https://web.archive.org/web/${date_param}/${url}`;
}

export function getFormDataString(formData: FormData, name: string): string | undefined {
  const result = formData.get(name);
  if (typeof result === "string") {
    return result;
  }
  return undefined;
}

export function renderEmail(email: string, name: string | undefined | null): string {
  if (name) {
    return `${name} <${email}>`;
  } else {
    return email;
  }
}
