import { Download, FileText, Library, Receipt } from "lucide-react";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Link, useNavigate } from "react-router";
import { ProductCover } from "@/components/products/ProductCover";
import { useShopApi } from "@/components/products/shopApiContext";
import { Button, ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { InputField } from "@/components/ui/FormField";
import { routes } from "@/config/navigation";
import { customerSignedIn, customerSignedOut } from "@/store/slices/customerSlice";
import { AccountShell } from "../AccountShell";
import { fieldErrors, redirectTo, useLoad } from "../hooks";
import { RequireCustomer } from "../RequireCustomer";

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

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function AccountOverviewPage() {
  return (
    <RequireCustomer>
      {(customer) => (
        <AccountShell
          title={customer.display_name ? `Hello, ${customer.display_name}` : "Your account"}
          path={routes.account}
        >
          <div className="grid gap-6 md:grid-cols-3">
            <section className="rounded-2xl border border-charcoal/10 bg-white p-6">
              <h2 className="text-lg font-medium">Account details</h2>
              <p className="mt-3 text-sm text-muted">Email</p>
              <p className="font-medium break-all">{customer.email}</p>
              <p className="mt-3 text-sm">
                {customer.email_verified ? "Email confirmed" : "Email not confirmed yet"}
              </p>
              <Link
                to={routes.accountSettings}
                className="mt-4 inline-block text-sm underline underline-offset-4"
              >
                Manage settings
              </Link>
            </section>
            <Link
              to={routes.accountLibrary}
              className="rounded-2xl border border-charcoal/10 bg-white p-6 hover:border-sage-600"
            >
              <Library aria-hidden className="size-6 text-sage-700" />
              <h2 className="mt-3 text-lg font-medium">Your library</h2>
              <p className="mt-1 text-sm text-muted">Download your purchases and free resources.</p>
            </Link>
            <Link
              to={routes.accountOrders}
              className="rounded-2xl border border-charcoal/10 bg-white p-6 hover:border-sage-600"
            >
              <Receipt aria-hidden className="size-6 text-sage-700" />
              <h2 className="mt-3 text-lg font-medium">Orders & receipts</h2>
              <p className="mt-1 text-sm text-muted">
                Payment status and receipts for every order.
              </p>
            </Link>
          </div>
        </AccountShell>
      )}
    </RequireCustomer>
  );
}

function LibraryList() {
  const shopApi = useShopApi();
  const { data: items, error, loading, reload } = useLoad(() => shopApi.library(), []);
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);
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
  const download = async (item, version) => {
    setBusy(version.version_id);
    setMessage(null);
    try {
      const res = await shopApi.authorizeDownload(item.id, version.version_id);
      redirectTo.go(res.data.url);
    } catch (err) {
      setMessage({ id: item.id, text: err.message });
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <p className="mb-6 max-w-2xl text-sm text-muted">
        Each download link is created when you press Download and expires after a few minutes, so
        please download from here rather than sharing links. You always get the latest version of
        each file, plus the edition you originally received.
      </p>
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
              <h2 className="text-xl font-medium">
                {item.product.slug ? (
                  <Link to={routes.product(item.product.slug)} className="hover:underline">
                    {item.product.title}
                  </Link>
                ) : (
                  item.product.title
                )}
              </h2>
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
              {item.status === "revoked" ? (
                <p className="mt-3 text-sm text-red-800">
                  Access ended{item.revoked_reason ? `: ${item.revoked_reason}` : ""}.
                </p>
              ) : item.includes.length > 0 ? (
                <p className="mt-3 text-sm">
                  Includes: {item.includes.join(", ")} (listed separately).
                </p>
              ) : item.files.length === 0 ? (
                <p className="mt-3 text-sm text-muted">
                  Files are being prepared. Please check back soon.
                </p>
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
                            {version.kind === "latest"
                              ? "Download"
                              : "Your original edition"} · {version.format} ·{" "}
                            {formatSize(version.size_bytes)}
                          </Button>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {message?.id === item.id && (
                <p role="alert" className="mt-3 text-sm text-red-800">
                  {message.text}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

export function AccountLibraryPage() {
  return (
    <RequireCustomer>
      <AccountShell title="Your library" path={routes.accountLibrary}>
        <LibraryList />
      </AccountShell>
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

function Settings({ customer }) {
  const shopApi = useShopApi();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [name, setName] = useState(customer.display_name);
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "" });
  const [deletePassword, setDeletePassword] = useState("");
  const [msg, setMsg] = useState({});
  const run = async (key, action, success) => {
    setMsg((m) => ({ ...m, [key]: null }));
    try {
      const res = await action();
      setMsg((m) => ({ ...m, [key]: { ok: true, text: success(res) } }));
    } catch (error) {
      setMsg((m) => ({
        ...m,
        [key]: { ok: false, text: error.message, errors: fieldErrors(error) },
      }));
    }
  };
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
          autoComplete="name"
          onChange={(e) => setName(e.target.value)}
        />
        {note("profile")}
        <Button type="submit" size="sm">
          Save
        </Button>
      </form>
      <form
        className="space-y-4 rounded-2xl border border-charcoal/10 bg-white p-6"
        onSubmit={(e) => {
          e.preventDefault();
          run(
            "password",
            () => shopApi.changePassword(passwords),
            () => {
              setPasswords({ current_password: "", new_password: "" });
              return "Password changed. Other devices have been signed out.";
            },
          );
        }}
      >
        <h2 className="text-lg font-medium">Security</h2>
        <InputField
          label="Current password"
          type="password"
          autoComplete="current-password"
          required
          value={passwords.current_password}
          onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })}
        />
        <InputField
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          hint="At least 12 characters."
          error={msg.password?.errors?.new_password}
          value={passwords.new_password}
          onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })}
        />
        {note("password")}
        <Button type="submit" size="sm">
          Change password
        </Button>
      </form>
      <section className="space-y-4 rounded-2xl border border-charcoal/10 bg-white p-6">
        <h2 className="text-lg font-medium">Your data</h2>
        <p className="text-sm text-muted">
          Download a copy of your profile, orders, library and download history.
        </p>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            run(
              "export",
              () => shopApi.exportData(),
              (res) => {
                const blob = new Blob([JSON.stringify(res.data, null, 2)], {
                  type: "application/json",
                });
                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.download = "think-positive-always-account.json";
                link.click();
                URL.revokeObjectURL(link.href);
                return "Your data file has been downloaded.";
              },
            )
          }
        >
          Download my data
        </Button>
        {note("export")}
      </section>
      <form
        className="space-y-4 rounded-2xl border border-red-200 bg-white p-6"
        onSubmit={(e) => {
          e.preventDefault();
          run(
            "delete",
            () => shopApi.deleteAccount(deletePassword),
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
          kept, as required for accounting and tax purposes.
        </p>
        <InputField
          label="Confirm with your password"
          type="password"
          autoComplete="current-password"
          required
          value={deletePassword}
          onChange={(e) => setDeletePassword(e.target.value)}
        />
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
