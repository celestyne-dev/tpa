import { CircleAlert, CircleCheck, UploadCloud } from "lucide-react";
import { useId, useRef, useState } from "react";
import { cn, formatBytes } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";

const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"];
const DEFAULT_MAX_MB = 20;
const CONCURRENCY = 2;

/**
 * Drag-and-drop / multi-file uploader with per-file progress. Files are checked
 * locally for type and size first (the server re-validates the real content).
 */
export function MediaUploader({
  onUploaded,
  maxMb = DEFAULT_MAX_MB,
  compact = false,
  fields = {},
}) {
  const api = useAdminApi();
  const inputId = useId();
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [queue, setQueue] = useState([]); // {key, name, size, progress, status, error}

  const patch = (key, values) =>
    setQueue((items) => items.map((i) => (i.key === key ? { ...i, ...values } : i)));

  const start = async (files) => {
    const items = files.map((file, n) => ({
      key: `${Date.now()}-${n}-${file.name}`,
      file,
      name: file.name,
      size: file.size,
      progress: 0,
      status: "waiting",
      error: null,
    }));
    for (const item of items) {
      if (!ACCEPTED_TYPES.includes(item.file.type)) {
        item.status = "error";
        item.error = "Unsupported file type. Use JPEG, PNG, WebP, AVIF or GIF.";
      } else if (item.file.size > maxMb * 1024 * 1024) {
        item.status = "error";
        item.error = `Larger than ${maxMb} MB.`;
      }
    }
    setQueue((current) => [...items.map(({ file: _file, ...rest }) => rest), ...current]);
    const pending = items.filter((i) => i.status === "waiting");
    const worker = async () => {
      while (pending.length) {
        const item = pending.shift();
        patch(item.key, { status: "uploading" });
        try {
          const res = await api.media.upload(item.file, fields, (progress) =>
            patch(item.key, { progress: progress ?? 50 }),
          );
          patch(item.key, {
            status: "done",
            progress: 100,
            duplicate: res.data.duplicate,
            result: res.data,
          });
          onUploaded?.(res.data);
        } catch (err) {
          patch(item.key, { status: "error", error: err.message });
        }
      }
    };
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  };

  const onFiles = (fileList) => {
    const files = Array.from(fileList ?? []);
    if (files.length) start(files);
  };

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onFiles(e.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed text-center transition-colors",
          compact ? "p-4" : "p-8",
          dragging ? "border-sage-600 bg-sage-50" : "border-charcoal/20 bg-cream/40",
        )}
      >
        <UploadCloud aria-hidden className="size-8 text-sage-700" />
        <p className="text-sm">
          <label htmlFor={inputId} className="cursor-pointer font-semibold text-sage-700 underline">
            Choose images
          </label>{" "}
          or drag and drop them here
        </p>
        <p className="text-xs text-muted">
          JPEG, PNG, WebP, AVIF or GIF up to {maxMb} MB. Images are optimised automatically
          (WebP/AVIF, responsive sizes, metadata removed).
        </p>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          multiple
          accept={ACCEPTED_TYPES.join(",")}
          className="sr-only"
          data-testid="media-file-input"
          onChange={(e) => {
            onFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {queue.length > 0 && (
        <ul aria-label="Uploads" className="space-y-2">
          {queue.map((item) => (
            <li
              key={item.key}
              className="rounded-lg border border-charcoal/10 bg-white px-3 py-2 text-sm"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate font-medium">{item.name}</span>
                <span className="shrink-0 text-xs text-muted">{formatBytes(item.size)}</span>
              </div>
              {item.status === "error" ? (
                <p role="alert" className="mt-1 flex items-center gap-1 text-red-800">
                  <CircleAlert aria-hidden className="size-4" /> {item.error}
                </p>
              ) : item.status === "done" ? (
                <p className="mt-1 flex items-center gap-1 text-sage-800">
                  <CircleCheck aria-hidden className="size-4" />
                  {item.duplicate
                    ? "Already in the library (reused)."
                    : `Optimised: ${item.result?.variants?.length ?? 0} versions, ${formatBytes(
                        item.result?.variants_size_bytes,
                      )} total.`}
                </p>
              ) : (
                <div
                  role="progressbar"
                  aria-label={`Uploading ${item.name}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={item.progress}
                  className="mt-2 h-1.5 overflow-hidden rounded-full bg-beige"
                >
                  <div
                    className="h-full bg-sage-600 transition-[width]"
                    style={{ width: `${item.status === "waiting" ? 0 : item.progress}%` }}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
