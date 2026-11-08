import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router";
import { useAdminApi } from "../adminApiContext";
import { PreviewShell } from "../components/builder/PreviewShell";

/**
 * Rendered inside the builder's preview iframe (same origin, admin session required).
 * Only the newest update is shown (a slow, older response never replaces a newer one),
 * and a failed update says so instead of silently leaving an out-of-date preview.
 */
export function PreviewFramePage() {
  const { id } = useParams();
  const api = useAdminApi();
  const [page, setPage] = useState(null);
  const [failed, setFailed] = useState(false);
  const [stale, setStale] = useState("");
  const latest = useRef(0);

  useEffect(() => {
    let cancelled = false;
    api.pages
      .preview(id)
      .then((res) => !cancelled && setPage(res.data.page))
      .catch(() => !cancelled && setFailed(true));
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "tpa-preview-update") return;
      const request = (latest.current += 1);
      const current = () => !cancelled && request === latest.current;
      api.pages
        .preview(id, event.data.payload)
        .then((res) => {
          if (!current()) return;
          setPage(res.data.page);
          setStale("");
        })
        .catch((err) => {
          if (!current()) return;
          setStale(
            err?.status === 400
              ? "The preview can't show the latest edits yet. Save the draft to see which fields need fixing."
              : "The preview couldn't update. Your edits are still in the editor.",
          );
        });
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
  return (
    <>
      {stale && (
        <p role="status" className="bg-gold-100 px-5 py-2 text-center text-sm text-charcoal">
          {stale}
        </p>
      )}
      <PreviewShell page={page} />
    </>
  );
}
