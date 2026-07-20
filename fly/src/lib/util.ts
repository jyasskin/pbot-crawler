import type { AstroCookies } from "astro";
import debugModule from "debug";
import { createHash } from "node:crypto";
import "temporal-polyfill/global";

const debug = debugModule("pbotcrawl");

export function without_origin(url: string): string {
  const parsed = new URL(url);
  return `${parsed.pathname}${parsed.search}`;
}

export function parse_crawl_date(
  crawl_date: string | undefined,
): Temporal.PlainDate | undefined {
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

export function web_archive(
  url: string,
  latest_date?: string | Temporal.PlainDate | undefined,
): string {
  function pad(n: number, digits: number): string {
    return String(n).padStart(digits, "0");
  }

  let date_param: string;
  if (latest_date === undefined) {
    date_param = "*";
  } else {
    if (typeof latest_date === "string") {
      latest_date = Temporal.PlainDate.from(latest_date);
    }
    const d = latest_date.add({ days: 1 });
    date_param = `${pad(d.year, 4)}${pad(d.month, 2)}${pad(d.day, 2)}000000`;
  }
  return `https://web.archive.org/web/${date_param}/${url}`;
}

export function getFormDataString(
  formData: FormData,
  name: string,
): string | undefined {
  const result = formData.get(name);
  if (typeof result === "string") {
    return result;
  }
  return undefined;
}

export function renderEmail(
  email: string,
  name: string | undefined | null,
): string {
  if (name) {
    return `${name} <${email}>`;
  } else {
    return email;
  }
}

export function sha256(str: string): Uint8Array<ArrayBuffer> {
  const hash = createHash("sha256");
  hash.update(str, "utf8");
  return new Uint8Array(hash.digest().buffer);
}

/** Resolves no sooner than `when`. */
export function until(when: Temporal.Instant): Promise<void> {
  return new Promise((resolve) => {
    const ms = Temporal.Now.instant().until(when).total("millisecond");
    if (ms > 0) {
      setTimeout(
        resolve,
        Temporal.Now.instant().until(when).total("millisecond"),
      );
    } else {
      resolve();
    }
  });
}

export function timeFormatterFromCookies(
  cookies: AstroCookies,
): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat(cookies.get("locale")?.value ?? "en_US", {
    timeZone: cookies.get("timeZoneId")?.value ?? "utc",
    dateStyle: "short",
    timeStyle: "long",
  });
}

export function renderException(e: unknown): string {
  let error: string[] = [];
  while (e instanceof Error) {
    const message = e.stack ?? e.message;
    error.push(message.startsWith(e.name) ? message : `${e.name}: ${message})`);
    if (e.cause != null) {
      error.push("caused by");
    }
    e = e.cause;
  }
  if (e != null) {
    error.push(String(e));
  }
  return error.join("\n");
}

export class FetchError extends Error {
  constructor(originalException: unknown) {
    if (originalException instanceof TypeError) {
      // fetch() throws network errors as TypeError:
      // https://developer.mozilla.org/en-US/docs/Web/API/Window/fetch#exceptions
      super(originalException.message, { cause: originalException.cause });
    } else {
      super("fetch() failed", { cause: originalException });
    }
    this.name = "FetchError";
  }
}
export const fetchWithDistinctiveExceptions: typeof fetch = async (
  input,
  init,
) => {
  return fetch(input, init).catch((e) => {
    throw new FetchError(e);
  });
};
