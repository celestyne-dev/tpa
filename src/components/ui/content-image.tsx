import Image, { type ImageProps } from "next/image";
import type { ImageAsset } from "@/types";

type ContentImageProps = Omit<ImageProps, "src" | "alt" | "width" | "height"> & {
  image: ImageAsset;
  fill?: boolean;
};

/**
 * Wraps next/image for content assets. Vector artwork (SVG) is served as-is;
 * raster images (e.g. migrated featured images) go through the optimiser.
 */
export function ContentImage({ image, fill, ...props }: ContentImageProps) {
  const unoptimized = image.src.endsWith(".svg");
  return fill ? (
    <Image src={image.src} alt={image.alt} fill unoptimized={unoptimized} {...props} />
  ) : (
    <Image
      src={image.src}
      alt={image.alt}
      width={image.width}
      height={image.height}
      unoptimized={unoptimized}
      {...props}
    />
  );
}
