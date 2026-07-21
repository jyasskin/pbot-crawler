import type {
  CachedPageInclude,
  CachedPageUncheckedUpdateInput,
  CachedPageUpdateInput,
  KnownUrlModel,
} from "@generated/prisma/models";
import { type CachedPageModel } from "@generated/prisma/models/CachedPage.js";
import { robots, URL_PREFIX, USER_AGENT } from "./crawl_config";
import { normalizeHtml } from "./html_processor";
import { prisma } from "./prisma";
import { fetchWithDistinctiveExceptions } from "./util";

export type FetchWithCacheResult = CachedPageModel & {
  url: KnownUrlModel;
  normalizedContent: { links: KnownUrlModel[] } | null;
};

/**
 * @param urlId KnownUrl.id
 * @param oldestFresh The time the current crawl started. Any cached pages newer than this will just
 * be returned. Older pages will be revalidated per RFC9111.
 */
export async function fetchWithCache(
  url: KnownUrlModel,
  oldestFresh: Temporal.Instant,
): Promise<FetchWithCacheResult> {
  const include = {
    url: true,
    normalizedContent: { select: { links: true } },
  } satisfies CachedPageInclude;
  const cachedValue = await prisma.cachedPage.findUnique({
    where: { urlId: url.id },
    include,
  });
  if (
    cachedValue &&
    Temporal.Instant.compare(
      oldestFresh,
      cachedValue.fetchEnd.toTemporalInstant(),
    ) <= 0
  ) {
    return cachedValue;
  }

  const fetchStart = new Date();

  const inScope = url.url.startsWith(URL_PREFIX.href);
  if (!inScope || !(await robots.canFetch(url.url, oldestFresh))) {
    const update = {
      fetchStart,
      fetchEnd: fetchStart,
      httpStatus: 403, // Best match for robot-excluded.
      excluded: !inScope ? "SCOPE" : "ROBOTS",
      contentHash: null,
    } satisfies CachedPageUncheckedUpdateInput;
    return await prisma.cachedPage.upsert({
      where: { urlId: url.id },
      create: Object.assign({ urlId: url.id }, update),
      update,
      include,
    });
  }

  // Revalidate the cached response, if there is one.
  let headers = new Headers({ "User-Agent": USER_AGENT });
  if (cachedValue?.eTag != null) {
    headers.set("If-None-Match", cachedValue.eTag);
  } else if (cachedValue?.lastModified) {
    headers.set("If-Modified-Since", cachedValue.lastModified);
  }
  const controller = new AbortController();
  try {
    const response = await fetchWithDistinctiveExceptions(url.url, {
      headers,
      redirect: "manual",
      signal: controller.signal,
    });
    if (response.status === 304) {
      const update = {
        fetchStart,
        fetchEnd: new Date(),
        excluded: null,
        eTag: response.headers.get("etag") ?? cachedValue?.eTag,
        location: response.headers.get("location") ?? cachedValue?.location,
        contentType:
          response.headers.get("content-type") ?? cachedValue?.contentType,
        lastModified:
          response.headers.get("last-modified") ?? cachedValue?.lastModified,
      } satisfies CachedPageUpdateInput;
      // If the 304 is returned in response to an `If-*` header as send above, the page will already
      // be in the cache. There's an upsert() here anyway in case the server incorrectly sent a 304.
      return await prisma.cachedPage.upsert({
        where: { urlId: url.id },
        create: Object.assign(
          {
            urlId: url.id,
            httpStatus: response.status,
          },
          update,
        ),
        update,
        include,
      });
    }

    // Cache miss: insert the new content.

    // Only store content if the server sent HTML.
    let contentStoreUpsert = undefined;
    if (
      response.status === 200 &&
      response.headers.get("content-type")?.startsWith("text/html")
    ) {
      contentStoreUpsert = {
        ...normalizeHtml(await response.text(), url.url),
        select: { hash: true },
      };
    }
    // Transaction to ensure that even if we GC content store entries, this one still exists when
    // it's used for the cache update.
    return await prisma.$transaction(async (tx) => {
      const contentHash =
        contentStoreUpsert &&
        (await tx.contentStore.upsert(contentStoreUpsert)).hash;

      const update = {
        fetchStart,
        fetchEnd: new Date(),
        httpStatus: response.status,
        excluded: null,
        eTag: response.headers.get("etag"),
        location: response.headers.get("location"),
        contentType: response.headers.get("content-type"),
        lastModified: response.headers.get("last-modified"),
      } satisfies CachedPageUpdateInput;
      return await tx.cachedPage.upsert({
        where: { urlId: url.id },
        create: {
          url: { connect: { id: url.id } },
          ...update,
          normalizedContent: contentHash
            ? { connect: { hash: contentHash } }
            : undefined,
        },
        update: {
          ...update,
          normalizedContent: contentHash
            ? { connect: { hash: contentHash } }
            : { disconnect: true },
        },
        include,
      });
    });
  } finally {
    controller.abort();
  }
}
