import { BigQuery, BigQueryDate } from '@google-cloud/bigquery';
import debugModule from 'debug';
import { Temporal } from 'temporal-polyfill';

const debug = debugModule('pbotcrawl:bigquery');
const bigqueryClient = new BigQuery();
const location = 'us-west1';
const UTC = new Temporal.TimeZone('UTC');

function toBQDate(date: Temporal.PlainDate) {
    return BigQuery.date(date);
}

function fromBQDate(date: BigQueryDate): Temporal.PlainDate {
    return Temporal.PlainDate.from(date.value);
}

export type CrawlDates = {
    current_crawl: Temporal.PlainDate
    prev_crawl: Temporal.PlainDate
}

export async function find_crawl_dates(current_crawl?: Temporal.PlainDate): Promise<CrawlDates | undefined> {
    const [results] = await
        bigqueryClient.query({
            location,
            query: `SELECT DISTINCT crawl
                FROM \`pbot-site-crawler.crawl.changed-pages\`
                WHERE @current_crawl IS NULL OR crawl <= @current_crawl
                ORDER BY crawl DESC
                LIMIT 2`,
            params: {
                current_crawl: current_crawl ? toBQDate(current_crawl) : null,
            },
            types: {
                current_crawl: 'DATE',
            }
        })
    if (results.length != 2) {
        debug(results);
        return undefined;
    }
    const crawl_dates = {
        current_crawl: fromBQDate(results[0]["crawl"]),
        prev_crawl: fromBQDate(results[1]["crawl"]),
    }
    if (current_crawl && !crawl_dates.current_crawl.equals(current_crawl)) {
        debug("%j", { current_crawl, crawl_dates });
        return undefined;
    }
    return crawl_dates
}

export type PagesResult = {
    pages: any[];
    more_available: boolean;
    total_rows: number;
}

export async function get_pages_with_change(options: {
    current_crawl: Temporal.PlainDate,
    change: "ADD" | "DEL" | "CHANGE",
    max_results?: number,
}): Promise<PagesResult> {
    const [job] = await bigqueryClient.createQueryJob({
        location,
        query: `
            SELECT page, diff
            FROM \`pbot-site-crawler.crawl.changed-pages\`
            WHERE crawl = @current_crawl AND change = @change
            ORDER BY page`,
        params: {
            current_crawl: toBQDate(options.current_crawl),
            change: options.change,
        },
    });

    const [results, _, metadata] = await job.getQueryResults({ maxResults: options.max_results });

    let more_available = false;
    const total_rows = parseInt(metadata?.totalRows!); // parseInt takes any type.
    if (options.max_results && options.max_results < total_rows) {
        more_available = true
    }
    return {
        pages: results,
        more_available,
        total_rows,
    };
}
