import { TopicGrid } from "@/components/topics/TopicGrid";
import { ErrorState } from "@/components/ui/ErrorState";
import { Section } from "@/components/ui/Section";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { CardGridSkeleton } from "@/components/ui/Skeleton";
import { useTopics } from "@/hooks/useContent";

export function TopicsSection() {
  const { data: topics, isLoading, isError, retry } = useTopics();
  return (
    <Section aria-labelledby="topics-heading">
      <SectionHeading
        id="topics-heading"
        eyebrow="Explore by topic"
        title="Explore What Matters to You"
        description="Find encouragement and practical guidance for the part of life you are working on right now."
      />
      <div className="mt-12">
        {isLoading && <CardGridSkeleton count={6} />}
        {isError && <ErrorState onRetry={retry} title="We couldn't load the topics" />}
        {topics && <TopicGrid topics={topics.filter((t) => t.featured)} />}
      </div>
    </Section>
  );
}
