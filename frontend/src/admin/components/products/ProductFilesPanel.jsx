import { Download, FileUp, ShieldAlert } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { TextField } from "../Fields";
import { useNotify } from "../notifyContext";
import { StatusBadge } from "../StatusBadge";

const formatSize = (bytes) =>
  bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.round(bytes / 1024)} KB`;

const SCAN_LABEL = {
  not_configured: "Not scanned (no scanner configured)",
  pending: "Awaiting malware scan",
  clean: "Scanned: clean",
  infected: "Scan found a threat — not delivered",
  error: "Scan failed — not delivered",
};

function UploadForm({ onUpload, label = "Upload file", withMeta = true }) {
  const input = useRef(null);
  const [meta, setMeta] = useState({ title: "", description: "" });
  const [state, setState] = useState({ busy: false, progress: null, error: null });
  const submit = async (event) => {
    event.preventDefault();
    const file = input.current?.files?.[0];
    if (!file) {
      setState({ busy: false, progress: null, error: { message: "Choose a file to upload." } });
      return;
    }
    setState({ busy: true, progress: 0, error: null });
    try {
      await onUpload(file, withMeta ? meta : {}, (p) => setState((s) => ({ ...s, progress: p })));
      setMeta({ title: "", description: "" });
      input.current.value = "";
      setState({ busy: false, progress: null, error: null });
    } catch (error) {
      setState({ busy: false, progress: null, error });
    }
  };
  return (
    <form
      aria-label={label}
      onSubmit={submit}
      className="space-y-3 rounded-xl border border-dashed border-charcoal/20 p-4"
    >
      <label className="block text-sm font-medium">
        Choose a PDF, EPUB or ZIP file
        <input
          ref={input}
          type="file"
          accept=".pdf,.epub,.zip,application/pdf,application/epub+zip,application/zip"
          className="mt-2 block w-full text-sm"
        />
      </label>
      {withMeta && (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField
            label="Title shown to buyers"
            value={meta.title}
            placeholder="e.g. Workbook (printable PDF)"
            onChange={(e) => setMeta({ ...meta, title: e.target.value })}
          />
          <TextField
            label="Description (optional)"
            value={meta.description}
            placeholder="e.g. A4 and US Letter"
            onChange={(e) => setMeta({ ...meta, description: e.target.value })}
          />
        </div>
      )}
      {state.error && (
        <p role="alert" className="text-sm text-red-800">
          {state.error.details?.file?.join(" ") ?? state.error.message}
        </p>
      )}
      <Button type="submit" size="sm" disabled={state.busy}>
        <FileUp aria-hidden />
        {state.busy ? `Uploading… ${state.progress ?? 0}%` : label}
      </Button>
    </form>
  );
}

/** Private deliverable files. They never enter the public media library. */
export function ProductFilesPanel({ product, canManage, onChanged, scanner, maxMb }) {
  const api = useAdminApi();
  const notify = useNotify();
  const run = async (fn, message) => {
    try {
      await fn();
      notify(message);
      onChanged();
    } catch (error) {
      notify(error.message, "error");
    }
  };
  if (product.product_type === "bundle") {
    return (
      <p className="text-sm text-muted">
        Bundles deliver the files of the products they include. Manage files on each included
        product.
      </p>
    );
  }
  return (
    <div className="space-y-6">
      <div className="rounded-xl bg-sage-50 p-4 text-sm">
        <p className="font-medium">How files are protected and versioned</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
          <li>
            Files are stored privately and are only downloadable through a buyer's account, with
            short-lived links.
          </li>
          <li>
            Accepted: PDF, EPUB and ZIP resource packs (up to {maxMb} MB). Executables, scripts,
            PDFs with JavaScript and unsafe archives are refused.
          </li>
          <li>
            Replacing a file adds a new version. Buyers always get the latest version and can also
            download the version they originally received.
          </li>
          <li>
            Deactivated files stay available to people who already bought them, but new buyers don't
            receive them.
          </li>
          {!scanner && (
            <li>
              No malware scanner is configured (PRODUCT_FILES_SCAN_COMMAND); files are checked
              structurally only.
            </li>
          )}
        </ul>
      </div>
      {product.files.length === 0 && <p className="text-sm text-muted">No files uploaded yet.</p>}
      <ul className="space-y-4">
        {product.files.map((file) => (
          <li key={file.id} className="rounded-xl border border-charcoal/10 bg-white p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium">{file.title}</p>
                {file.description && <p className="text-sm text-muted">{file.description}</p>}
                <p className="mt-1 text-xs text-muted">{file.downloads} customer download(s)</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <StatusBadge status={file.status} />
                {canManage && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      run(
                        () =>
                          api.products.updateFile(product.id, file.id, {
                            status: file.status === "active" ? "inactive" : "active",
                          }),
                        file.status === "active"
                          ? "File deactivated for new buyers."
                          : "File reactivated.",
                      )
                    }
                  >
                    {file.status === "active" ? "Deactivate" : "Reactivate"}
                  </Button>
                )}
              </div>
            </div>
            <table className="mt-3 w-full text-sm">
              <caption className="sr-only">Versions of {file.title}</caption>
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1 font-medium">Version</th>
                  <th className="font-medium">File</th>
                  <th className="font-medium">Security check</th>
                  <th className="font-medium">Bought with it</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {file.versions.map((v) => (
                  <tr key={v.id} className="border-t border-charcoal/5">
                    <td className="py-2">
                      v{v.version}
                      {file.current_version?.id === v.id && (
                        <span className="ml-1 text-xs text-sage-800">(current)</span>
                      )}
                    </td>
                    <td>
                      {v.original_filename} · {v.format.toUpperCase()} · {formatSize(v.size_bytes)}
                      <span className="block text-xs text-muted">
                        {formatDateTime(v.created_at)}
                      </span>
                    </td>
                    <td className={v.deliverable ? "" : "text-red-800"}>
                      {!v.deliverable && <ShieldAlert aria-hidden className="mr-1 inline size-4" />}
                      {SCAN_LABEL[v.scan_status]}
                    </td>
                    <td>{v.purchases}</td>
                    <td className="space-x-2 text-right whitespace-nowrap">
                      {canManage && (
                        <a
                          href={api.products.fileDownloadUrl(product.id, file.id, v.id)}
                          className="inline-flex items-center gap-1 text-sage-800 underline"
                        >
                          <Download aria-hidden className="size-4" />
                          <span className="sr-only">
                            Download v{v.version} of {file.title}
                          </span>
                          <span aria-hidden>Download</span>
                        </a>
                      )}
                      {canManage && file.current_version?.id !== v.id && (
                        <button
                          type="button"
                          className="text-sage-800 underline"
                          onClick={() =>
                            run(
                              () =>
                                api.products.updateFile(product.id, file.id, {
                                  current_version_id: v.id,
                                }),
                              `v${v.version} is now the current version.`,
                            )
                          }
                        >
                          Make current
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {canManage && (
              <div className="mt-3">
                <UploadForm
                  label="Upload a new version"
                  withMeta={false}
                  onUpload={async (f, _meta, progress) => {
                    await api.products.uploadVersion(product.id, file.id, f, {}, progress);
                    notify("New version uploaded.");
                    onChanged();
                  }}
                />
              </div>
            )}
          </li>
        ))}
      </ul>
      {canManage && (
        <UploadForm
          label="Upload a new file"
          onUpload={async (f, meta, progress) => {
            await api.products.uploadFile(product.id, f, meta, progress);
            notify("File uploaded privately.");
            onChanged();
          }}
        />
      )}
    </div>
  );
}
