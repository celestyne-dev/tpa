import { ImagePlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { mediaCache, rememberMedia } from "./mediaCache";
import { MediaPicker } from "./MediaPicker";

/** Small preview of a library image referenced by id. */
export function MediaThumb({ id, className = "size-20" }) {
  const api = useAdminApi();
  const [asset, setAsset] = useState(() => mediaCache.get(id) ?? null);
  useEffect(() => {
    if (!id || mediaCache.has(id)) return undefined;
    let cancelled = false;
    api.media
      .get(id)
      .then((res) => {
        rememberMedia(res.data);
        if (!cancelled) setAsset(res.data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [api, id]);
  const current = (asset?.id === id ? asset : null) ?? mediaCache.get(id);
  if (!current) return <span className={`${className} block rounded-lg bg-beige`} aria-hidden />;
  return (
    <img
      src={current.thumbnail_url ?? current.url}
      alt={current.alt_text || current.filename}
      className={`${className} rounded-lg bg-beige object-cover`}
    />
  );
}

/** Button + picker for a single image field. */
export function ImageChooser({ mediaId, onChange, label, allowClear = true, disabled = false }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-3">
      {mediaId ? <MediaThumb id={mediaId} /> : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <ImagePlus aria-hidden />
        {mediaId ? `Change ${label}` : `Choose ${label}`}
      </Button>
      {mediaId && allowClear && !disabled && (
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange(null)}>
          Remove
        </Button>
      )}
      <MediaPicker
        open={open}
        onClose={() => setOpen(false)}
        onSelect={(asset) => {
          rememberMedia(asset);
          onChange(asset.id, asset);
        }}
      />
    </div>
  );
}
