import { cn } from "@/utils/format";

/**
 * Content image with intrinsic dimensions (prevents layout shift).
 * `fill` positions the image to cover its relatively positioned parent.
 */
export function ContentImage({ image, fill = false, priority = false, className, sizes }) {
  return (
    <img
      src={image.src}
      alt={image.alt}
      width={image.width}
      height={image.height}
      sizes={sizes}
      loading={priority ? "eager" : "lazy"}
      decoding="async"
      fetchPriority={priority ? "high" : undefined}
      className={cn(fill && "absolute inset-0 h-full w-full", className)}
    />
  );
}
