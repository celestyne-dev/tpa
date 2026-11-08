import { Link } from "react-router";
import { routes } from "@/config/navigation";
import { cn } from "@/utils/format";
import { TopicIcon } from "./TopicIcon";

/**
 * Topic links as a wrap of pills: "Explore topics" beside articles, under topic pages,
 * in search and in the article sidebar. Topics come from the API (never hardcoded);
 * `current` marks the topic being viewed.
 */
export function TopicLinks({ topics, current, label = "Topics", className, size = "md" }) {
  if (!topics?.length) return null;
  return (
    <ul aria-label={label} className={cn("flex flex-wrap gap-2", className)}>
      {topics.map((topic) => {
        const active = topic.slug === current;
        return (
          <li key={topic.slug}>
            <Link
              to={routes.topic(topic.slug)}
              aria-current={active ? "page" : undefined}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border font-medium transition-colors",
                size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-sm",
                active
                  ? "border-sage-700 bg-sage-700 text-ivory"
                  : "border-charcoal/15 bg-white/60 text-ink hover:border-sage-600 hover:text-sage-800",
              )}
            >
              <TopicIcon
                name={topic.icon}
                className={cn("size-4", active ? "text-ivory" : "text-sage-700")}
              />
              {topic.name}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
