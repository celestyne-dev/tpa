import { useCallback, useEffect, useState } from "react";

/**
 * Reading preferences: font size, line spacing, reading width and theme.
 *
 * Sizes are relative (rem), so the reader follows the browser's font settings and zoom
 * instead of overriding them. Themes recolour the reader by redefining the design tokens
 * inside it; every pairing keeps WCAG AA contrast (see readerPrefs.test.js).
 */
export const READER_DEFAULTS = {
  font_size: "medium",
  line_spacing: "standard",
  width: "standard",
  theme: "light",
};

export const READER_OPTIONS = {
  font_size: [
    ["small", "Small"],
    ["medium", "Medium"],
    ["large", "Large"],
  ],
  line_spacing: [
    ["standard", "Standard"],
    ["comfortable", "Comfortable"],
  ],
  width: [
    ["standard", "Standard"],
    ["wide", "Wide"],
  ],
  theme: [
    ["light", "Light"],
    ["warm", "Warm paper"],
    ["dark", "Dark"],
  ],
};

export const READER_LABELS = {
  font_size: "Text size",
  line_spacing: "Line spacing",
  width: "Reading width",
  theme: "Theme",
};

const SIZES = { small: "1rem", medium: "1.125rem", large: "1.3125rem" };
const LEADING = { standard: "1.75", comfortable: "2.05" };
const WIDTHS = { standard: "68ch", wide: "84ch" };

/** Token overrides per theme (light uses the site's own palette). */
export const READER_THEMES = {
  light: {
    "--color-white": "#ffffff",
    "--color-ivory": "#faf6ee",
    "--color-ink": "#34312c",
    "--color-muted": "#5e584e",
  },
  warm: {
    "--color-white": "#fbf4e6",
    "--color-ivory": "#f3e9d4",
    "--color-cream": "#ecdfc4",
    "--color-charcoal": "#2a2219",
    "--color-ink": "#382d22",
    "--color-muted": "#5c4f40",
    "--color-sage-50": "#e8e6cf",
  },
  dark: {
    "--color-white": "#262421",
    "--color-ivory": "#1b1a18",
    "--color-cream": "#2b2925",
    "--color-beige": "#34312c",
    "--color-charcoal": "#f2ede3",
    "--color-ink": "#e6e0d4",
    "--color-muted": "#c3bba9",
    "--color-sage-50": "#232c24",
    "--color-sage-100": "#2c382c",
    "--color-sage-600": "#9dbb8d",
    "--color-sage-700": "#b2cca4",
    "--color-sage-800": "#c9dcbd",
    "--color-gold-100": "#3a3122",
    "--color-gold-300": "#8f7645",
    "--color-gold-400": "#b8964f",
    "--color-gold-700": "#e7cb8f",
    "--color-red-800": "#ffb4a8",
  },
};

export function readerStyle(prefs) {
  const p = { ...READER_DEFAULTS, ...prefs };
  return {
    ...READER_THEMES[p.theme],
    "--reader-size": SIZES[p.font_size],
    "--reader-leading": LEADING[p.line_spacing],
    "--reader-width": WIDTHS[p.width],
  };
}

const STORAGE_KEY = "tpa-reader-preferences";

function stored() {
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

function clean(value) {
  const out = {};
  for (const [key, options] of Object.entries(READER_OPTIONS)) {
    if (options.some(([v]) => v === value?.[key])) out[key] = value[key];
  }
  return out;
}

/**
 * Preferences for this reader: remembered on the device for instant rendering and, for
 * signed-in learners, saved to their account so they follow them between sessions.
 */
export function useReadingPreferences(shopApi, signedIn) {
  const [prefs, setPrefs] = useState(() => ({ ...READER_DEFAULTS, ...clean(stored()) }));
  const [status, setStatus] = useState("");
  useEffect(() => {
    if (!signedIn || !shopApi?.readingPreferences) return undefined;
    let live = true;
    shopApi.readingPreferences().then(
      (res) => live && setPrefs((p) => ({ ...p, ...clean(res.data) })),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [shopApi, signedIn]);
  const update = useCallback(
    (patch) => {
      setPrefs((p) => {
        const next = { ...p, ...clean(patch) };
        try {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          // Private browsing: kept for this visit only.
        }
        return next;
      });
      if (signedIn && shopApi?.saveReadingPreferences) {
        setStatus("Saving…");
        shopApi.saveReadingPreferences(clean(patch)).then(
          () => setStatus("Saved to your account"),
          () => setStatus("Couldn't save to your account; kept on this device"),
        );
      }
    },
    [shopApi, signedIn],
  );
  return [prefs, update, status];
}
