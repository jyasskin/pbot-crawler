import type { ContentStoreUpsertArgs } from "@generated/prisma/models/ContentStore";
import type { KnownUrlCreateOrConnectWithoutLinkedFromInput } from "@generated/prisma/models/KnownUrl";
import { fromHtml } from "hast-util-from-html";
import { toMdast } from "hast-util-to-mdast";
import { gfmToMarkdown } from "mdast-util-gfm";
import { toMarkdown } from "mdast-util-to-markdown";
import { CONTINUE, visit } from "unist-util-visit";
import { sha256 } from "./util";

const contentToRemoveRE = new RegExp(
  [
    "(?:js-view-dom-id-|views_dom_id:)[0-9a-f]+",
    ',"view_dom_id":"[0-9a-f]+"',
    "<script .+?NREUM.+?</script>",
  ].join("|"),
  "g",
);

/// Removes bits of HTML that change on every fetch from PBOT's website.
export function cleanContent(content: string): string {
  content = content.replaceAll(contentToRemoveRE, "");
  content = content.replaceAll(/drawer--\d+/g, "drawer--0000000000");
  return content;
}

export function normalizeHtml(
  html: string,
  baseUrl: string | URL,
): Pick<ContentStoreUpsertArgs, "where" | "create" | "update"> {
  const latestRetrievedSize = html.length;
  html = cleanContent(html);
  const tree = fromHtml(html);
  const links: KnownUrlCreateOrConnectWithoutLinkedFromInput[] = [];
  visit(tree, "element", (node, _index, _parent) => {
    if (node.tagName === "a" && typeof node.properties.href === "string") {
      const target = URL.parse(node.properties.href, baseUrl);
      if (target === null) {
        // Ignore invalid URLs.
        return CONTINUE;
      }
      cleanUrlInPlace(target);
      links.push({ where: { url: target.href }, create: { url: target.href } });
    }
    return CONTINUE;
  });
  const content = toMarkdown(toMdast(tree), {
    listItemIndent: "tab",
    extensions: [gfmToMarkdown()],
  });
  const hash = sha256(content);
  return {
    where: { hash },
    create: {
      hash,
      content,
      latestRetrievedSize,
      links: { connectOrCreate: links },
    },
    update: { latestRetrievedSize, links: { connectOrCreate: links } },
  };
}

/// Removes query parameters that don't affect the resulting page.
export function cleanUrlInPlace(url: URL) {
  url.hash = "";
  url.searchParams.delete("utm_medium");
  url.searchParams.delete("utm_source");
  url.searchParams.delete("_ga");
  url.searchParams.delete("_gl");
}
