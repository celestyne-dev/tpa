import { CheckCircle2, Download } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { LeadMagnetForm } from "@/components/newsletter/LeadMagnetForm";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { redirectTo, useLoad } from "../hooks";

/** Tokens arrive in the URL fragment, so they never reach server logs or referrers. */
function tokenFromHash() {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
}

function Card({ title, children }) {
  return (
    <Container size="narrow" className="py-14 sm:py-20">
      <div className="mx-auto max-w-lg rounded-[var(--radius-card)] border border-charcoal/10 bg-white p-7 shadow-soft sm:p-9">
        <h1 className="text-3xl font-medium">{title}</h1>
        <div className="mt-6 space-y-4">{children}</div>
      </div>
    </Container>
  );
}

function Problem({ children }) {
  return (
    <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-900">
      {children}
    </p>
  );
}

export function NewsletterConfirmPage() {
  const shopApi = useShopApi();
  const [state, setState] = useState({ phase: "idle", error: null, manage: "" });
  const token = tokenFromHash();
  // Confirmation needs a click: link scanners that open emails can't subscribe anyone.
  const confirm = async () => {
    setState({ phase: "busy", error: null, manage: "" });
    try {
      const res = await shopApi.confirmSubscription(token);
      setState({ phase: "done", error: null, manage: res.data.preferences_token });
    } catch (error) {
      setState({ phase: "error", error, manage: "" });
    }
  };
  return (
    <>
      <Seo title="Confirm your subscription" path={routes.newsletterConfirm} noIndex />
      <Card title="Confirm your subscription">
        {state.phase === "done" ? (
          <div role="status" className="space-y-4">
            <CheckCircle2 aria-hidden className="size-8 text-sage-700" />
            <p>Thank you — you're subscribed to The Positive Reset.</p>
            <p className="text-sm text-muted">
              You can choose what you receive, or unsubscribe, at any time.
            </p>
            <Link
              to={`${routes.newsletterPreferences}#token=${state.manage}`}
              className="font-medium underline underline-offset-4"
            >
              Choose what you receive
            </Link>
          </div>
        ) : !token ? (
          <Problem>
            This link is incomplete. Please use the button in your confirmation email.
          </Problem>
        ) : (
          <>
            <p className="text-muted">
              Press the button to confirm that you want to receive The Positive Reset.
            </p>
            {state.phase === "error" && (
              <Problem>
                {state.error.message}{" "}
                <Link to={routes.newsletter} className="underline">
                  Sign up again
                </Link>
              </Problem>
            )}
            <Button onClick={confirm} disabled={state.phase === "busy"} className="w-full">
              {state.phase === "busy" ? "Confirming…" : "Confirm my subscription"}
            </Button>
          </>
        )}
      </Card>
    </>
  );
}

export function NewsletterPreferencesPage() {
  const shopApi = useShopApi();
  const token = tokenFromHash();
  const { data, error, loading } = useLoad(
    () => (token ? shopApi.newsletterPreferences(token) : Promise.reject(new Error("missing"))),
    [token],
  );
  return (
    <>
      <Seo title="Email preferences" path={routes.newsletterPreferences} noIndex />
      <Card title="Your email preferences">
        {loading ? (
          <p className="text-muted">Loading…</p>
        ) : error || !data ? (
          <Problem>
            This link is invalid or no longer works. Use the link in your latest email.
          </Problem>
        ) : (
          <PreferencesForm token={token} initial={data} />
        )}
      </Card>
    </>
  );
}

function PreferencesForm({ token, initial }) {
  const shopApi = useShopApi();
  const [view, setView] = useState(initial);
  const [prefs, setPrefs] = useState(initial.preferences);
  const [name, setName] = useState(initial.first_name);
  const [state, setState] = useState({ phase: "idle", message: "" });
  const [erased, setErased] = useState(false);
  if (erased)
    return (
      <p role="status">
        Your details have been deleted. Your address stays on our do-not-email list so you won't
        hear from us again.
      </p>
    );
  if (view.status === "unsubscribed")
    return (
      <p>
        {view.email} is unsubscribed. Changed your mind?{" "}
        <Link to={routes.newsletter} className="underline underline-offset-4">
          Sign up again
        </Link>
        .
      </p>
    );
  const save = async (event) => {
    event.preventDefault();
    setState({ phase: "busy", message: "" });
    try {
      const res = await shopApi.updateNewsletterPreferences(token, {
        preferences: prefs,
        first_name: name,
      });
      setView(res.data);
      setState({ phase: "saved", message: "Your preferences are saved." });
    } catch (error) {
      setState({ phase: "error", message: error.message });
    }
  };
  return (
    <form onSubmit={save} className="space-y-4">
      <p className="text-sm text-muted">Signed in by email link as {view.email}.</p>
      <label className="block text-sm font-medium">
        First name (optional)
        <input
          className="mt-1.5 w-full rounded-full border border-charcoal/20 px-4 py-2.5"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Send me</legend>
        {view.options.map((option) => (
          <label key={option.key} className="flex items-center gap-3 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-sage-700"
              checked={prefs.includes(option.key)}
              onChange={() =>
                setPrefs(
                  prefs.includes(option.key)
                    ? prefs.filter((p) => p !== option.key)
                    : [...prefs, option.key],
                )
              }
            />
            {option.label}
          </label>
        ))}
      </fieldset>
      {state.phase === "error" && <Problem>{state.message}</Problem>}
      {state.phase === "saved" && (
        <p role="status" className="text-sm text-sage-800">
          {state.message}
        </p>
      )}
      <Button type="submit" disabled={state.phase === "busy"}>
        Save preferences
      </Button>
      <div className="border-t border-charcoal/10 pt-4 text-sm">
        <Link
          to={`${routes.newsletterUnsubscribe}#token=${token}`}
          className="underline underline-offset-4"
        >
          Unsubscribe from everything
        </Link>
        <button
          type="button"
          className="ml-4 text-red-800 underline underline-offset-4"
          onClick={async () => {
            if (!window.confirm("Delete your details? This can't be undone.")) return;
            await shopApi.eraseSubscription(token);
            setErased(true);
          }}
        >
          Delete my details
        </button>
      </div>
    </form>
  );
}

export function NewsletterUnsubscribePage() {
  const shopApi = useShopApi();
  const token = tokenFromHash();
  const [reason, setReason] = useState("");
  const [state, setState] = useState({ phase: "idle", message: "" });
  const unsubscribe = async () => {
    setState({ phase: "busy", message: "" });
    try {
      const res = await shopApi.unsubscribe(token, { reason });
      setState({ phase: "done", message: res.data.email });
    } catch (error) {
      setState({ phase: "error", message: error.message });
    }
  };
  return (
    <>
      <Seo title="Unsubscribe" path={routes.newsletterUnsubscribe} noIndex />
      <Card title="Unsubscribe">
        {state.phase === "done" ? (
          <div role="status" className="space-y-3">
            <p>{state.message} won't receive The Positive Reset any more.</p>
            <p className="text-sm text-muted">
              Changed your mind?{" "}
              <Link to={routes.newsletter} className="underline underline-offset-4">
                You can sign up again
              </Link>{" "}
              at any time.
            </p>
          </div>
        ) : !token ? (
          <Problem>
            This link is incomplete. Please use the link at the bottom of our emails.
          </Problem>
        ) : (
          <>
            <p className="text-muted">
              You'll stop receiving all newsletters and automated emails straight away.
            </p>
            <label className="block text-sm font-medium">
              Anything we could do better? (optional)
              <textarea
                className="mt-1.5 w-full rounded-2xl border border-charcoal/20 px-4 py-2.5"
                rows={3}
                maxLength={300}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            {state.phase === "error" && <Problem>{state.message}</Problem>}
            <Button onClick={unsubscribe} disabled={state.phase === "busy"} className="w-full">
              Unsubscribe
            </Button>
            <p className="text-sm">
              Or{" "}
              <Link
                to={`${routes.newsletterPreferences}#token=${token}`}
                className="underline underline-offset-4"
              >
                choose fewer emails instead
              </Link>
              .
            </p>
          </>
        )}
      </Card>
    </>
  );
}

function formatBytes(bytes) {
  return bytes > 1_000_000
    ? `${(bytes / 1_000_000).toFixed(1)} MB`
    : `${Math.ceil(bytes / 1000)} KB`;
}

export function ResourceAccessPage() {
  const shopApi = useShopApi();
  const token = tokenFromHash();
  const { data, error, loading } = useLoad(
    () => (token ? shopApi.leadMagnetAccess(token) : Promise.reject(new Error("missing"))),
    [token],
  );
  const expiredSlug = error?.status === 410 ? error.details?.slug : null;
  const magnet = useLoad(
    () => (expiredSlug ? shopApi.leadMagnet(expiredSlug) : Promise.resolve(null)),
    [expiredSlug],
  );
  const [downloadError, setDownloadError] = useState("");
  const download = async (fileId) => {
    setDownloadError("");
    try {
      const res = await shopApi.leadMagnetDownload(token, fileId);
      redirectTo.go(res.data.url);
    } catch (err) {
      setDownloadError(err.message);
    }
  };
  return (
    <>
      <Seo title="Your free resource" path={routes.resourceAccess} noIndex />
      <Card title={data ? data.lead_magnet.title : "Your free resource"}>
        {loading ? (
          <p className="text-muted">Loading…</p>
        ) : expiredSlug ? (
          <>
            <Problem>{error.message}</Problem>
            {magnet.data && <LeadMagnetForm leadMagnet={magnet.data} />}
          </>
        ) : error || !data ? (
          <Problem>This link is invalid. Please use the button in your email.</Problem>
        ) : (
          <>
            {data.lead_magnet.description && (
              <p className="text-muted">{data.lead_magnet.description}</p>
            )}
            <ul className="space-y-3">
              {data.files.map((file) => (
                <li
                  key={file.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-charcoal/10 p-4"
                >
                  <div>
                    <p className="font-medium">{file.title}</p>
                    <p className="text-xs text-muted">
                      {file.format} · {formatBytes(file.size_bytes)}
                    </p>
                  </div>
                  <Button size="sm" onClick={() => download(file.id)}>
                    <Download aria-hidden className="size-4" /> Download
                  </Button>
                </li>
              ))}
            </ul>
            {downloadError && <Problem>{downloadError}</Problem>}
            <p className="text-xs text-muted">
              {data.downloads_remaining != null &&
                `${data.downloads_remaining} download${data.downloads_remaining === 1 ? "" : "s"} left on this link. `}
              Please don't share this link; request your own instead.
            </p>
          </>
        )}
      </Card>
    </>
  );
}
