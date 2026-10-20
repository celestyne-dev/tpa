import { Section } from "@/components/ui/section";
import { SectionHeading } from "@/components/ui/section-heading";
import { TopicCard } from "@/components/topics/topic-card";
import type { Topic } from "@/types";

export function TopicsSection({ topics }: { topics: Topic[] }) {
  return (
    <Section aria-labelledby="topics-heading">
      <SectionHeading
        id="topics-heading"
        eyebrow="Explore by topic"
        title="Explore What Matters to You"
        description="Find encouragement and practical guidance for the part of life you are working on right now."
      />
      <ul className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {topics.map((topic) => (
          <li key={topic.slug}>
            <TopicCard topic={topic} />
          </li>
        ))}
      </ul>
    </Section>
  );
}
