import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { routes } from "@/config/navigation";
import { Card } from "@/components/ui/card";
import type { Topic } from "@/types";
import { TopicIcon } from "./topic-icon";

export function TopicCard({ topic }: { topic: Topic }) {
  return (
    <Card interactive className="group flex h-full flex-col p-7">
      <span className="grid size-14 place-items-center rounded-2xl bg-sage-100 text-sage-700 transition-colors group-hover:bg-sage-700 group-hover:text-ivory">
        <TopicIcon name={topic.icon} className="size-6" />
      </span>
      <h3 className="mt-6 text-2xl font-medium">
        <Link
          href={routes.topic(topic.slug)}
          className="after:absolute after:inset-0 after:rounded-[var(--radius-card)] focus-visible:outline-none focus-visible:after:outline-3 focus-visible:after:outline-offset-2 focus-visible:after:outline-sage-600"
        >
          {topic.name}
        </Link>
      </h3>
      <p className="mt-3 flex-1 text-muted">{topic.description}</p>
      <span
        aria-hidden
        className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-sage-700"
      >
        Explore topic
        <ArrowRight className="size-4 transition-transform group-hover:translate-x-1 motion-reduce:group-hover:translate-x-0" />
      </span>
    </Card>
  );
}
