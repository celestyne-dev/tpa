import {
  CalendarCheck,
  Flame,
  Gem,
  HeartHandshake,
  Leaf,
  Sprout,
  Sun,
  Sunrise,
  type LucideIcon,
} from "lucide-react";
import type { TopicIconName } from "@/types";

const icons: Record<TopicIconName, LucideIcon> = {
  sun: Sun,
  sprout: Sprout,
  gem: Gem,
  sunrise: Sunrise,
  "heart-handshake": HeartHandshake,
  "calendar-check": CalendarCheck,
  flame: Flame,
  leaf: Leaf,
};

export function TopicIcon({ name, className }: { name: TopicIconName; className?: string }) {
  const Icon = icons[name];
  return <Icon aria-hidden className={className} />;
}
