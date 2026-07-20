import robotsParser, { type Robot } from "robots-parser";
import { USER_AGENT } from "./crawl_config";
import { debug } from "./debug";
import { fetchWithDistinctiveExceptions, renderException } from "./util";

export class Robots {
  constructor(origin: URL) {
    this.robotsUrl = new URL("robots.txt", origin.origin);
    // Very old so the next use will fetch robots.txt.
    this.fetchedAt = Temporal.Instant.fromEpochMilliseconds(0);
    this.robotsParser = null;
  }

  async canFetch(url: string, oldestFresh: Temporal.Instant): Promise<boolean> {
    if (Temporal.Instant.compare(this.fetchedAt, oldestFresh) < 0) {
      await this.updateRobotContent();
    }
    return (
      this.robotsParser == null ||
      this.robotsParser.isAllowed(url, USER_AGENT) == true
    );
  }

  async crawlRate(oldestFresh: Temporal.Instant): Promise<Temporal.Duration> {
    if (Temporal.Instant.compare(this.fetchedAt, oldestFresh) < 0) {
      await this.updateRobotContent();
    }
    const crawlDelay = this.robotsParser?.getCrawlDelay(USER_AGENT);
    return Temporal.Duration.from({ seconds: crawlDelay ?? 1 });
  }

  private robotsUrl: URL;
  private fetchedAt: Temporal.Instant;
  private robotsParser: Robot | null;

  private async updateRobotContent() {
    try {
      const robotsResponse = await fetchWithDistinctiveExceptions(
        this.robotsUrl,
        {
          redirect: "follow",
        },
      );
      this.fetchedAt = Temporal.Now.instant();
      if (robotsResponse.status < 300) {
        this.robotsParser = robotsParser(
          this.robotsUrl.href,
          await robotsResponse.text(),
        );
      } else {
        this.robotsParser = null;
      }
    } catch (e) {
      debug("Robots update failed: %s", renderException(e));
      throw e;
    }
  }
}
