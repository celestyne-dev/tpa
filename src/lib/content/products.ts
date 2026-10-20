import { products as localProducts } from "@/data/products";
import type { ProductPreview } from "@/types";

/** Product preview repository; replaced by the real catalog in Batch 04. */
export async function getProductPreviews(): Promise<ProductPreview[]> {
  return localProducts;
}
