import { ExternalLink, Send, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDateTime } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { DataTable } from "../../components/DataTable";
import { SelectField, TextAreaField, TextField } from "../../components/Fields";
import { ImageChooser, MediaThumb } from "../../components/media/ImageChooser";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { PLATFORM_LABELS } from "./socialLinks";

const VIEWS = [
  ["queue", "Scheduled queue"],
  ["published", "Published"],
  ["failed", "Failed and cancelled"],
];
const STATUS_LABELS = {
  scheduled: "Scheduled",
  publishing: "Publishing",
  checking: "Checking",
  published: "Published",
  failed: "Failed",
  cancelled: "Cancelled",
};
const STATUS_TONES = { publishing: "running", checking: "pending" };
const LIMITS = { pinterest: { title: 100, text: 800 }, instagram: { text: 2200 } };

const numberParam = (params, key) => {
  const value = Number(params.get(key));
  return Number.isInteger(value) && value > 0 ? value : null;
};

function AccountStrip({ accounts }) {
  return (
    <ul className="mb-6 grid gap-3 sm:grid-cols-2" aria-label="Connected accounts">
      {accounts.map((a) => (
        <li
          key={a.platform}
          className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-charcoal/10 bg-white px-4 py-3 text-sm"
        >
          <span>
            <span className="font-medium">{a.label}</span>{" "}
            {a.account?.username ? <span className="text-muted">@{a.account.username}</span> : null}
            {a.account?.last_error && !a.connected ? (
              <span className="block text-red-800">{a.account.last_error}</span>
            ) : null}
          </span>
          {a.connected ? (
            <StatusBadge status="active" label="Connected" />
          ) : (
            <Link to="/admin/integrations" className="text-sage-800 underline">
              {a.account ? "Reconnect" : a.setup.ready ? "Connect" : "Set up"}
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Finds a published article or quote collection to relate the post to. */
function RelatedPicker({ article, onChange }) {
  const api = useAdminApi();
  const [kind, setKind] = useState("quotes");
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);

  const search = async () => {
    setBusy(true);
    try {
      const res = await api.articles.list({
        q: q.trim() || undefined,
        status: "published",
        content_type: kind === "article" ? undefined : kind,
        page_size: 10,
      });
      setResults(res.data);
    } catch {
      setResults([]);
    } finally {
      setBusy(false);
    }
  };

  if (article) {
    return (
      <div className="rounded-lg border border-charcoal/10 bg-cream/50 p-3 text-sm">
        <p className="font-medium">{article.title}</p>
        <p className="text-muted">
          {article.content_type === "quotes" ? "Quote collection" : "Article"}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-1"
          onClick={() => onChange(null)}
        >
          <X aria-hidden />
          Remove
        </Button>
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      <div className="grid gap-2 sm:grid-cols-[10rem_1fr_auto] sm:items-end">
        <SelectField
          label="Type"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          options={[
            { value: "quotes", label: "Quote collection" },
            { value: "article", label: "Article" },
          ]}
        />
        <TextField
          label="Search published titles"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              search();
            }
          }}
        />
        <Button type="button" variant="outline" size="sm" disabled={busy} onClick={search}>
          Search
        </Button>
      </div>
      {results &&
        (results.length ? (
          <ul className="divide-y divide-charcoal/10 rounded-lg border border-charcoal/10 text-sm">
            {results.map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  className="w-full px-3 py-2 text-left hover:bg-cream/60"
                  onClick={() => onChange(row)}
                >
                  {row.title}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Nothing published matches.</p>
        ))}
    </div>
  );
}

function Composer({ accounts, onCreated }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [params] = useSearchParams();
  const connected = accounts.filter((a) => a.connected).map((a) => a.platform);
  const asked = params.get("platform");
  const [platform, setPlatform] = useState(
    connected.includes(asked) ? asked : (connected[0] ?? "pinterest"),
  );
  const [mediaId, setMediaId] = useState(numberParam(params, "media"));
  const [article, setArticle] = useState(null);
  const [form, setForm] = useState({ title: "", text: "", alt_text: "", destination_url: "" });
  const [boardId, setBoardId] = useState("");
  const [when, setWhen] = useState(params.get("when") === "schedule" ? "schedule" : "now");
  const [at, setAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [repeat, setRepeat] = useState(false);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const isPin = platform === "pinterest";
  const ready = connected.includes(platform);

  const articleId = numberParam(params, "article");
  useEffect(() => {
    if (!articleId) return undefined;
    let cancelled = false;
    api.articles
      .get(articleId)
      .then((res) => {
        if (cancelled) return;
        setArticle(res.data);
        setForm((f) => ({ ...f, title: f.title || (res.data.title ?? "").slice(0, 100) }));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [api, articleId]);

  const pinterestReady = connected.includes("pinterest");
  const boards = useAdminQuery(
    () => (pinterestReady ? api.social.boards() : Promise.resolve({ data: [] })),
    [pinterestReady],
  );

  const submit = async (allowRepeat = false) => {
    setBusy(true);
    setError(null);
    try {
      const body = {
        platform,
        media_asset_id: mediaId,
        article_id: article?.id ?? null,
        text: form.text,
        scheduled_at: when === "schedule" && at ? new Date(at).toISOString() : null,
        ...(isPin
          ? {
              title: form.title,
              alt_text: form.alt_text,
              board_id: boardId,
              destination_url: article ? undefined : form.destination_url,
            }
          : {}),
        ...(allowRepeat ? { allow_repeat: true } : {}),
      };
      const res = await api.social.createPost(body);
      const post = res.data;
      setRepeat(false);
      setMediaId(null);
      setForm({ title: "", text: "", alt_text: "", destination_url: "" });
      setAt("");
      if (post.status === "published") notify(`Published to ${PLATFORM_LABELS[platform]}.`);
      else if (post.status === "failed") notify(post.last_error ?? "The post failed.", "error");
      else if (when === "schedule") notify("Post scheduled.");
      else notify("The post is being processed; see the queue for its status.");
      onCreated(post);
    } catch (err) {
      if (err.status === 409 && err.details?.allow_repeat) setRepeat(true);
      else setError(err);
    } finally {
      setBusy(false);
    }
  };
  const fieldError = (key) => error?.details?.[key]?.[0];
  const published = article && article.status === "published";

  return (
    <form
      aria-labelledby="compose-heading"
      className="rounded-xl border border-charcoal/10 bg-white p-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (when === "schedule" && !at) {
          setError({
            message: "Choose a date and time.",
            details: { scheduled_at: ["Required."] },
          });
          return;
        }
        submit();
      }}
    >
      <h2 id="compose-heading" className="text-xl font-medium">
        New post
      </h2>
      <div className="mt-4 grid gap-5">
        <fieldset>
          <legend className="text-sm font-medium">Platform</legend>
          <div className="mt-2 flex flex-wrap gap-4 text-sm">
            {accounts.map((a) => (
              <label key={a.platform} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="platform"
                  className="accent-sage-700"
                  value={a.platform}
                  checked={platform === a.platform}
                  onChange={() => setPlatform(a.platform)}
                />
                {a.label}
                {!a.connected && <span className="text-muted">(not connected)</span>}
              </label>
            ))}
          </div>
        </fieldset>

        {!ready && (
          <p role="note" className="rounded-lg bg-gold-100/60 p-3 text-sm">
            {PLATFORM_LABELS[platform]} is not connected.{" "}
            <Link to="/admin/integrations" className="text-sage-800 underline">
              Open Integrations
            </Link>{" "}
            to connect it.
          </p>
        )}

        <div>
          <p className="mb-2 text-sm font-medium">Image</p>
          <ImageChooser label="image" mediaId={mediaId} onChange={setMediaId} />
          {fieldError("media_asset_id") && (
            <p role="alert" className="mt-1 text-sm text-red-800">
              {fieldError("media_asset_id")}
            </p>
          )}
          {!isPin && (
            <p className="mt-1 text-sm text-muted">
              Instagram needs a JPEG between 4:5 (portrait) and 1.91:1 (landscape).
            </p>
          )}
        </div>

        <div>
          <p className="mb-2 text-sm font-medium">Related article or quote collection</p>
          <RelatedPicker
            article={article}
            onChange={(row) => {
              setArticle(row);
              if (row)
                setForm((f) => ({ ...f, title: f.title || (row.title ?? "").slice(0, 100) }));
            }}
          />
          {fieldError("article_id") && (
            <p role="alert" className="mt-1 text-sm text-red-800">
              {fieldError("article_id")}
            </p>
          )}
          {article && !published && (
            <p className="mt-1 text-sm text-red-800">
              This is not published yet. Publish it on the site before posting about it.
            </p>
          )}
        </div>

        {isPin ? (
          <>
            <TextField
              label="Pin title"
              required
              maxLength={LIMITS.pinterest.title}
              value={form.title}
              error={fieldError("title")}
              onChange={set("title")}
            />
            <TextAreaField
              label="Pin description"
              maxLength={LIMITS.pinterest.text}
              value={form.text}
              error={fieldError("text")}
              onChange={set("text")}
            />
            <TextField
              label="Alt text (optional)"
              hint="Left empty, the image's own alt text is used."
              maxLength={500}
              value={form.alt_text}
              error={fieldError("alt_text")}
              onChange={set("alt_text")}
            />
            <SelectField
              label="Board"
              required
              value={boardId}
              error={fieldError("board_id") ?? boards.error?.message}
              onChange={(e) => setBoardId(e.target.value)}
              options={[
                { value: "", label: boards.loading ? "Loading boards…" : "Choose a board" },
                ...(boards.data ?? []).map((b) => ({ value: b.id, label: b.name })),
              ]}
            />
            {article ? (
              <p className="text-sm text-ink">
                <span className="font-medium">Destination link:</span> the Pin links to this{" "}
                {article.content_type === "quotes" ? "quote collection" : "article"}’s page on the
                website.
              </p>
            ) : (
              <TextField
                label="Destination link"
                type="url"
                required
                placeholder="https://"
                hint="A page on this website. Choose a related article or quote collection above to use its address automatically."
                value={form.destination_url}
                error={fieldError("destination_url")}
                onChange={set("destination_url")}
              />
            )}
          </>
        ) : (
          <TextAreaField
            label="Caption"
            required
            rows={6}
            maxLength={LIMITS.instagram.text}
            hint="Hashtags go in the caption (30 at most). Links in Instagram captions are not clickable, so a web address here will not send readers to the site."
            value={form.text}
            error={fieldError("text") ?? fieldError("destination_url")}
            onChange={set("text")}
          />
        )}

        <fieldset>
          <legend className="text-sm font-medium">When</legend>
          <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="when"
                className="accent-sage-700"
                checked={when === "now"}
                onChange={() => setWhen("now")}
              />
              Publish now
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="when"
                className="accent-sage-700"
                checked={when === "schedule"}
                onChange={() => setWhen("schedule")}
              />
              Schedule
            </label>
          </div>
          {when === "schedule" && (
            <TextField
              className="mt-3 max-w-xs"
              label="Date and time"
              type="datetime-local"
              hint="Your local time. Scheduled posts go out within a few minutes of this time."
              value={at}
              error={fieldError("scheduled_at")}
              onChange={(e) => setAt(e.target.value)}
            />
          )}
        </fieldset>

        {error && (
          <p role="alert" className="text-sm text-red-800">
            {error.message}
          </p>
        )}
        <div>
          <Button type="submit" disabled={busy || !ready || !mediaId}>
            <Send aria-hidden />
            {when === "schedule"
              ? "Schedule post"
              : isPin
                ? "Send to Pinterest"
                : "Publish to Instagram"}
          </Button>
        </div>
      </div>
      <ConfirmDialog
        open={repeat}
        title="Publish this image again?"
        message="This image has already been published to this account. Publishing it again creates a second post."
        confirmLabel="Publish again"
        busy={busy}
        onConfirm={() => submit(true)}
        onCancel={() => setRepeat(false)}
      />
    </form>
  );
}

function Posts({ canPublish, refreshKey, postsFor, onClearFilter }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [view, setView] = useState(postsFor ? "published" : "queue");
  const [busy, setBusy] = useState(null);
  const { data, meta, error, loading, reload } = useAdminQuery(
    () => api.social.posts({ view, page_size: 50, media_asset_id: postsFor ?? undefined }),
    [view, refreshKey, postsFor],
  );
  const act = async (post, action, message) => {
    setBusy(post.id);
    try {
      const res = await (action === "retry"
        ? api.social.retryPost(post.id)
        : api.social.cancelPost(post.id));
      if (res.data.status === "failed") notify(res.data.last_error ?? "The post failed.", "error");
      else notify(message);
      reload();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(null);
    }
  };
  const columns = [
    {
      key: "image",
      header: "Image",
      render: (p) =>
        p.media_asset ? <MediaThumb id={p.media_asset.id} className="size-12" /> : "—",
    },
    {
      key: "post",
      header: "Post",
      render: (p) => (
        <div className="max-w-md">
          <p className="font-medium">
            {PLATFORM_LABELS[p.platform]}
            {p.board_name ? ` · ${p.board_name}` : ""}
          </p>
          <p className="line-clamp-2 text-muted">{p.title || p.text}</p>
          {p.article && <p className="text-xs text-muted">About: {p.article.title}</p>}
          {p.destination_url && (
            <p className="truncate text-xs text-muted">Links to {p.destination_url}</p>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (p) => (
        <div>
          <StatusBadge
            status={STATUS_TONES[p.status] ?? p.status}
            label={STATUS_LABELS[p.status] ?? p.status}
          />
          {p.last_error && <p className="mt-1 max-w-xs text-xs text-red-800">{p.last_error}</p>}
          {p.status === "checking" && (
            <p className="mt-1 max-w-xs text-xs text-muted">
              Confirming with the platform before anything is sent again.
            </p>
          )}
        </div>
      ),
    },
    {
      key: "when",
      header: view === "published" ? "Published" : "Scheduled for",
      render: (p) => formatDateTime(p.published_at ?? p.next_attempt_at ?? p.scheduled_at),
    },
    {
      key: "actions",
      header: "Actions",
      render: (p) => (
        <div className="flex flex-wrap items-center gap-2">
          {p.external_url && (
            <a
              href={p.external_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-sage-800 underline"
            >
              <ExternalLink aria-hidden className="size-4" />
              View on {PLATFORM_LABELS[p.platform]}
            </a>
          )}
          {canPublish && p.can_retry && (
            <Button
              size="sm"
              variant="outline"
              disabled={busy === p.id}
              onClick={() => act(p, "retry", "Retried.")}
            >
              Retry
            </Button>
          )}
          {canPublish && p.can_cancel && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy === p.id}
              onClick={() => act(p, "cancel", "Post cancelled.")}
            >
              Cancel
            </Button>
          )}
        </div>
      ),
    },
  ];
  return (
    <section aria-labelledby="posts-heading" className="mt-10">
      <h2 id="posts-heading" className="mb-3 text-xl font-medium">
        Posts
      </h2>
      {postsFor && (
        <p className="mb-3 flex flex-wrap items-center gap-2 text-sm">
          Showing posts made from one image.
          <Button size="sm" variant="ghost" onClick={onClearFilter}>
            <X aria-hidden />
            Show all posts
          </Button>
        </p>
      )}
      <div role="tablist" aria-label="Posts" className="mb-4 flex flex-wrap gap-2">
        {VIEWS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={view === key}
            onClick={() => setView(key)}
            className={
              view === key
                ? "rounded-full bg-sage-700 px-4 py-1.5 text-sm font-medium text-white"
                : "rounded-full bg-beige px-4 py-1.5 text-sm text-ink hover:bg-sage-100"
            }
          >
            {label}
          </button>
        ))}
      </div>
      {error ? (
        <ErrorState title="We couldn't load the posts" onRetry={reload} />
      ) : (
        <>
          <DataTable
            caption={VIEWS.find(([k]) => k === view)[1]}
            columns={columns}
            rows={data}
            loading={loading}
            empty={{
              title:
                view === "queue"
                  ? "Nothing is waiting to be published"
                  : view === "published"
                    ? "Nothing has been published yet"
                    : "No failed or cancelled posts",
            }}
          />
          {meta?.total > (data?.length ?? 0) && (
            <p className="mt-2 text-sm text-muted">
              Showing the first {data.length} of {meta.total}.
            </p>
          )}
        </>
      )}
    </section>
  );
}

export function SocialPublishingPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const [params, setParams] = useSearchParams();
  const [refreshKey, setRefreshKey] = useState(0);
  const accounts = useAdminQuery(() => api.social.accounts(), [refreshKey]);
  const canPublish = can("social.publish");
  const postsFor = numberParam(params, "posts_for");
  return (
    <>
      <AdminPageHeader
        title="Social publishing"
        description="Send Media Library images to Pinterest and Instagram, now or at a time you choose. Nothing is posted unless someone creates the post here."
        breadcrumbs={[{ label: "Social publishing" }]}
      />
      {accounts.error ? (
        <ErrorState title="We couldn't load the accounts" onRetry={accounts.reload} />
      ) : !accounts.data ? (
        <p role="status">Loading…</p>
      ) : (
        <>
          <AccountStrip accounts={accounts.data} />
          {canPublish ? (
            <Composer
              key={`${params.get("media")}-${params.get("article")}-${params.get("platform")}`}
              accounts={accounts.data}
              onCreated={() => setRefreshKey((k) => k + 1)}
            />
          ) : (
            <p className="text-sm text-muted">
              You can see the posts below; creating them needs the “Publish to Pinterest and
              Instagram” permission.
            </p>
          )}
        </>
      )}
      <Posts
        canPublish={canPublish}
        refreshKey={refreshKey}
        postsFor={postsFor}
        onClearFilter={() => setParams({})}
      />
    </>
  );
}
