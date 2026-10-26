import { BadgeCheck, Library, Mail, Receipt, UserRound } from "lucide-react";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Link, useLocation, useNavigate } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { InputField } from "@/components/ui/FormField";
import { routes } from "@/config/navigation";
import { customerSignedIn, customerSignedOut } from "@/store/slices/customerSlice";
import { AccountShell } from "../AccountShell";
import { LibraryItems } from "../LibraryItems";
import { fieldErrors, useLoad } from "../hooks";
import { PasswordField } from "../PasswordField";
import { RequireCustomer } from "../RequireCustomer";
import { authErrorMessage } from "../authMessages";
import { ResendVerification } from "./AuthPages";

const STATUS_LABELS = {
  pending: "Pending",
  awaiting_payment: "Awaiting payment",
  paid: "Paid",
  failed: "Payment failed",
  cancelled: "Cancelled",
  partially_refunded: "Partially refunded",
  refunded: "Refunded",
};

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
    : "";

function Card({ title, icon: Icon, children, action }) {
  return (
    <section className="flex flex-col rounded-2xl border border-charcoal/10 bg-white p-6">
      <h2 className="flex items-center gap-2 text-lg font-medium">
        {Icon && <Icon aria-hidden className="size-5 text-sage-700" />}
        {title}
      </h2>
      <div className="mt-3 flex-1 text-sm">{children}</div>
      {action && <div className="mt-4">{action}</div>}
    </section>
  );
}

function RecentLibrary() {
  const shopApi = useShopApi();
  const { data, error, loading } = useLoad(() => shopApi.library(), []);
  if (loading) return <p className="text-muted">Loading…</p>;
  if (error) return <p className="text-red-800">We couldn't load your library.</p>;
  const active = data.filter((i) => i.status === "active" && !i.duplicate);
  if (!active.length) return <p className="text-muted">No purchases or free resources yet.</p>;
  return (
    <>
      <p className="text-muted">
        {active.length} {active.length === 1 ? "item" : "items"} ready to download
      </p>
      <ul className="mt-2 space-y-1">
        {active.slice(0, 3).map((i) => (
          <li key={i.id} className="truncate font-medium">
            {i.product.title}
          </li>
        ))}
      </ul>
    </>
  );
}

function RecentOrders() {
  const shopApi = useShopApi();
  const { data, error, loading } = useLoad(() => shopApi.orders(), []);
  if (loading) return <p className="text-muted">Loading…</p>;
  if (error) return <p className="text-red-800">We couldn't load your orders.</p>;
  if (!data.length) return <p className="text-muted">You haven't placed any orders yet.</p>;
  return (
    <ul className="divide-y divide-charcoal/10">
      {data.slice(0, 3).map((o) => (
        <li key={o.id} className="flex items-baseline justify-between gap-3 py-2">
          <span>
            <span className="font-medium">{o.number}</span>
            <span className="block text-muted">
              {formatDate(o.created_at)} · {STATUS_LABELS[o.status] ?? o.status}
              {o.test_mode ? " (test)" : ""}
            </span>
          </span>
          <span className="font-semibold">{o.total.formatted}</span>
        </li>
      ))}
    </ul>
  );
}

const NEWSLETTER_STATUS = {
  subscribed: "You're subscribed.",
  pending: "Waiting for you to confirm by email.",
  unsubscribed: "You're unsubscribed.",
  none: "You're not subscribed.",
};

function NewsletterSummary() {
  const shopApi = useShopApi();
  const { data, error, loading } = useLoad(() => shopApi.accountNewsletter(), []);
  if (loading) return <p className="text-muted">Loading…</p>;
  if (error || !data) return <p className="text-muted">Newsletter details are unavailable.</p>;
  if (!data.available && data.status === "none")
    return <p className="text-muted">{data.name} isn't open for sign-ups yet.</p>;
  return (
    <p>
      <span className="font-medium">{data.name}:</span>{" "}
      {NEWSLETTER_STATUS[data.status] ?? data.status}
    </p>
  );
}

function Overview({ customer }) {
  const location = useLocation();
  const welcome = location.state?.welcome;
  return (
    <div className="space-y-6">
      {welcome && (
        <p role="status" className="rounded-2xl bg-sage-50 p-4">
          Welcome! Your account is ready.
          {!customer.email_verified && " We've emailed you a link to confirm your address."}
          {location.state?.newsletter === "check_email" &&
            " Check your inbox to confirm your newsletter subscription too."}
        </p>
      )}
      {!customer.email_verified && (
        <section
          aria-labelledby="verify-heading"
          className="rounded-2xl border border-gold-300 bg-gold-100/50 p-5"
        >
          <h2 id="verify-heading" className="font-medium">
            Please confirm your email address
          </h2>
          <p className="mt-1 text-sm">
            We sent a link to <span className="font-medium">{customer.email}</span>. You need a
            confirmed address to buy products. Can't find it?
          </p>
          <div className="mt-3">
            <ResendVerification signedIn />
          </div>
        </section>
      )}
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        <Card
          title="Profile"
          icon={UserRound}
          action={
            <Link to={routes.accountSettings} className="text-sm underline underline-offset-4">
              Edit profile and security
            </Link>
          }
        >
          <p className="font-medium">{customer.display_name || "No name set"}</p>
          <p className="break-all text-muted">{customer.email}</p>
          <p className="mt-2 flex items-center gap-1.5">
            {customer.email_verified ? (
              <>
                <BadgeCheck aria-hidden className="size-4 text-sage-700" /> Email confirmed
              </>
            ) : (
              "Email not confirmed yet"
            )}
          </p>
          {customer.created_at && (
            <p className="mt-1 text-muted">Member since {formatDate(customer.created_at)}</p>
          )}
        </Card>
        <Card
          title="My library"
          icon={Library}
          action={
            <Link to={routes.accountLibrary} className="text-sm underline underline-offset-4">
              Open your library
            </Link>
          }
        >
          <RecentLibrary />
        </Card>
        <Card
          title="Recent orders"
          icon={Receipt}
          action={
            <Link to={routes.accountOrders} className="text-sm underline underline-offset-4">
              All orders and receipts
            </Link>
          }
        >
          <RecentOrders />
        </Card>
        <Card
          title="Newsletter"
          icon={Mail}
          action={
            <Link to={routes.accountSettings} className="text-sm underline underline-offset-4">
              Newsletter preferences
            </Link>
          }
        >
          <NewsletterSummary />
        </Card>
      </div>
    </div>
  );
}

export function AccountOverviewPage() {
  return (
    <RequireCustomer>
      {(customer) => (
        <AccountShell
          title={customer.display_name ? `Hello, ${customer.display_name}` : "Your account"}
          path={routes.account}
        >
          <Overview customer={customer} />
        </AccountShell>
      )}
    </RequireCustomer>
  );
}

function LibraryList() {
  const shopApi = useShopApi();
  const { data: items, error, loading, reload } = useLoad(() => shopApi.library(), []);
  if (loading)
    return (
      <p role="status" className="text-muted">
        Loading your library…
      </p>
    );
  if (error) return <ErrorState title="We couldn't load your library" onRetry={reload} />;
  if (!items.length) {
    return (
      <EmptyState
        icon={Library}
        title="Nothing here yet"
        description="Purchases and free resources appear here once they're confirmed."
        action={<ButtonLink to={routes.shop}>Browse the shop</ButtonLink>}
      />
    );
  }
  return (
    <>
      <p className="mb-6 max-w-2xl text-sm text-muted">
        Each download link is created when you press Download and expires after a few minutes, so
        please download from here rather than sharing links. You always get the latest version of
        each file, plus the edition you originally received.
      </p>
      <LibraryItems
        items={items}
        authorize={(item, version) => shopApi.authorizeDownload(item.id, version.version_id)}
      />
    </>
  );
}

/** Guest-checkout purchases join an account only once its email is confirmed. The note is
 * the same for every unconfirmed account (it never says whether such purchases exist). */
function UnconfirmedNote() {
  return (
    <div role="note" className="mb-6 rounded-2xl bg-gold-100/60 p-5 text-sm">
      <p className="font-medium">Bought something without an account?</p>
      <p className="mt-1">
        Purchases made with guest checkout using this email address appear here once you confirm
        your email. Until then, the download link we emailed you keeps working.
      </p>
      <div className="mt-3">
        <ResendVerification signedIn />
      </div>
    </div>
  );
}

export function AccountLibraryPage() {
  return (
    <RequireCustomer>
      {(customer) => (
        <AccountShell title="Your library" path={routes.accountLibrary}>
          {!customer.email_verified && <UnconfirmedNote />}
          <LibraryList />
        </AccountShell>
      )}
    </RequireCustomer>
  );
}

function OrderList() {
  const shopApi = useShopApi();
  const { data: orders, error, loading, reload } = useLoad(() => shopApi.orders(), []);
  const [open, setOpen] = useState(null);
  const receipt = useLoad(() => (open ? shopApi.order(open) : Promise.resolve(null)), [open]);
  if (loading)
    return (
      <p role="status" className="text-muted">
        Loading orders…
      </p>
    );
  if (error) return <ErrorState title="We couldn't load your orders" onRetry={reload} />;
  if (!orders.length) {
    return (
      <EmptyState
        icon={Receipt}
        title="No orders yet"
        description="When you buy something, the order and its receipt appear here."
      />
    );
  }
  return (
    <ul className="space-y-4">
      {orders.map((order) => (
        <li key={order.id} className="rounded-2xl border border-charcoal/10 bg-white p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-medium">Order {order.number}</h2>
              <p className="text-sm text-muted">
                {formatDate(order.created_at)} · {order.items.map((i) => i.title).join(", ")}
              </p>
            </div>
            <div className="text-right">
              <p className="font-semibold">{order.total.formatted}</p>
              <p className="text-sm">
                {STATUS_LABELS[order.status] ?? order.status}
                {order.test_mode ? " (test)" : ""}
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            {order.can_retry && (
              <ButtonLink size="sm" to={`${routes.checkoutComplete}?order=${order.id}`}>
                Complete payment
              </ButtonLink>
            )}
            {["paid", "partially_refunded", "refunded"].includes(order.status) && (
              <Button
                size="sm"
                variant="outline"
                aria-expanded={open === order.id}
                onClick={() => setOpen(open === order.id ? null : order.id)}
              >
                {open === order.id ? "Hide receipt" : "View receipt"}
              </Button>
            )}
          </div>
          {open === order.id && receipt.data?.receipt && (
            <div className="mt-4 rounded-xl bg-cream/60 p-4 text-sm">
              <p className="font-medium">Receipt {receipt.data.receipt.number}</p>
              <p className="text-muted">
                Paid {formatDate(receipt.data.receipt.paid_at)} via Paystack · reference{" "}
                {receipt.data.receipt.reference}
              </p>
              <ul className="mt-3 space-y-1">
                {receipt.data.receipt.items.map((i) => (
                  <li key={i.title} className="flex justify-between gap-4">
                    <span>{i.title}</span>
                    <span>{i.amount.formatted}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 flex justify-between border-t border-charcoal/10 pt-2 font-semibold">
                <span>Total paid</span>
                <span>{receipt.data.receipt.total.formatted}</span>
              </p>
              {order.refunded.amount_minor > 0 && (
                <p className="mt-1 flex justify-between text-muted">
                  <span>Refunded</span>
                  <span>{order.refunded.formatted}</span>
                </p>
              )}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function AccountOrdersPage() {
  return (
    <RequireCustomer>
      <AccountShell title="Orders & receipts" path={routes.accountOrders}>
        <OrderList />
      </AccountShell>
    </RequireCustomer>
  );
}

function NewsletterSettings() {
  const shopApi = useShopApi();
  const { data, error, loading, reload } = useLoad(() => shopApi.accountNewsletter(), []);
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState({ busy: false, message: "", error: null });
  const subscribe = async (event) => {
    event.preventDefault();
    setState({ busy: true, message: "", error: null });
    try {
      await shopApi.subscribeFromAccount(data.consent_version);
      setState({
        busy: false,
        message: "Check your inbox and confirm to start receiving emails.",
        error: null,
      });
      reload();
    } catch (err) {
      setState({ busy: false, message: "", error: err });
    }
  };
  return (
    <section className="space-y-3 rounded-2xl border border-charcoal/10 bg-white p-6">
      <h2 className="text-lg font-medium">Newsletter</h2>
      {loading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : error || !data ? (
        <p className="text-sm text-muted">Newsletter details are unavailable right now.</p>
      ) : (
        <>
          <p className="text-sm">
            <span className="font-medium">{data.name}:</span>{" "}
            {NEWSLETTER_STATUS[data.status] ?? data.status}
          </p>
          {data.preferences_token && (
            <Link
              to={`${routes.newsletterPreferences}#token=${data.preferences_token}`}
              className="inline-block text-sm underline underline-offset-4"
            >
              Manage topics or unsubscribe
            </Link>
          )}
          {data.status !== "none" && !data.preferences_token && (
            <p className="text-sm text-muted">
              Confirm your account email to manage your subscription here, or use the link at the
              bottom of any newsletter.
            </p>
          )}
          {data.available && ["none", "unsubscribed"].includes(data.status) && (
            <form onSubmit={subscribe} className="space-y-3">
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1 size-4 shrink-0 accent-sage-700"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span>{data.consent_text}</span>
              </label>
              <Button type="submit" size="sm" disabled={!consent || state.busy}>
                Subscribe
              </Button>
            </form>
          )}
          {state.message && (
            <p role="status" className="text-sm text-sage-800">
              {state.message}
            </p>
          )}
          {state.error && (
            <p role="alert" className="text-sm text-red-800">
              {authErrorMessage(state.error)}
            </p>
          )}
        </>
      )}
    </section>
  );
}

function downloadJson(data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "think-positive-always-account.json";
  link.click();
  URL.revokeObjectURL(link.href);
}

function Settings({ customer }) {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [name, setName] = useState(customer.display_name);
  const [passwords, setPasswords] = useState({
    current_password: "",
    new_password: "",
    confirm: "",
  });
  const [exportPassword, setExportPassword] = useState("");
  const [deletion, setDeletion] = useState({ password: "", confirm: false });
  const [msg, setMsg] = useState({});
  const run = async (key, action, success) => {
    setMsg((m) => ({ ...m, [key]: null }));
    try {
      const res = await action();
      setMsg((m) => ({ ...m, [key]: { ok: true, text: success(res) } }));
    } catch (error) {
      setMsg((m) => ({
        ...m,
        [key]: { ok: false, text: authErrorMessage(error), errors: fieldErrors(error) },
      }));
    }
  };
  const fail = (key, text) => setMsg((m) => ({ ...m, [key]: { ok: false, text, errors: {} } }));
  const note = (key) =>
    msg[key] && (
      <p
        role={msg[key].ok ? "status" : "alert"}
        className={`text-sm ${msg[key].ok ? "text-sage-800" : "text-red-800"}`}
      >
        {msg[key].text}
      </p>
    );
  return (
    <div className="grid max-w-3xl gap-8">
      <form
        className="space-y-4 rounded-2xl border border-charcoal/10 bg-white p-6"
        onSubmit={(e) => {
          e.preventDefault();
          run(
            "profile",
            () => shopApi.updateProfile({ display_name: name }),
            (res) => {
              dispatch(customerSignedIn(res.data.customer));
              return "Saved.";
            },
          );
        }}
      >
        <h2 className="text-lg font-medium">Profile</h2>
        <InputField
          label="Name"
          value={name}
          required
          maxLength={120}
          autoComplete="name"
          error={msg.profile?.errors?.display_name}
          onChange={(e) => setName(e.target.value)}
        />
        <div>
          <p className="text-sm font-medium">Email</p>
          <p className="text-sm text-muted">
            <span className="break-all">{customer.email}</span> ·{" "}
            {customer.email_verified ? "confirmed" : "not confirmed yet"}
          </p>
        </div>
        {note("profile")}
        <Button type="submit" size="sm">
          Save
        </Button>
      </form>
      <form
        className="space-y-4 rounded-2xl border border-charcoal/10 bg-white p-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (passwords.new_password !== passwords.confirm) {
            fail("password", "The new passwords don't match.");
            return;
          }
          run(
            "password",
            () =>
              shopApi.changePassword({
                current_password: passwords.current_password,
                new_password: passwords.new_password,
              }),
            () => {
              setPasswords({ current_password: "", new_password: "", confirm: "" });
              return "Password changed. Your other devices have been signed out.";
            },
          );
        }}
      >
        <h2 className="text-lg font-medium">Change password</h2>
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          required
          value={passwords.current_password}
          onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })}
        />
        <PasswordField
          label="New password"
          autoComplete="new-password"
          required
          hint="At least 12 characters, not too repetitive, without your email name."
          error={msg.password?.errors?.new_password}
          value={passwords.new_password}
          onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })}
        />
        <PasswordField
          label="Confirm new password"
          autoComplete="new-password"
          required
          value={passwords.confirm}
          onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })}
        />
        {note("password")}
        <Button type="submit" size="sm">
          Change password
        </Button>
      </form>
      <NewsletterSettings />
      <form
        className="space-y-4 rounded-2xl border border-charcoal/10 bg-white p-6"
        onSubmit={(e) => {
          e.preventDefault();
          run(
            "export",
            () => shopApi.exportData(exportPassword),
            (res) => {
              setExportPassword("");
              downloadJson(res.data);
              return "Your data file has been downloaded.";
            },
          );
        }}
      >
        <h2 className="text-lg font-medium">Your data</h2>
        <p className="text-sm text-muted">
          Download a copy of your profile, orders, library and download history. For your security,
          confirm your password first.
        </p>
        <PasswordField
          label="Your password"
          autoComplete="current-password"
          required
          value={exportPassword}
          onChange={(e) => setExportPassword(e.target.value)}
        />
        {note("export")}
        <Button type="submit" size="sm" variant="outline">
          Download my data
        </Button>
      </form>
      <form
        className="space-y-4 rounded-2xl border border-red-200 bg-white p-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (!deletion.confirm) {
            fail("delete", "Please tick the box to confirm you want to delete your account.");
            return;
          }
          run(
            "delete",
            () => shopApi.deleteAccount(deletion.password),
            () => {
              dispatch(customerSignedOut());
              navigate(routes.home);
              return "Your account has been deleted.";
            },
          );
        }}
      >
        <h2 className="text-lg font-medium">Delete account</h2>
        <p className="text-sm text-muted">
          Your personal details are removed and your library closes. Order and payment records are
          kept, as required for accounting and tax purposes. This can't be undone.
        </p>
        <PasswordField
          label="Confirm with your password"
          autoComplete="current-password"
          required
          value={deletion.password}
          onChange={(e) => setDeletion({ ...deletion, password: e.target.value })}
        />
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-1 size-4 accent-red-700"
            checked={deletion.confirm}
            onChange={(e) => setDeletion({ ...deletion, confirm: e.target.checked })}
          />
          <span>I understand that my account and library will be closed permanently.</span>
        </label>
        {note("delete")}
        <Button type="submit" size="sm" variant="outline" className="border-red-700 text-red-800">
          Delete my account
        </Button>
      </form>
    </div>
  );
}

export function AccountSettingsPage() {
  return (
    <RequireCustomer>
      {(customer) => (
        <AccountShell title="Settings" path={routes.accountSettings}>
          <Settings customer={customer} />
        </AccountShell>
      )}
    </RequireCustomer>
  );
}
