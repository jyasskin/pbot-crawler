import { prisma } from "@lib/prisma";
import nock from "nock";
import "temporal-polyfill/global";
import { afterEach, beforeEach } from "vitest";

afterEach(async () => {
  await prisma.knownUrl.deleteMany();
  await prisma.contentStore.deleteMany();
  await prisma.crawl.deleteMany();
});

beforeEach(async () => {
  nock("https://www.portland.gov")
    .get("/robots.txt")
    .reply(
      200,
      `User-agent: *
Disallow: /core/
Disallow: /profiles/
Disallow: /README.md
Disallow: /*/search/
Disallow: /*/search?

Disallow: /*?f[*
Disallow: /*?f%5B*
Disallow: /*&f[*
Disallow: /*&f%5B*
Disallow: /*&format=rss*
Disallow: /*/rss?*
`,
    )
    .persist();

  return async () => {
    nock.cleanAll();
  };
});
