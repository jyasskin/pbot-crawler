/*
  Warnings:

  - Added the required column `unsubscribeSecret` to the `Subscription` table without a default value. This is not possible if the table is not empty.

*/
-- CreateTable
CREATE TABLE "CrawlState" (
    "crawl_date" TEXT NOT NULL PRIMARY KEY,
    "state" TEXT NOT NULL
);

-- RedefineTables
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_Subscription" (
    "email" TEXT NOT NULL PRIMARY KEY,
    "name" TEXT,
    "subscribedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "unsubscribeSecret" TEXT NOT NULL
);
INSERT INTO "new_Subscription" ("email", "subscribedAt") SELECT "email", "subscribedAt" FROM "Subscription";
DROP TABLE "Subscription";
ALTER TABLE "new_Subscription" RENAME TO "Subscription";
CREATE UNIQUE INDEX "Subscription_email_key" ON "Subscription"("email");
PRAGMA foreign_key_check;
PRAGMA foreign_keys=ON;

-- CreateIndex
CREATE UNIQUE INDEX "CrawlState_crawl_date_key" ON "CrawlState"("crawl_date");
