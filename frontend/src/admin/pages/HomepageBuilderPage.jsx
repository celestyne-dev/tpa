import { useCallback } from "react";
import { useAdminApi } from "../adminApiContext";
import { PageBuilder } from "../components/builder/PageBuilder";

/** Admin › Homepage: the homepage's sections, drafts, preview and publishing. */
export function HomepageBuilderPage() {
  const api = useAdminApi();
  const load = useCallback(() => api.pages.homepage(), [api]);
  return <PageBuilder load={load} isHome />;
}
