import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/** WCAG relative-luminance contrast ratio between two #rrggbb colours. */
function contrast(a, b) {
  const lum = (hex) => {
    const [r, g, b2] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    const ch = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b2);
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const css = readFileSync(path.resolve(__dirname, "../../assets/styles/globals.css"), "utf8");

function tokens(block) {
  return Object.fromEntries(
    [...block.matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]),
  );
}

const base = tokens(css.slice(css.indexOf("@theme"), css.indexOf("}", css.indexOf("@theme"))));
const palettes = { classic: base };
for (const name of ["evergreen", "golden_hour"]) {
  const start = css.indexOf(`[data-palette="${name}"]`);
  palettes[name] = { ...base, ...tokens(css.slice(start, css.indexOf("}", start))) };
}

describe("approved brand palettes", () => {
  for (const [name, c] of Object.entries(palettes)) {
    it(`${name} keeps WCAG AA contrast for text and buttons`, () => {
      expect(contrast(c["sage-700"], c.ivory)).toBeGreaterThanOrEqual(4.5); // eyebrow/links on ivory
      expect(contrast(c["sage-700"], c.cream)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.ivory, c["sage-700"])).toBeGreaterThanOrEqual(4.5); // primary buttons
      expect(contrast(c.ivory, c["sage-800"])).toBeGreaterThanOrEqual(4.5); // deep sage sections
      expect(contrast(c["gold-300"], c.charcoal)).toBeGreaterThanOrEqual(4.5); // dark eyebrows
      expect(contrast(c.muted, c.cream)).toBeGreaterThanOrEqual(4.5); // body text on cream
      expect(contrast(c.charcoal, c["gold-100"])).toBeGreaterThanOrEqual(4.5); // gold announcement
    });
  }
});
