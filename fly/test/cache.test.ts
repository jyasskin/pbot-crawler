import type { ContentStoreCreateManyInput } from "@generated/prisma/models/ContentStore";
import { fetchWithCache, type FetchWithCacheResult } from "@lib/cache";
import { prisma } from "@lib/prisma";
import { sha256 } from "@lib/util";
import nock from "nock";
import { beforeEach, expect, test, vi } from "vitest";

//const TEST_LINK_TARGET = "https://www.portland.gov/transportation/link/target";
const TEST_PAGE1 = "https://www.portland.gov/transportation";
const TEST_PAGE2 = "https://www.portland.gov/transportation/has-text-content";
const THE_ETAG = "This is an ETag";

function contentStoreRow({
  content,
}: {
  content: string;
}): ContentStoreCreateManyInput {
  return {
    hash: sha256(content),
    content,
    latestRetrievedSize: content.length,
  };
}

beforeEach(async () => {
  nock.disableNetConnect();
  vi.useFakeTimers();
  return async () => {
    vi.useRealTimers();
    nock.enableNetConnect();
  };
});
beforeEach(async () => {
  await prisma.contentStore.create({
    data: contentStoreRow({ content: "This is some text\n" }),
  });
  await prisma.crawl.create({
    data: {
      date: "2022-09-26",
      startTime: "2022-09-26T12:53:12Z",
      state: "RUNNING",
    },
  });
  await prisma.knownUrl.create({
    data: {
      url: TEST_PAGE1,
      cache: {
        create: {
          httpStatus: 200,
          eTag: THE_ETAG,
          contentType: "text/html",
          fetchStart: "2022-09-26T12:53:12Z",
          fetchEnd: "2022-09-26T12:53:13Z",
          normalizedContent: { connect: { content: "This is some text\n" } },
        },
      },
    },
  });

  await prisma.knownUrl.create({
    data: {
      url: TEST_PAGE2,
      cache: {
        create: {
          httpStatus: 200,
          eTag: THE_ETAG,
          contentType: "text/html",
          fetchStart: "2022-09-26T12:53:13Z",
          fetchEnd: "2022-09-26T12:53:14Z",
          normalizedContent: { connect: { content: "This is some text\n" } },
        },
      },
    },
  });
});

test("cached response fresh", async () => {
  const page1 = await prisma.knownUrl.findUniqueOrThrow({
    where: { url: TEST_PAGE1 },
  });
  expect(
    await fetchWithCache(page1, Temporal.Instant.from("2022-09-25T00:00Z")),
  ).toEqual({
    contentHash: new Uint8Array(sha256("This is some text\n")),
    contentType: "text/html",
    eTag: THE_ETAG,
    excluded: null,
    fetchEnd: new Date("2022-09-26T12:53:13.000Z"),
    fetchStart: new Date("2022-09-26T12:53:12.000Z"),
    httpStatus: 200,
    lastModified: null,
    location: null,
    normalizedContent: { links: [] },
    url: {
      id: expect.any(Number),
      url: "https://www.portland.gov/transportation",
    },
    urlId: expect.any(Number),
  } satisfies FetchWithCacheResult);
});

test("cached response stale", async () => {
  const page1 = await prisma.knownUrl.findUniqueOrThrow({
    where: { url: TEST_PAGE1 },
  });
  vi.setSystemTime(new Date("2022-09-28T05:32Z"));
  nock("https://www.portland.gov")
    .matchHeader("if-none-match", THE_ETAG)
    .get("/transportation")
    .reply(200, "Page content", {
      etag: "New etag",
      "content-type": "text/html",
    });
  expect(
    await fetchWithCache(page1, Temporal.Instant.from("2022-09-27T00:00Z")),
  ).toEqual({
    contentHash: sha256("Page content\n"),
    contentType: "text/html",
    eTag: "New etag",
    excluded: null,
    fetchEnd: new Date("2022-09-28T05:32Z"),
    fetchStart: new Date("2022-09-28T05:32Z"),
    httpStatus: 200,
    lastModified: null,
    location: null,
    normalizedContent: { links: [] },
    url: {
      id: expect.any(Number),
      url: "https://www.portland.gov/transportation",
    },
    urlId: expect.any(Number),
  } satisfies FetchWithCacheResult);
});

test("cached response stale and validates", async () => {
  const page1 = await prisma.knownUrl.findUniqueOrThrow({
    where: { url: TEST_PAGE1 },
  });
  vi.setSystemTime(new Date("2022-09-28T05:32Z"));
  nock("https://www.portland.gov")
    .matchHeader("if-none-match", THE_ETAG)
    .get("/transportation")
    .reply(304, "Ignored page content", {
      etag: "New etag",
      "content-type": "text/html",
    });
  expect(
    await fetchWithCache(page1, Temporal.Instant.from("2022-09-27T00:00Z")),
  ).toEqual({
    contentHash: new Uint8Array(sha256("This is some text\n")),
    contentType: "text/html",
    eTag: "New etag",
    excluded: null,
    fetchEnd: new Date("2022-09-28T05:32Z"),
    fetchStart: new Date("2022-09-28T05:32Z"),
    httpStatus: 200,
    lastModified: null,
    location: null,
    normalizedContent: { links: [] },
    url: {
      id: expect.any(Number),
      url: "https://www.portland.gov/transportation",
    },
    urlId: expect.any(Number),
  } satisfies FetchWithCacheResult);
});
