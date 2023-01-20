-- CreateTable
CREATE TABLE "Subscription" (
    "email" TEXT NOT NULL PRIMARY KEY,
    "subscribedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateIndex
CREATE UNIQUE INDEX "Subscription_email_key" ON "Subscription"("email");
