import { Download } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/Button";
import { useAdminApi } from "../../adminApiContext";
import { CheckboxField, TextField } from "../../components/Fields";
import { Modal } from "../../components/Modal";
import { useNotify } from "../../components/notifyContext";

function ImportDialog({ item, onClose, onImported }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [alt, setAlt] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.social.importInstagram({
        external_id: item.id,
        alt_text: alt.trim(),
        ownership_confirmed: confirmed,
      });
      notify("Image imported into the Media Library.");
      onImported(item.id, res.data.id);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  };

  return (
    <Modal open title="Import this image" onClose={onClose} size="md">
      <form onSubmit={submit} className="grid gap-4">
        <img
          src={item.preview_url}
          alt="Preview of the Instagram post"
          referrerPolicy="no-referrer"
          className="max-h-80 w-full rounded-lg bg-beige object-contain"
        />
        {item.caption && (
          <p className="line-clamp-4 text-sm whitespace-pre-line text-ink">{item.caption}</p>
        )}
        <p className="text-sm text-muted">
          A copy is saved in the Media Library with the caption, the link to the original post and
          “@{item.username} on Instagram” as the credit. Pages use the copy, never Instagram’s
          address.
        </p>
        <TextField
          label="Alt text"
          hint="Describe the image for people who cannot see it."
          required
          maxLength={300}
          value={alt}
          error={error?.details?.alt_text?.[0]}
          onChange={(e) => setAlt(e.target.value)}
        />
        <CheckboxField
          label="This is our own image and it is suitable for Think Positive Always"
          hint="Do not import reposts or other people's photos, artwork or quotes cards without permission."
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        {error && !error.details?.alt_text && (
          <p role="alert" className="text-sm text-red-800">
            {error.message}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy || !confirmed || !alt.trim()}>
            <Download aria-hidden />
            Import image
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** The connected Instagram account's own image posts, importable into the Media Library. */
export function InstagramImport() {
  const api = useAdminApi();
  const [state, setState] = useState({ items: null, after: null, error: null, loading: false });
  const [chosen, setChosen] = useState(null);

  const load = async (after) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await api.social.instagramMedia(after);
      setState((s) => ({
        items: [...(after ? (s.items ?? []) : []), ...res.data.items],
        after: res.data.after,
        error: null,
        loading: false,
      }));
    } catch (error) {
      setState((s) => ({ ...s, error, loading: false }));
    }
  };
  const imported = (externalId, assetId) => {
    setChosen(null);
    setState((s) => ({
      ...s,
      items: s.items.map((i) =>
        i.id === externalId ? { ...i, imported: true, media_asset_id: assetId } : i,
      ),
    }));
  };

  return (
    <section
      aria-labelledby="import-heading"
      className="rounded-xl border border-charcoal/10 bg-white p-5"
    >
      <h2 id="import-heading" className="text-xl font-medium">
        Import images from Instagram
      </h2>
      <p className="mt-2 text-sm text-ink">
        Only the connected account’s own single-image posts can be imported. Imported images appear
        in the Media Library and can be placed between quotes in the Quotes editor.
      </p>
      {state.items === null ? (
        <Button
          className="mt-4"
          size="sm"
          variant="outline"
          disabled={state.loading}
          onClick={() => load()}
        >
          {state.loading ? "Loading…" : "Show my Instagram posts"}
        </Button>
      ) : state.items.length === 0 ? (
        <p className="mt-4 text-sm text-muted">This account has no posts yet.</p>
      ) : (
        <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {state.items.map((item) => (
            <li key={item.id} className="rounded-lg border border-charcoal/10 p-2 text-sm">
              {item.preview_url ? (
                <img
                  src={item.preview_url}
                  alt={item.caption ? item.caption.slice(0, 80) : "Instagram post"}
                  referrerPolicy="no-referrer"
                  loading="lazy"
                  className="aspect-square w-full rounded bg-beige object-cover"
                />
              ) : (
                <div className="grid aspect-square place-items-center rounded bg-beige text-xs text-muted">
                  {item.media_type === "VIDEO" ? "Video" : "Album"}: not importable
                </div>
              )}
              <div className="mt-2">
                {item.imported ? (
                  <Link to="/admin/media" className="text-sage-800 underline">
                    Imported: see the Media Library
                  </Link>
                ) : item.supported ? (
                  <Button size="sm" variant="outline" onClick={() => setChosen(item)}>
                    Preview and import
                  </Button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {state.error && (
        <p role="alert" className="mt-3 text-sm text-red-800">
          {state.error.message}
        </p>
      )}
      {state.after && (
        <Button
          className="mt-4"
          size="sm"
          variant="outline"
          disabled={state.loading}
          onClick={() => load(state.after)}
        >
          Load more
        </Button>
      )}
      {chosen && (
        <ImportDialog item={chosen} onClose={() => setChosen(null)} onImported={imported} />
      )}
    </section>
  );
}
