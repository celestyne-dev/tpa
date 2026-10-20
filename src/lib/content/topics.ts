import { topics as localTopics } from "@/data/topics";
import type { Topic } from "@/types";

export async function getTopics(): Promise<Topic[]> {
  return localTopics;
}

export async function getFeaturedTopics(): Promise<Topic[]> {
  return localTopics.filter((t) => t.featured);
}

export async function getTopicBySlug(slug: string): Promise<Topic | null> {
  return localTopics.find((t) => t.slug === slug) ?? null;
}

/** Synchronous lookup map for rendering topic labels on cards. */
export const topicMap: ReadonlyMap<string, Topic> = new Map(localTopics.map((t) => [t.slug, t]));
