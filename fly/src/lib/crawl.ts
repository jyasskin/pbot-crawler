import type { PageChange } from "@generated/prisma/enums";
import type {
  CachedPageModel,
  CrawledPageCrawlDateUrlIdCompoundUniqueInput,
  CrawledPageModel,
  CrawlInclude,
  CrawlModel,
} from "@generated/prisma/models";
import process from "node:process";
import { fetchWithCache } from "./cache";
import { robots, URL_PREFIX } from "./crawl_config";
import { debug } from "./debug";
import { prisma } from "./prisma";
import { FetchError, renderException, until } from "./util";

const INITIAL_PAGE = "https://www.portland.gov/transportation";

/** 6 days is long enough to start the next crawl. */
export function readyToCrawlAgain(latestCrawl: Pick<CrawlModel, "startTime">) {
  return (
    process.env.DEBUG_CAN_CRAWL_IMMEDIATELY ||
    latestCrawl.startTime
      .toTemporalInstant()
      .until(Temporal.Now.instant())
      .total("days") >= 6
  );
}

var crawlExecuting = false;
var crawlContinued: Temporal.Instant =
  Temporal.Instant.fromEpochMilliseconds(0);

type CrawlWorkOptions = {
  /// Postpones crawl cleanup work until all promises passed to this function have settled.
  waitUntil: (until: Promise<any>) => void;
};
async function doCrawlWork<T>(
  work: (options: CrawlWorkOptions) => Promise<T>,
): Promise<T | undefined> {
  if (
    crawlExecuting ||
    crawlContinued.until(Temporal.Now.instant()).total("minutes") < 1
  ) {
    // Don't start a parallel crawl process or retry more than once/minute.
    return;
  }
  crawlContinued = Temporal.Now.instant();
  const untils: Promise<any>[] = [];
  crawlExecuting = true;
  try {
    return await work({
      waitUntil: function waitUntil(until: Promise<any>) {
        untils.push(until);
      },
    });
  } finally {
    Promise.allSettled(untils).finally(() => {
      crawlExecuting = false;
    });
  }
}

export async function startCrawl(
  latestCrawl: CrawlModel | null,
): Promise<CrawlModel | undefined> {
  return doCrawlWork(async ({ waitUntil }) => {
    const startTime = Temporal.Now.zonedDateTimeISO("utc");
    if (process.env.DEBUG_CAN_CRAWL_IMMEDIATELY) {
      // Ensure the new crawl won't collide with an existing one.
      await prisma.crawl.deleteMany({
        where: { date: startTime.toPlainDate().toString() },
      });
      latestCrawl = await prisma.crawl.findFirst({
        orderBy: { startTime: "desc" },
      });
    }

    const initialUrls = latestCrawl
      ? (
          await prisma.crawledPage.findMany({
            where: { crawlDate: latestCrawl.date, httpStatus: { lt: 400 } },
            select: { url: { select: { url: true } } },
            distinct: "urlId",
          })
        ).map((page) => page.url.url)
      : [];
    if (!initialUrls.includes(INITIAL_PAGE)) {
      initialUrls.push(INITIAL_PAGE);
    }
    const newCrawl = await prisma.crawl.create({
      data: {
        date: startTime.toPlainDate().toString(),
        startTime: new Date(startTime.epochMilliseconds),
        state: "RUNNING",
        prevCrawl: latestCrawl
          ? { connect: { date: latestCrawl.date } }
          : undefined,
        pages: {
          create: initialUrls.map((url) => ({
            url: { connectOrCreate: { where: { url }, create: { url } } },
            state: "TODO",
          })),
        },
      },
      include: executeCrawlExtraInclude,
    });

    // Run the crawl in the background.
    waitUntil(executeCrawl(newCrawl));

    return newCrawl;
  });
}

export async function continueCrawl() {
  const latestCrawl = await prisma.crawl.findFirst({
    orderBy: { date: "desc" },
    include: executeCrawlExtraInclude,
  });
  if (latestCrawl?.state === "RUNNING" || latestCrawl?.state === "ERROR") {
    return doCrawlWork(async () => {
      // Restart the fetch for any pages that were in the middle of being fetched.
      await prisma.crawledPage.updateMany({
        where: { crawlDate: latestCrawl.date, state: "FETCHING" },
        data: { state: "TODO" },
      });
      await executeCrawl(latestCrawl);
    });
  }
}

const executeCrawlExtraInclude = {
  _count: {
    select: { pages: { where: { state: { in: ["TODO", "FETCHING"] } } } },
  },
} satisfies CrawlInclude;

async function executeCrawl(crawl: CrawlModel & { _count: { pages: number } }) {
  try {
    const crawlStartTime = crawl.startTime.toTemporalInstant();
    debug(
      "Running the %s crawl: %d pages left",
      crawl.date,
      crawl._count.pages,
    );
    while (true) {
      const nextPage = await prisma.crawledPage.findFirst({
        where: {
          crawl: { date: crawl.date },
          state: "TODO",
          OR: [{ nextFetchTime: null }, { nextFetchTime: { lt: new Date() } }],
        },
        include: { url: true },
      });
      if (nextPage == null) {
        const erroredPage = await prisma.crawledPage.findFirst({
          where: {
            crawl: { date: crawl.date },
            state: "TODO",
            nextFetchTime: { not: null },
          },
          orderBy: { nextFetchTime: "desc" },
          select: { nextFetchTime: true },
        });
        if (erroredPage == null || erroredPage.nextFetchTime == null) {
          break;
        }
        await until(erroredPage.nextFetchTime.toTemporalInstant());
        continue;
      }
      const crawlDate_urlId: CrawledPageCrawlDateUrlIdCompoundUniqueInput = {
        crawlDate: nextPage.crawlDate,
        urlId: nextPage.urlId,
      };
      const inScope = nextPage.url.url.startsWith(URL_PREFIX.href);
      if (
        !inScope ||
        !(await robots.canFetch(nextPage.url.url, crawlStartTime))
      ) {
        await prisma.crawledPage.update({
          where: { crawlDate_urlId },
          data: {
            state: "DONE",
            excluded: !inScope ? "SCOPE" : "ROBOTS",
          },
        });
        // No need to wait a second between non-crawled pages.
        continue;
      }

      const pageCrawlStart = Temporal.Now.instant();
      await prisma.crawledPage.update({
        where: { crawlDate_urlId },
        data: {
          state: "FETCHING",
          fetchStart: new Date(pageCrawlStart.epochMilliseconds),
        },
      });
      try {
        const newPage = await fetchWithCache(nextPage.url, crawlStartTime);
        const {
          fetchEnd,
          httpStatus,
          excluded,
          eTag,
          lastModified,
          location,
          contentType,
          contentHash,
          normalizedContent,
        } = newPage;
        const change = await computeChange(crawl, newPage);
        if (change === "NEW" || change === "CHANGED") {
          // TODO: Archive the page, and insert the archive link into the database.
        }
        if (normalizedContent && normalizedContent.links.length > 0) {
          // Queue links to be crawled. Do this before marking the page as done, so that a crash
          // retries the link-following.
          await prisma.$transaction(
            normalizedContent.links.map((link) =>
              prisma.crawledPage.upsert({
                where: {
                  crawlDate_urlId: { crawlDate: crawl.date, urlId: link.id },
                },
                create: {
                  crawl: { connect: { date: crawl.date } },
                  url: {
                    connectOrCreate: {
                      where: { url: link.url },
                      create: { url: link.url },
                    },
                  },
                  state: "TODO",
                },
                // If the page is already in the crawl, don't touch it.
                update: {},
              }),
            ),
          );
        }
        await prisma.crawledPage.update({
          where: { crawlDate_urlId },
          data: {
            state: "DONE",
            fetchEnd,
            httpStatus,
            excluded,
            eTag,
            lastModified,
            location,
            contentType,
            contentHash,
            change,
          },
        });
      } catch (e) {
        if (e instanceof FetchError) {
          const retryAgain = nextPage.fetchRetries < 3;
          await prisma.crawledPage.update({
            where: { crawlDate_urlId },
            data: {
              state: retryAgain ? "TODO" : "DONE",
              fetchStart: null,
              httpStatus: null,
              fetchError: renderException(e.cause),
              fetchRetries: nextPage.fetchRetries + 1,
              nextFetchTime: retryAgain
                ? new Date(
                    Temporal.Now.instant().add({
                      seconds: 4 * 2 ** nextPage.fetchRetries,
                    }).epochMilliseconds,
                  )
                : null,
            },
          });
        } else {
          throw e;
        }
      }
      await until(pageCrawlStart.add(await robots.crawlRate(crawlStartTime)));
    }
    await prisma.crawl.update({
      where: { date: crawl.date },
      data: { endTime: new Date(), state: "COMPLETE" },
    });
  } catch (e) {
    // Record the exception in the crawl row.
    crawl = await prisma.crawl.update({
      where: { date: crawl.date },
      data: { state: "ERROR", error: renderException(e) },
      include: {
        _count: { select: { pages: { where: { state: { not: "DONE" } } } } },
      },
    });
    debug(
      "The %s crawl stopped due to an error (%s): %d pages left",
      crawl.date,
      e instanceof Error ? e.message : String(e),
      crawl._count.pages,
    );
  }
}

/** True if the page should be considered "in" its crawl. */
function pagePresent(
  page: CrawledPageModel | CachedPageModel | null,
): page is (CrawledPageModel | CachedPageModel) & { httpStatus: number } {
  return page !== null && page.httpStatus != null && page.httpStatus < 400;
}

async function computeChange(
  crawl: CrawlModel,
  page: CachedPageModel,
): Promise<PageChange> {
  const prevCrawlDate = crawl.prevCrawlDate;
  if (prevCrawlDate === null) {
    return "NEW";
  }
  const oldPage = await prisma.crawledPage.findUnique({
    where: { crawlDate_urlId: { crawlDate: prevCrawlDate, urlId: page.urlId } },
  });
  if (pagePresent(oldPage)) {
    if (pagePresent(page)) {
      if (
        oldPage.httpStatus == page.httpStatus &&
        (oldPage.httpStatus % 100 != 3 || oldPage.location == page.location) &&
        oldPage.contentType == page.contentType &&
        oldPage.contentHash == page.contentHash
      ) {
        return "SAME";
      }
      return "CHANGED";
    } else {
      // New page absent.
      return "REMOVED";
    }
  } else {
    // Old page absent.
    if (pagePresent(page)) {
      return "NEW";
    } else {
      // New page absent.
      return "SAME";
    }
  }
}
