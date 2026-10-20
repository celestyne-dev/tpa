import { describe, expect, it } from "vitest";
import { estimateReadingTime } from "@/lib/reading-time";
import { serializeJsonLd } from "@/lib/structured-data";
import { cn, formatDate, slugify } from "@/lib/utils";

describe("utils", () => {
  it("joins class names and skips falsy values", () => {
    expect(cn("a", false, undefined, "b")).toBe("a b");
  });

  it("formats dates in UTC", () => {
    expect(formatDate("2026-09-01T00:30:00.000Z")).toBe("September 1, 2026");
  });

  it("slugifies titles", () => {
    expect(slugify("Confidence & Self-Worth")).toBe("confidence-and-self-worth");
    expect(slugify("  Café Déjà Vu!  ")).toBe("cafe-deja-vu");
  });

  it("estimates reading time with a one-minute minimum", () => {
    expect(estimateReadingTime([{ type: "paragraph", text: "Hello" }])).toBe(1);
    const long = Array.from({ length: 900 }, () => "word").join(" ");
    expect(estimateReadingTime([{ type: "paragraph", text: long }])).toBe(4);
  });

  it("escapes < in JSON-LD output", () => {
    expect(serializeJsonLd({ a: "</script>" })).not.toContain("</script>");
  });
});
