import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { useAdminApi } from "../adminApiContext";
import { PreviewShell } from "../components/builder/PreviewShell";

/** Rendered inside the builder's preview iframe (same origin, admin session required). */
export function PreviewFramePage() {
  const { id } = useParams();
  const api = useAdminApi();
  const [page, setPage] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.pages
      .preview(id)
      .then((res) => !cancelled && setPage(res.data.page))
      .catch(() => !cancelled && setFailed(true));
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "tpa-preview-update") return;
      api.pages
        .preview(id, event.data.payload)
        .then((res) => !cancelled && setPage(res.data.page))
        .catch(() => {});
    };
    window.addEventListener("message", onMessage);
    window.parent?.postMessage({ type: "tpa-preview-ready" }, window.location.origin);
    return () => {
      cancelled = true;
      window.removeEventListener("message", onMessage);
    };
  }, [api, id]);

  if (failed) return <p className="p-8 text-center text-muted">The preview could not be loaded.</p>;
  if (!page) return <p className="p-8 text-center text-muted">Loading preview…</p>;
  return <PreviewShell page={page} />;
}
