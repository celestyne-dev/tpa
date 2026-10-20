import { env } from "@/lib/env";
import type { SocialLink, SocialPlatform } from "@/types";

const labels: Record<SocialPlatform, string> = {
  linkedin: "LinkedIn",
  instagram: "Instagram",
  facebook: "Facebook",
  x: "X",
  youtube: "YouTube",
  tiktok: "TikTok",
  pinterest: "Pinterest",
};

/**
 * Social links come from environment configuration. Platforms without a
 * verified URL are omitted entirely (no "#" placeholders).
 */
export const socialLinks: SocialLink[] = (Object.keys(labels) as SocialPlatform[]).flatMap(
  (platform) => {
    const url = env.social[platform];
    return url ? [{ platform, label: labels[platform], url }] : [];
  },
);
