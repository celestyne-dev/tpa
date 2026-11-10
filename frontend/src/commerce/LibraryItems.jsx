import { Download, FileText, GraduationCap } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { ProductCover } from "@/components/products/ProductCover";
import { Button } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { redirectTo } from "./hooks";

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
    : "";

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

const STARTED =
  "Your download should start in a moment. If it doesn't start or stops partway, press Download again: trying again within an hour doesn't use another download.";

/** Short titles for refused downloads, so a used-up allowance is never mistaken for an
 * expired link (the server's message follows). */
const PROBLEMS = {
  download_limit_reached: "Download limit reached",
  download_link_expired: "The download link expired",
  download_link_used_up: "The download link was used up",
  download_file_unavailable: "File temporarily unavailable",
  not_entitled: "No access",
  network_error: "No connection",
};

/**
 * Library items with their download buttons. ``authorize(item, version)`` asks the
 * server for a short-lived download link (account session, guest order token or guest
 * access link) and resolves to the API response; the browser then follows the link.
 * Course purchases link to the course; ``learner`` is true in the signed-in account (guests
 * are told how to start learning with the purchase email).
 */
export function LibraryItems({ items, authorize, headingLevel = 2, learner = false }) {
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);
  const Heading = `h${headingLevel}`;
  const download = async (item, version) => {
    setBusy(version.version_id);
    setMessage(null);
    try {
      const res = await authorize(item, version);
      redirectTo.go(res.data.url);
      setMessage({ id: item.id, ok: true, text: STARTED });
    } catch (err) {
      setMessage({
        id: item.id,
        title: PROBLEMS[err.code] ?? "The download could not start",
        text: err.message,
        contact: err.code === "download_limit_reached" || err.code === "download_file_unavailable",
      });
    } finally {
      setBusy(null);
    }
  };
  return (
    <ul className="space-y-5">
      {items.map((item) => (
        <li
          key={item.id}
          className="flex flex-col gap-5 rounded-2xl border border-charcoal/10 bg-white p-5 sm:flex-row sm:p-6"
        >
          <div className="w-24 shrink-0">
            <ProductCover product={{ ...item.product, format: "" }} className="shadow-none" />
          </div>
          <div className="min-w-0 flex-1">
            <Heading className="text-xl font-medium">
              {item.product.slug ? (
                <Link to={routes.product(item.product.slug)} className="hover:underline">
                  {item.product.title}
                </Link>
              ) : (
                item.product.title
              )}
            </Heading>
            <p className="mt-1 text-sm text-muted">
              {item.source === "free"
                ? "Free resource"
                : item.source === "bundle"
                  ? "Included in a bundle"
                  : item.source === "manual"
                    ? "Added by our team"
                    : `Order ${item.order_number}`}
              {" · "}added {formatDate(item.granted_at)}
              {item.download_limit
                ? ` · ${item.download_count}/${item.download_limit} downloads used`
                : ""}
            </p>
            {item.product.course && item.status === "active" && (
              <div className="mt-3 rounded-xl bg-sage-50 p-4 text-sm">
                {learner ? (
                  <Link
                    to={routes.learn(item.product.course.slug)}
                    className="inline-flex items-center gap-1.5 font-medium text-sage-800 underline underline-offset-4"
                  >
                    <GraduationCap aria-hidden className="size-4" /> Open the course
                  </Link>
                ) : (
                  <p>
                    <span className="font-medium">To start “{item.product.course.title}”:</span>{" "}
                    sign in or create an account with the email address you used for this purchase
                    and confirm it. The course then appears in{" "}
                    <Link to={routes.accountLearning} className="underline underline-offset-4">
                      My learning
                    </Link>
                    .
                  </p>
                )}
              </div>
            )}
            {item.status === "revoked" ? (
              <p className="mt-3 text-sm text-red-800">
                Access ended{item.revoked_reason ? `: ${item.revoked_reason}` : ""}.
              </p>
            ) : item.includes.length > 0 ? (
              <p className="mt-3 text-sm">
                Includes: {item.includes.join(", ")} (listed separately).
              </p>
            ) : item.files.length === 0 ? (
              item.product.course ? null : (
                <p className="mt-3 text-sm text-muted">
                  Files are being prepared. Please check back soon.
                </p>
              )
            ) : (
              <ul className="mt-4 space-y-3">
                {item.files.map((file) => (
                  <li key={file.file_id} className="rounded-xl bg-cream/60 p-4">
                    <p className="flex items-center gap-2 font-medium">
                      <FileText aria-hidden className="size-4 text-sage-700" /> {file.title}
                    </p>
                    {file.description && (
                      <p className="mt-1 text-sm text-muted">{file.description}</p>
                    )}
                    <div className="mt-3 flex flex-wrap gap-2">
                      {file.versions.map((version) => (
                        <Button
                          key={version.version_id}
                          size="sm"
                          variant={version.kind === "latest" ? "primary" : "outline"}
                          disabled={busy === version.version_id}
                          onClick={() => download(item, version)}
                          aria-label={`Download ${file.title} ${version.kind === "latest" ? "latest version" : "version you received"} (${version.format})`}
                        >
                          <Download aria-hidden className="size-4" />
                          {version.kind === "latest" ? "Download" : "Your original edition"} ·{" "}
                          {version.format} · {formatSize(version.size_bytes)}
                        </Button>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {message?.id === item.id &&
              (message.ok ? (
                <p role="status" className="mt-3 text-sm text-sage-800">
                  {message.text}
                </p>
              ) : (
                <div role="alert" className="mt-3 text-sm text-red-800">
                  <p className="font-medium">{message.title}</p>
                  <p>
                    {message.text}
                    {message.contact && (
                      <>
                        {" "}
                        <Link to={routes.contact} className="underline underline-offset-4">
                          Contact us
                        </Link>
                      </>
                    )}
                  </p>
                </div>
              ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
