import { describe, expect, it } from "vitest";
import { applyHead, buildHead, renderHeadToString } from "./head";

describe("head builder", () => {
  it("defaults to noindex unless indexing is explicitly enabled", () => {
    const head = buildHead({ title: "About", path: "/about" });
    expect(head.meta.find((m) => m.name === "robots").content).toBe("noindex, nofollow");
    expect(head.title).toBe("About | Think Positive Always");
    expect(head.links[0].href).toMatch(/\/about$/);
  });

  it("supports canonical overrides and article metadata", () => {
    const head = buildHead({
      title: "A",
      path: "/articles/a",
      canonicalUrl: "https://legacy.example/a",
      type: "article",
      article: { publishedTime: "2026-01-01", tags: ["x"], authors: ["TPA"] },
    });
    expect(head.links[0].href).toBe("https://legacy.example/a");
    expect(head.meta).toContainEqual({ property: "article:tag", content: "x" });
  });

  it("escapes values when serialising", () => {
    const html = renderHeadToString(
      buildHead({ title: 'Quotes "&" <tags>', jsonLd: { a: "</script>" } }),
    );
    expect(html).toContain(
      "<title>Quotes &quot;&amp;&quot; &lt;tags&gt; | Think Positive Always</title>",
    );
    expect(html).not.toContain("</script><");
  });

  it("replaces previous tags when applied on the client", () => {
    applyHead(buildHead({ title: "One" }));
    applyHead(buildHead({ title: "Two" }));
    expect(document.title).toBe("Two | Think Positive Always");
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1);
  });
});
