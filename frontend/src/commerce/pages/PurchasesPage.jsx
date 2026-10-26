import { Mail } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { useShopApi } from "@/components/products/shopApiContext";
import { Seo } from "@/components/seo/Seo";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";
import { InputField } from "@/components/ui/FormField";
import { routes } from "@/config/navigation";
import { useAccountStatus } from "@/hooks/useAccountStatus";
import { fieldErrors } from "../hooks";
import { LibraryItems } from "../LibraryItems";

const TOKEN_KEY = "tpa-guest-access";

const STATUS_LABELS = {
  paid: "Paid",
  partially_refunded: "Partially refunded",
  refunded: "Refunded",
};

/**
 * The emailed link is /purchases#token=…: the fragment never reaches servers or logs. It is
 * moved into this tab's session storage and removed from the address bar, so it isn't kept
 * in history or shared by copying the URL.
 */
function takeToken() {
  if (typeof window === "undefined") return "";
  const fromHash = new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
  try {
    if (fromHash) {
      window.sessionStorage.setItem(TOKEN_KEY, fromHash);
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      return fromHash;
    }
    return window.sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return fromHash;
  }
}

function forgetToken() {
  try {
    window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // nothing stored
  }
}

const formatDate = (iso) =>
  iso
    ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
    : "";

function RecoveryForm({ expired }) {
  const shopApi = useShopApi();
  const [email, setEmail] = useState("");
  const [state, setState] = useState({ status: "idle", error: null });
  const submit = async (event) => {
    event.preventDefault();
    setState({ status: "busy", error: null });
    try {
      await shopApi.requestGuestAccess(email.trim());
      setState({ status: "sent", error: null });
    } catch (error) {
      setState({ status: "idle", error });
    }
  };
  if (state.status === "sent") {
    return (
      <div role="status" className="rounded-2xl bg-sage-50 p-5">
        <p className="flex items-center gap-2 font-medium">
          <Mail aria-hidden className="size-5 text-sage-700" /> Check your inbox
        </p>
        <p className="mt-2 text-sm text-muted">
          If purchases were made with guest checkout using that address, we've sent a new private
          link to it. It can take a few minutes to arrive; check your spam folder too.
        </p>
      </div>
    );
  }
  const errors = fieldErrors(state.error);
  return (
    <form onSubmit={submit} className="space-y-4">
      {expired && (
        <p role="alert" className="rounded-xl bg-gold-100/60 p-3 text-sm">
          This link has expired or was replaced by a newer one. Ask for a new link below.
        </p>
      )}
      <InputField
        label="Email address used at checkout"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={errors.email}
      />
      {state.error && !errors.email && (
        <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">
          {state.error.message}
        </p>
      )}
      <Button type="submit" className="w-full sm:w-auto" disabled={state.status === "busy"}>
        {state.status === "busy" ? "Sending…" : "Email me a link"}
      </Button>
    </form>
  );
}

function Purchases({ token, onExpired }) {
  const shopApi = useShopApi();
  const [state, setState] = useState({ data: null, loading: true });
  useEffect(() => {
    let alive = true;
    shopApi.guestLibrary(token).then(
      (res) => alive && setState({ data: res.data, loading: false }),
      () => alive && onExpired(),
    );
    return () => {
      alive = false;
    };
  }, [token, shopApi, onExpired]);
  if (state.loading) {
    return (
      <p role="status" className="text-muted">
        Opening your purchases…
      </p>
    );
  }
  const { data } = state;
  return (
    <div>
      <p className="text-muted">
        Purchases made with guest checkout by <strong>{data.email_hint}</strong>.
      </p>
      {data.library.length === 0 ? (
        <p className="mt-6">There's nothing to download yet.</p>
      ) : (
        <div className="mt-8">
          <h2 className="sr-only">Downloads</h2>
          <LibraryItems
            items={data.library}
            authorize={(item, version) =>
              shopApi.guestLibraryDownload(token, item.id, version.version_id)
            }
          />
        </div>
      )}
      {data.orders.length > 0 && (
        <section aria-labelledby="guest-orders" className="mt-10">
          <h2 id="guest-orders" className="text-xl font-medium">
            Orders
          </h2>
          <ul className="mt-4 divide-y divide-charcoal/10 rounded-2xl border border-charcoal/10 bg-white">
            {data.orders.map((order) => (
              <li key={order.number} className="flex flex-wrap justify-between gap-2 p-4 text-sm">
                <span>
                  <span className="font-medium">{order.number}</span> · {formatDate(order.paid_at)}
                  <span className="block text-muted">{order.items.join(", ")}</span>
                </span>
                <span className="text-right">
                  {order.total.formatted}
                  <span className="block text-muted">
                    {STATUS_LABELS[order.status] ?? order.status}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <div className="mt-10 rounded-2xl bg-sage-50 p-5 text-sm">
        <p className="font-medium">Want a permanent library?</p>
        <p className="mt-1 text-muted">
          Create an account with the same email address. Once you confirm it, these purchases appear
          in your library and you won't need emailed links.
        </p>
        <ButtonLink to={routes.register} variant="outline" size="sm" className="mt-3">
          Create an account
        </ButtonLink>
      </div>
    </div>
  );
}

export function PurchasesPage() {
  const [token, setToken] = useState(takeToken);
  const [expired, setExpired] = useState(false);
  const { status } = useAccountStatus();
  const onExpired = useCallback(() => {
    forgetToken();
    setToken("");
    setExpired(true);
  }, []);
  return (
    <>
      <Seo title="Your purchases" path={routes.purchases} noIndex />
      <Container size="narrow" className="py-14 sm:py-20">
        <h1 className="text-3xl font-medium sm:text-4xl">Your purchases</h1>
        {token ? (
          <div className="mt-6">
            <Purchases token={token} onExpired={onExpired} />
          </div>
        ) : (
          <div className="mt-4 max-w-xl">
            <p className="mb-6 text-muted">
              Bought without an account? Enter the email address you used at checkout and we'll send
              you a private link to download your purchases again.
            </p>
            <RecoveryForm expired={expired} />
            {status === "signed_in" ? (
              <p className="mt-8 text-sm">
                Purchases made while signed in are in{" "}
                <Link to={routes.accountLibrary} className="underline underline-offset-4">
                  your library
                </Link>
                .
              </p>
            ) : (
              <p className="mt-8 text-sm">
                Have an account?{" "}
                <Link
                  to={`${routes.signIn}?next=${encodeURIComponent(routes.accountLibrary)}`}
                  className="underline underline-offset-4"
                >
                  Log in to your library
                </Link>
                .
              </p>
            )}
          </div>
        )}
      </Container>
    </>
  );
}
