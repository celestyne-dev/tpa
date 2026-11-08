import { useCallback } from "react";
import { useAdminApi } from "../adminApiContext";
import { PageBuilder } from "../components/builder/PageBuilder";

/**
 * Admin › Article sidebar: the sections beside every article (Popular articles, Related
 * articles, The Positive Reset, Editor's Picks, Explore topics, live sponsored bookings).
 * Uses the homepage permissions; the sidebar has no address of its own.
 */
export function ArticleSidebarBuilderPage() {
  const api = useAdminApi();
  const load = useCallback(() => api.pages.articleSidebar(), [api]);
  return <PageBuilder load={load} isSidebar />;
}
