import { ArrowLeft, EyeOff } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdminApi } from "../adminApiContext";
import { PreviewShell } from "../components/builder/PreviewShell";
import { useAdminQuery } from "../hooks/useAdminQuery";

/** Private, non-indexed preview of a page's saved draft (opens in a new tab). */
export function PagePreviewPage() {
  const { id } = useParams();
  const api = useAdminApi();
  const navigate = useNavigate();
  const { data, error, reload } = useAdminQuery(() => api.pages.preview(id), [id]);
  return (
    <>
      <div
        role="note"
        className="sticky top-0 z-50 flex flex-wrap items-center justify-between gap-3 bg-charcoal px-5 py-2.5 text-sm text-ivory"
      >
        <span className="inline-flex items-center gap-2">
          <EyeOff aria-hidden className="size-4 text-gold-300" />
          Private preview of the saved draft. It is not on the website and is never indexed.
        </span>
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1 underline underline-offset-4"
        >
          <ArrowLeft aria-hidden className="size-4" />
          Back to the editor
        </button>
      </div>
      {error && <ErrorState title="We couldn't load this preview" onRetry={reload} />}
      {!data && !error && <Skeleton className="m-8 h-96" />}
      {data && <PreviewShell page={data.page} />}
    </>
  );
}
