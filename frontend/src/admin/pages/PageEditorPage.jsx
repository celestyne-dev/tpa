import { useCallback } from "react";
import { Navigate, useParams } from "react-router";
import { useAdminApi } from "../adminApiContext";
import { PageBuilder } from "../components/builder/PageBuilder";

/** Admin › Pages › page: the same builder as the homepage, for any CMS page. */
export function PageEditorPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const load = useCallback(async () => {
    const res = await api.pages.get(id);
    return res;
  }, [api, id]);
  if (!/^\d+$/.test(id)) return <Navigate to="/admin/pages" replace />;
  return <PageBuilder key={id} load={load} isHome={false} />;
}
