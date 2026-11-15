import { Link2, Unplug } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDate } from "@/utils/format";
import { useAdminApi } from "../../adminApiContext";
import { AdminPageHeader } from "../../components/AdminPageHeader";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { useNotify } from "../../components/notifyContext";
import { StatusBadge } from "../../components/StatusBadge";
import { useAdminQuery } from "../../hooks/useAdminQuery";
import { usePermissions } from "../../hooks/usePermissions";
import { InstagramImport } from "./InstagramImport";
import { leaveTo } from "./leave";
import { PLATFORM_LABELS } from "./socialLinks";

const NOTES = {
  pinterest: {
    needs:
      "A Pinterest business account and a Pinterest developer app with this redirect address registered.",
    does: "Creates image Pins from Media Library images on a board you choose. Each Pin links to the article, quote collection or page it belongs to.",
  },
  instagram: {
    needs:
      "An Instagram professional (Business or Creator) account and a Meta app using Instagram Login with this redirect address registered.",
    does: "Imports your own Instagram images into the Media Library and publishes single-image feed posts. Feed captions cannot contain clickable links.",
  },
};

function Row({ label, children }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[11rem_1fr]">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-charcoal">{children}</dd>
    </div>
  );
}

function Setup({ item }) {
  return (
    <div role="note" className="rounded-lg border border-gold-300 bg-gold-100/50 p-3 text-sm">
      <p className="font-medium text-charcoal">
        {item.label} is not set up on the server yet. The rest of the CMS is unaffected.
      </p>
      <p className="mt-1 text-ink">
        Whoever manages the server needs to add these settings, then restart the site:
      </p>
      <ul className="mt-1 list-disc pl-5 font-mono text-xs">
        {item.setup.missing.map((name) => (
          <li key={name}>{name}</li>
        ))}
      </ul>
    </div>
  );
}

function AccountCard({ item, canConnect, onChanged }) {
  const api = useAdminApi();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const account = item.account;
  const expired = account && account.status !== "connected";

  const connect = async () => {
    setBusy(true);
    try {
      const res = await api.social.connect(item.platform);
      leaveTo(res.data.authorize_url);
    } catch (err) {
      notify(err.message, "error");
      setBusy(false);
    }
  };
  const disconnect = async () => {
    setBusy(true);
    try {
      await api.social.disconnect(item.platform);
      notify(`${item.label} disconnected.`);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };

  return (
    <section
      aria-labelledby={`${item.platform}-heading`}
      className="rounded-xl border border-charcoal/10 bg-white p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={`${item.platform}-heading`} className="text-xl font-medium">
          {item.label}
        </h2>
        <StatusBadge
          status={!account ? "inactive" : expired ? "failed" : "active"}
          label={!account ? "Not connected" : expired ? "Reconnect needed" : "Connected"}
        />
      </div>
      <p className="mt-2 text-sm text-ink">{NOTES[item.platform].does}</p>

      <div className="mt-4 grid gap-4">
        {!item.setup.ready && <Setup item={item} />}
        {account && (
          <dl className="grid gap-2 text-sm">
            <Row label="Account">
              {account.profile_url ? (
                <a
                  href={account.profile_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sage-800 underline"
                >
                  @{account.username}
                </a>
              ) : (
                account.username || account.external_id
              )}
              {account.account_type ? ` (${account.account_type.toLowerCase()})` : ""}
            </Row>
            <Row label="Connected">
              {formatDate(account.connected_at)}
              {account.connected_by ? ` by ${account.connected_by}` : ""}
            </Row>
            {account.access_expires_at && (
              <Row label="Authorisation renews by">
                {formatDate(account.access_expires_at)} (renewed automatically while connected)
              </Row>
            )}
            {account.missing_scopes?.length > 0 && (
              <Row label="Missing permissions">
                <span className="text-red-800">{account.missing_scopes.join(", ")}</span>. Reconnect
                and approve every permission.
              </Row>
            )}
            {account.last_error && (
              <Row label="Last problem">
                <span className="text-red-800">{account.last_error}</span>
              </Row>
            )}
          </dl>
        )}
        <dl className="grid gap-2 text-sm">
          <Row label="You need">{NOTES[item.platform].needs}</Row>
          <Row label="Redirect address">
            <code className="text-xs break-all">{item.redirect_uri}</code>
          </Row>
          <Row label="Permissions requested">
            <code className="text-xs">{item.scopes_requested.join(", ")}</code>
          </Row>
        </dl>

        {canConnect ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy || !item.setup.ready} onClick={connect}>
              <Link2 aria-hidden />
              {account ? `Reconnect ${item.label}` : `Connect ${item.label}`}
            </Button>
            {account && (
              <Button variant="outline" size="sm" disabled={busy} onClick={() => setConfirm(true)}>
                <Unplug aria-hidden />
                Disconnect
              </Button>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted">
            Only a Super Admin can connect or disconnect accounts.
          </p>
        )}
      </div>
      <ConfirmDialog
        open={confirm}
        title={`Disconnect ${item.label}?`}
        message="Scheduled posts for this account will fail until it is connected again. Posts already published stay on the platform."
        confirmLabel="Disconnect"
        tone="danger"
        busy={busy}
        onConfirm={disconnect}
        onCancel={() => setConfirm(false)}
      />
    </section>
  );
}

function PinterestVerification() {
  return (
    <section
      aria-labelledby="verify-heading"
      className="rounded-xl border border-charcoal/10 bg-white p-5 text-sm"
    >
      <h2 id="verify-heading" className="text-xl font-medium">
        Claim the website on Pinterest
      </h2>
      <p className="mt-2 text-ink">
        The verification tag is added to every public page automatically from{" "}
        <Link to="/admin/settings" className="text-sage-800 underline">
          Settings › Technical › Pinterest verification code
        </Link>
        . It is part of the published HTML, so it stays in place after every publish.
      </p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-ink">
        <li>In Pinterest, open Settings › Claimed accounts › Websites › Claim.</li>
        <li>
          Choose “Add HTML tag”. If the code shown differs from the one saved in Settings, paste the
          new tag there, save, and wait for the site to republish.
        </li>
        <li>Enter the website address and press Verify.</li>
      </ol>
      <p className="mt-3 text-muted">
        Pinterest confirms the claim on its side; the CMS cannot see whether it has been approved.
      </p>
    </section>
  );
}

export function IntegrationsPage() {
  const api = useAdminApi();
  const { can } = usePermissions();
  const { data, error, loading, reload } = useAdminQuery(() => api.social.accounts(), []);
  const instagram = data?.find((a) => a.platform === "instagram");
  return (
    <>
      <AdminPageHeader
        title="Integrations"
        description="Connect the site's own Pinterest and Instagram accounts. Nothing is posted automatically: every Pin and post is created by a person in Social publishing."
        breadcrumbs={[{ label: "Integrations" }]}
      />
      {error ? (
        <ErrorState title="We couldn't load the integrations" onRetry={reload} />
      ) : loading && !data ? (
        <p role="status">Loading…</p>
      ) : (
        <div className="grid gap-6">
          {data.map((item) => (
            <AccountCard
              key={item.platform}
              item={item}
              canConnect={can("social.connect")}
              onChanged={reload}
            />
          ))}
          {instagram?.connected && can("social.publish", "media.upload") && <InstagramImport />}
          <PinterestVerification />
        </div>
      )}
    </>
  );
}

/** Where Pinterest / Instagram send the administrator back after they approve. */
export function IntegrationCallbackPage() {
  const api = useAdminApi();
  const notify = useNotify();
  const navigate = useNavigate();
  const { platform } = useParams();
  const [params] = useSearchParams();
  const [failure, setFailure] = useState(null);
  const sent = useRef(null);
  const label = PLATFORM_LABELS[platform] ?? "The platform";
  // Instagram appends "#_" to the code in some browsers.
  const code = (params.get("code") ?? "").replace(/#_$/, "");
  const state = params.get("state") ?? "";
  const refused = params.get("error");
  const reason = params.get("error_description") ?? refused;

  const known = Boolean(PLATFORM_LABELS[platform]);
  const upfront = !known
    ? "Unknown platform."
    : refused
      ? `The connection was not approved on ${label} (${reason}).`
      : !code
        ? `${label} did not return an authorisation code.`
        : null;

  useEffect(() => {
    if (upfront) return;
    const key = `${platform}:${state}:${code}`;
    if (sent.current === key) return; // an authorisation code can only be used once
    sent.current = key;
    api.social
      .callback(platform, { code, state })
      .then(() => {
        notify(`${label} connected.`);
        navigate("/admin/integrations", { replace: true });
      })
      .catch((err) => setFailure(err.message));
  }, [api, code, label, navigate, notify, platform, state, upfront]);
  const problem = upfront ?? failure;

  return (
    <>
      <AdminPageHeader
        title={`Connecting ${label}`}
        breadcrumbs={[{ label: "Integrations", to: "/admin/integrations" }, { label }]}
      />
      {problem ? (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm">
          <p className="font-medium text-red-900">{label} was not connected.</p>
          <p className="mt-1 text-red-900">{problem}</p>
          <p className="mt-3">
            <Link to="/admin/integrations" className="text-sage-800 underline">
              Back to Integrations
            </Link>
          </p>
        </div>
      ) : (
        <p role="status">Finishing the connection…</p>
      )}
    </>
  );
}
