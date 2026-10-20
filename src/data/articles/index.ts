import type { Article } from "@/types";
import { boundariesWithoutGuilt } from "./boundaries-without-guilt";
import { growthThroughReflection } from "./growth-through-reflection";
import { intentionalMornings } from "./intentional-mornings";
import { quietConfidence } from "./quiet-confidence";
import { reframingNegativeThoughts } from "./reframing-negative-thoughts";
import { smallStepsAfterAHardSeason } from "./small-steps-after-a-hard-season";

/**
 * Local article store. Sample articles are marked `source: "sample"` and are
 * labelled in the UI. Migrated articles (future batch) should use
 * `source: "migrated"` with `legacy` metadata populated.
 */
export const articles: Article[] = [
  smallStepsAfterAHardSeason,
  reframingNegativeThoughts,
  quietConfidence,
  boundariesWithoutGuilt,
  intentionalMornings,
  growthThroughReflection,
];
