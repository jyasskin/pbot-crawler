-- CreateTable
CREATE TABLE "Crawl" (
    "date" TEXT NOT NULL PRIMARY KEY,
    "prevCrawlDate" TEXT,
    "startTime" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "endTime" DATETIME,
    "state" TEXT NOT NULL,
    "error" TEXT,
    CONSTRAINT "Crawl_prevCrawlDate_fkey" FOREIGN KEY ("prevCrawlDate") REFERENCES "Crawl" ("date") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "KnownUrl" (
    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "url" TEXT NOT NULL
);

-- CreateTable
CREATE TABLE "CachedPage" (
    "urlId" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    "fetchStart" DATETIME NOT NULL,
    "fetchEnd" DATETIME NOT NULL,
    "httpStatus" INTEGER NOT NULL,
    "excluded" TEXT,
    "eTag" TEXT,
    "lastModified" TEXT,
    "location" TEXT,
    "contentType" TEXT,
    "contentHash" BLOB,
    CONSTRAINT "CachedPage_urlId_fkey" FOREIGN KEY ("urlId") REFERENCES "KnownUrl" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "CachedPage_contentHash_fkey" FOREIGN KEY ("contentHash") REFERENCES "ContentStore" ("hash") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "CrawledPage" (
    "crawlDate" TEXT NOT NULL,
    "urlId" INTEGER NOT NULL,
    "state" TEXT NOT NULL DEFAULT 'TODO',
    "change" TEXT,
    "excluded" TEXT,
    "fetchStart" DATETIME,
    "fetchEnd" DATETIME,
    "fetchError" TEXT,
    "fetchRetries" INTEGER NOT NULL DEFAULT 0,
    "nextFetchTime" DATETIME,
    "httpStatus" INTEGER,
    "eTag" TEXT,
    "lastModified" TEXT,
    "location" TEXT,
    "contentType" TEXT,
    "contentHash" BLOB,

    PRIMARY KEY ("crawlDate", "urlId"),
    CONSTRAINT "CrawledPage_crawlDate_fkey" FOREIGN KEY ("crawlDate") REFERENCES "Crawl" ("date") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "CrawledPage_urlId_fkey" FOREIGN KEY ("urlId") REFERENCES "KnownUrl" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "CrawledPage_contentHash_fkey" FOREIGN KEY ("contentHash") REFERENCES "ContentStore" ("hash") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "ContentStore" (
    "hash" BLOB NOT NULL PRIMARY KEY,
    "content" TEXT NOT NULL,
    "latestRetrievedSize" INTEGER NOT NULL
);

-- CreateTable
CREATE TABLE "_ContentStoreToKnownUrl" (
    "A" BLOB NOT NULL,
    "B" INTEGER NOT NULL,
    CONSTRAINT "_ContentStoreToKnownUrl_A_fkey" FOREIGN KEY ("A") REFERENCES "ContentStore" ("hash") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "_ContentStoreToKnownUrl_B_fkey" FOREIGN KEY ("B") REFERENCES "KnownUrl" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "Crawl_date_key" ON "Crawl"("date");

-- CreateIndex
CREATE UNIQUE INDEX "Crawl_prevCrawlDate_key" ON "Crawl"("prevCrawlDate");

-- CreateIndex
CREATE UNIQUE INDEX "KnownUrl_url_key" ON "KnownUrl"("url");

-- CreateIndex
CREATE INDEX "CrawledPage_crawlDate_state_idx" ON "CrawledPage"("crawlDate", "state");

-- CreateIndex
CREATE UNIQUE INDEX "ContentStore_content_key" ON "ContentStore"("content");

-- CreateIndex
CREATE UNIQUE INDEX "_ContentStoreToKnownUrl_AB_unique" ON "_ContentStoreToKnownUrl"("A", "B");

-- CreateIndex
CREATE INDEX "_ContentStoreToKnownUrl_B_index" ON "_ContentStoreToKnownUrl"("B");
