import { Search } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdminApi } from "../../adminApiContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { Modal } from "../Modal";
import { MediaGrid } from "./MediaGrid";
import { MediaUploader } from "./MediaUploader";

/** Choose one (or several) images from the library, or upload new ones on the spot. */
export function MediaPicker({
  open,
  onClose,
  onSelect,
  multiple = false,
  title = "Choose an image",
}) {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState([]);
  const query = useAdminQuery(
    () =>
      open
        ? api.media.list({ q: search || undefined, page_size: 40 })
        : Promise.resolve({ data: [] }),
    [open, search],
  );
  const items = query.data ?? [];

  const toggle = (item) => {
    if (!multiple) {
      onSelect(item);
      onClose();
      return;
    }
    setSelected((current) =>
      current.some((s) => s.id === item.id)
        ? current.filter((s) => s.id !== item.id)
        : [...current, item],
    );
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description="Only active images are shown. Archived images can be restored in the media library."
      size="lg"
      footer={
        multiple && (
          <>
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              disabled={!selected.length}
              onClick={() => {
                onSelect(selected);
                setSelected([]);
                onClose();
              }}
            >
              Add {selected.length || ""} image{selected.length === 1 ? "" : "s"}
            </Button>
          </>
        )
      }
    >
      <div className="space-y-4">
        {can("media.upload") && (
          <MediaUploader
            compact
            onUploaded={(asset) => {
              query.reload();
              if (!multiple) {
                onSelect(asset);
                onClose();
              } else setSelected((s) => [...s, asset]);
            }}
          />
        )}
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q.trim());
          }}
          className="flex gap-2"
        >
          <label className="sr-only" htmlFor="media-picker-search">
            Search images
          </label>
          <input
            id="media-picker-search"
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name, title or alt text"
            className="h-10 flex-1 rounded-lg border border-charcoal/20 px-3 text-sm"
          />
          <Button type="submit" size="sm" variant="outline">
            <Search aria-hidden />
            Search
          </Button>
        </form>
        {query.loading && !query.data ? (
          <Skeleton className="h-40 w-full" />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted">No images found.</p>
        ) : (
          <MediaGrid
            items={items}
            label="Images to choose from"
            selectedIds={multiple ? selected.map((s) => s.id) : []}
            onOpen={toggle}
          />
        )}
      </div>
    </Modal>
  );
}
