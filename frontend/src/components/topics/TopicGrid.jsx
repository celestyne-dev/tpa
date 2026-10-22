import { cn } from "@/utils/format";
import { TopicCard } from "./TopicCard";

export function TopicGrid({ topics, className }) {
  return (
    <ul className={cn("grid gap-6 sm:grid-cols-2 lg:grid-cols-3", className)}>
      {topics.map((topic) => (
        <li key={topic.slug}>
          <TopicCard topic={topic} />
        </li>
      ))}
    </ul>
  );
}
