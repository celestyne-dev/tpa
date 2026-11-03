import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Read from the project root (tests run in frontend/): under jsdom, import.meta.url is not
// a file: URL, and Vitest stubs .css imports when CSS processing is off.
const css = readFileSync(resolve(process.cwd(), "src/assets/styles/globals.css"), "utf8");

/**
 * WCAG AA contrast for the colours used as text (4.5:1 for body text). Decorative,
 * aria-hidden icons (gold-500, sage-500, sage-600) are exempt and not listed here.
 */
const theme = css.slice(0, css.indexOf("}"));
const tokens = Object.fromEntries(
  [...theme.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]),
);
tokens.white = "#ffffff";

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const ratio = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

describe("text colour contrast (WCAG AA)", () => {
  const light = ["ivory", "cream", "white", "beige", "sage-50", "gold-100"];
  it.each(["charcoal", "ink", "muted", "sage-700", "sage-800", "gold-700"])(
    "text-%s reads at 4.5:1 or more on every light background",
    (text) => {
      for (const bg of light) expect(ratio(tokens[text], tokens[bg])).toBeGreaterThanOrEqual(4.5);
    },
  );
  it.each(["ivory", "sand", "gold-300", "sage-100"])(
    "text-%s reads at 4.5:1 or more on the dark footer and panels",
    (text) => {
      for (const bg of ["charcoal", "sage-800"])
        expect(ratio(tokens[text], tokens[bg])).toBeGreaterThanOrEqual(4.5);
    },
  );
});
