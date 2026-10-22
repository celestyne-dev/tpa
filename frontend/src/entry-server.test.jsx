import { describe, expect, it } from "vitest";
import { render } from "@/entry-server";
import { ApiError } from "@/services/apiClient";
import { createFakeApi } from "@/test/utils";

describe("prerender (entry-server)", () => {
  it("renders crawlable article HTML with head tags and state", async () => {
    const result = await render("/articles/reframing-negative-thoughts", createFakeApi());
    expect(result.status).toBe(200);
    expect(result.html).toContain("How to Reframe a Negative Thought</h1>");
    expect(result.html).toContain("Notice the thought first");
    expect(result.head).toContain(
      "<title>How to Reframe a Negative Thought | Think Positive Always</title>",
    );
    expect(result.head).toMatch(/<meta data-seo name="description" content="Realistic optimism/);
    expect(result.head).toMatch(
      /<link data-seo rel="canonical" href="[^"]+\/articles\/reframing-negative-thoughts"/,
    );
    expect(result.head).toContain('"@type":"Article"');
    expect(result.state.articles.bySlug["reframing-negative-thoughts"].status).toBe("succeeded");
  });

  it("renders topic pages and the homepage with content", async () => {
    const topic = await render("/topics/positive-mindset", createFakeApi());
    expect(topic.html).toContain("Designing an Intentional Morning");
    const home = await render("/", createFakeApi());
    expect(home.html).toContain("Explore What Matters to You");
    expect(home.html).toContain("Know Your Worth");
  });

  it("reports 404 for unknown routes and slugs", async () => {
    expect((await render("/nope", createFakeApi())).status).toBe(404);
    expect((await render("/articles/missing", createFakeApi())).status).toBe(404);
    expect((await render("/topics/missing", createFakeApi())).status).toBe(404);
  });

  it("fails loudly when the API errors (never ships empty pages)", async () => {
    const api = createFakeApi({
      getProducts: async () => {
        throw new ApiError({ status: 500, code: "internal_error", message: "boom" });
      },
    });
    await expect(render("/shop", api)).rejects.toThrow(/API request failed/);
  });
});
