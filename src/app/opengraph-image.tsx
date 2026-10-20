import { renderOgImage, ogSize } from "./og-template";

export const alt = "Think Positive Always — A Better Mindset. A Brighter Life.";
export const size = ogSize;
export const contentType = "image/png";

export default function Image() {
  return renderOgImage({
    eyebrow: "Mindset · Growth · Confidence",
    title: "A Better Mindset. A Brighter Life.",
  });
}
