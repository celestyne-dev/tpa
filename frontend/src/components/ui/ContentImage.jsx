import { ImageOff } from "lucide-react";
import { useState } from "react";
import { cn } from "@/utils/format";
import { IMAGE_SIZES } from "./imageSizes";

export { IMAGE_SIZES };

/**
 * Responsive, layout-stable image.
 *
 * Optimised uploads render a <picture> with AVIF/WebP sources and a JPEG/PNG
 * fallback srcset; built-in images render a plain <img>. Intrinsic width and
 * height are always set (no layout shift). `priority` is for the main (LCP)
 * image: eager loading and high fetch priority; everything else lazy-loads.
 * `fill` covers a positioned parent, cropped around the image's focal point.
 */
export function ContentImage({
  image,
  fill = false,
  priority = false,
  className,
  sizes = IMAGE_SIZES.body,
}) {
  const [failed, setFailed] = useState(false);
  if (!image?.src || failed) {
    return (
      <span
        role="img"
        aria-label={image?.alt || "Image unavailable"}
        className={cn(
          "flex items-center justify-center bg-beige text-muted",
          fill ? "absolute inset-0" : "aspect-[16/10] w-full",
          className,
        )}
      >
        <ImageOff aria-hidden className="size-8 opacity-60" />
      </span>
    );
  }
  const style = {};
  if (image.placeholder) style.backgroundColor = image.placeholder;
  if (fill && image.focal)
    style.objectPosition = `${image.focal[0] * 100}% ${image.focal[1] * 100}%`;
  const img = (
    <img
      src={image.src}
      srcSet={image.srcset || undefined}
      sizes={image.srcset ? sizes : undefined}
      alt={image.alt ?? ""}
      width={image.width}
      height={image.height}
      loading={priority ? "eager" : "lazy"}
      decoding={priority ? "auto" : "async"}
      fetchPriority={priority ? "high" : undefined}
      onError={() => setFailed(true)}
      style={Object.keys(style).length ? style : undefined}
      className={cn(fill && "absolute inset-0 h-full w-full", className)}
    />
  );
  const sources = Object.entries(image.sources ?? {}).filter(([, srcset]) => srcset);
  if (!sources.length) return img;
  // AVIF first: browsers take the first type they support.
  sources.sort(([a]) => (a === "image/avif" ? -1 : 1));
  return (
    <picture className={fill ? "contents" : undefined}>
      {sources.map(([type, srcset]) => (
        <source key={type} type={type} srcSet={srcset} sizes={sizes} />
      ))}
      {img}
    </picture>
  );
}
