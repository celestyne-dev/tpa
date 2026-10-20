export interface NavItem {
  label: string;
  href: string;
  description?: string;
}

export interface NavGroup {
  title: string;
  items: NavItem[];
}

export type SocialPlatform =
  "linkedin" | "instagram" | "facebook" | "x" | "youtube" | "tiktok" | "pinterest";

export interface SocialLink {
  platform: SocialPlatform;
  label: string;
  url: string;
}
