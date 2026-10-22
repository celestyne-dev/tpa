import {
  CalendarCheck,
  Flame,
  Gem,
  HeartHandshake,
  Leaf,
  Sprout,
  Sun,
  Sunrise,
} from "lucide-react";

const icons = {
  sun: Sun,
  sprout: Sprout,
  gem: Gem,
  sunrise: Sunrise,
  "heart-handshake": HeartHandshake,
  "calendar-check": CalendarCheck,
  flame: Flame,
  leaf: Leaf,
};

export function TopicIcon({ name, className }) {
  const Icon = icons[name] ?? Sun;
  return <Icon aria-hidden className={className} />;
}
