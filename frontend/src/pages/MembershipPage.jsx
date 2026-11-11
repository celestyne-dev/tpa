import { BookOpen, Check, Crown, FileText, GraduationCap } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { newKey, redirectTo } from "@/commerce/hooks";
import { useShopApi } from "@/components/products/shopApiContext";
import { UsdEstimate, UsdEstimateNote } from "@/components/products/UsdEstimate";
import { Seo } from "@/components/seo/Seo";
import { ButtonLink } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { PageLoading } from "@/components/ui/PageLoading";
import { Section } from "@/components/ui/Section";
import { routes } from "@/config/navigation";
import { useAccountStatus } from "@/hooks/useAccountStatus";
import { useMemberships } from "@/hooks/useContent";

const INTERVAL_LABEL = { month: "per month", year: "per year" };

function Prose({ text }) {
  return text
    .split(/\n{2,}/)
    .filter((p) => p.trim())
    .map((p) => (
      <p key={p.slice(0, 40)} className="mt-3 leading-relaxed text-muted first:mt-0">
        {p}
      </p>
    ));
}

/** The yearly saving against twelve monthly payments: percent (one decimal when it isn't
 * a whole number, e.g. 16.7) and the amount, or null when yearly isn't cheaper. */
export function yearlySaving(prices) {
  const month = prices.find((p) => p.interval === "month")?.price;
  const year = prices.find((p) => p.interval === "year")?.price;
  if (!month || !year || month.currency !== year.currency) return null;
  const full = month.amount_minor * 12;
  const savedMinor = full - year.amount_minor;
  if (savedMinor <= 0) return null;
  const percent = Math.round((savedMinor / full) * 1000) / 10;
  const amount = (savedMinor / 100).toLocaleString("en-US", {
    minimumFractionDigits: savedMinor % 100 ? 2 : 0,
    maximumFractionDigits: 2,
  });
  return { percent, amount: `${year.currency} ${amount}`, currency: year.currency };
}

function IncludedItem({ item }) {
  const Icon = item.kind === "course" ? GraduationCap : FileText;
  const to = item.course
    ? routes.course(item.course.slug)
    : item.slug
      ? routes.product(item.slug)
      : null;
  return (
    <li className="flex items-start gap-3">
      <Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-sage-700" />
      <span>
        {to ? (
          <Link to={to} className="font-medium underline-offset-4 hover:underline">
            {item.course?.title ?? item.title}
          </Link>
        ) : (
          <span className="font-medium">{item.title}</span>
        )}
        <span className="block text-sm text-muted">{item.type_label}</span>
      </span>
    </li>
  );
}

const JOIN_ERRORS = {
  email_verification_required:
    "Please confirm your email address first: open the link we emailed you, then come back to join.",
  already_member: "You're already a member.",
  price_changed: "This price has just changed. Please check the new price and try again.",
  subscription_pending: "Your last payment is still being confirmed. Please check back shortly.",
};

/**
 * Starts a test-mode membership checkout. The server re-checks the price, verified email
 * and existing memberships; access is only granted after Paystack confirms the payment.
 */
function JoinButtons({ plan, describedBy }) {
  const { status } = useAccountStatus();
  const shopApi = useShopApi();
  const navigate = useNavigate();
  const keys = useRef({});
  const [state, setState] = useState({ busy: null, error: "" });
  const join = async (price) => {
    // One key per price for this visit, so a double click or retry resumes the same checkout.
    keys.current[price.id] ??= newKey();
    setState({ busy: price.id, error: "" });
    try {
      const res = await shopApi.membershipCheckout({
        price_id: price.id,
        idempotency_key: keys.current[price.id],
        expected_amount_minor: price.price.amount_minor,
        currency: price.price.currency,
        accept_terms: true,
      });
      const url = res.data.checkout_url;
      if (url) redirectTo.go(url);
      else navigate(routes.accountMembership);
    } catch (err) {
      const code = err?.details?.code ?? err?.code;
      if (code === "already_member" || code === "subscription_pending") {
        navigate(routes.accountMembership);
        return;
      }
      if (code === "price_changed") keys.current = {};
      setState({
        busy: null,
        error:
          JOIN_ERRORS[code] ??
          err?.message ??
          "We couldn't start the checkout. Please try again in a moment.",
      });
    }
  };
  if (status !== "signed_in") return <AccountFirst describedBy={describedBy} />;
  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        {plan.prices.map((p) => (
          <button
            key={p.interval}
            type="button"
            onClick={() => join(p)}
            disabled={state.busy !== null}
            aria-describedby={describedBy}
            className="min-h-12 w-full rounded-full bg-charcoal px-6 py-3 font-medium text-ivory hover:bg-charcoal/90 disabled:opacity-60 sm:w-auto"
          >
            {state.busy === p.id
              ? "Starting checkout…"
              : `Join ${p.interval === "month" ? "monthly" : "yearly"} · ${p.price.formatted}`}
          </button>
        ))}
      </div>
      {state.error && (
        <p role="alert" className="mt-2 text-sm text-red-800">
          {state.error}{" "}
          {state.error === JOIN_ERRORS.email_verification_required && (
            <Link to={routes.account} className="underline underline-offset-4">
              Resend the email
            </Link>
          )}
        </p>
      )}
      <p className="mt-2 text-sm text-muted">
        You&apos;ll pay by debit or credit card on Paystack&apos;s secure page. By joining you agree
        to the{" "}
        <Link to={routes.terms} className="underline underline-offset-4">
          terms
        </Link>{" "}
        and the membership renews automatically until you cancel.
      </p>
    </div>
  );
}

/** Signed-out visitors: memberships need an account (to renew, cancel and reach the
 * included courses and resources), so joining starts with one. */
function AccountFirst({ describedBy }) {
  const next = encodeURIComponent(routes.membership);
  return (
    <div aria-describedby={describedBy}>
      <ol className="space-y-2 text-sm">
        <li>
          <span className="font-semibold">1.</span> Create your free account and confirm your email
          address.
        </li>
        <li>
          <span className="font-semibold">2.</span> Come back here, choose monthly or yearly and pay
          by card.
        </li>
      </ol>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row">
        <ButtonLink to={`${routes.register}?next=${next}`} className="w-full sm:w-auto">
          Create an account to join
        </ButtonLink>
        <ButtonLink
          to={`${routes.signIn}?next=${next}`}
          variant="outline"
          className="w-full sm:w-auto"
        >
          Log in
        </ButtonLink>
      </div>
    </div>
  );
}

/** How billing works: KES charge, card-only automatic renewal and cancellation terms. */
function BillingTerms({ prices }) {
  const currency = prices[0]?.price.currency ?? "KES";
  return (
    <section aria-labelledby="billing-terms" className="mt-8 rounded-2xl bg-cream p-5 sm:p-6">
      <h3 id="billing-terms" className="text-lg font-medium">
        How billing works
      </h3>
      <ul className="mt-3 space-y-2 text-sm leading-relaxed">
        <li>
          You are charged in {currency === "KES" ? "Kenyan shillings (KES)" : currency}, the price
          shown above. Any US dollar amount is an estimate; your bank or card provider converts the
          charge at its own rate and may add a fee.
        </li>
        <li>
          Memberships are paid by debit or credit card and renew automatically each month or year at
          the same price until you cancel. M-Pesa can&apos;t be used for automatic renewals; you can
          still use it to buy individual resources.
        </li>
        <li>
          Cancel any time from your account. You keep access until the end of the period you&apos;ve
          paid for and won&apos;t be charged again. See our{" "}
          <Link to={routes.refundPolicy} className="underline underline-offset-4">
            refund policy
          </Link>
          .
        </li>
      </ul>
    </section>
  );
}

function PlanCard({ plan, billing }) {
  const saving = yearlySaving(plan.prices);
  const headingId = `plan-${plan.slug}`;
  return (
    <Card className="p-6 sm:p-8">
      <article aria-labelledby={headingId}>
        <p className="flex items-center gap-2 text-sm font-semibold tracking-[0.14em] text-sage-700 uppercase">
          <Crown aria-hidden className="size-4" /> Membership
        </p>
        <h2 id={headingId} className="mt-2 text-3xl font-medium">
          {plan.name}
        </h2>
        {plan.tagline && <p className="mt-2 text-lg text-muted">{plan.tagline}</p>}

        <ul aria-label={`${plan.name} prices`} className="mt-6 grid gap-3 sm:grid-cols-2">
          {plan.prices.map((p) => (
            <li key={p.interval} className="rounded-2xl border border-charcoal/10 bg-white p-5">
              <p className="text-sm text-muted capitalize">
                {p.interval === "month" ? "Monthly" : "Yearly"}
              </p>
              <p className="mt-1 text-3xl font-semibold">
                {p.price.formatted}
                <span className="ml-1 text-base font-normal text-muted">
                  {INTERVAL_LABEL[p.interval]}
                </span>
              </p>
              <UsdEstimate money={p.price} className="mt-1 block" />
              {p.interval === "year" && saving && (
                <p className="mt-1 text-sm font-medium text-sage-800">
                  Save {saving.amount} a year (about {saving.percent}%) compared with monthly
                </p>
              )}
              <p className="mt-2 text-xs text-muted">
                Renews automatically {p.interval === "month" ? "every month" : "every year"} ·
                cancel any time
              </p>
            </li>
          ))}
        </ul>

        <div className="mt-6">
          {billing.available ? (
            <JoinButtons plan={plan} describedBy={`${headingId}-billing`} />
          ) : (
            <button
              type="button"
              disabled
              aria-describedby={`${headingId}-billing`}
              className="w-full cursor-not-allowed rounded-full bg-charcoal/15 px-6 py-3 font-medium text-charcoal/70 sm:w-auto"
            >
              Coming soon
            </button>
          )}
          <p id={`${headingId}-billing`} className="mt-2 text-sm text-muted">
            {billing.message}
          </p>
        </div>

        {plan.description && (
          <div className="mt-8">
            <Prose text={plan.description} />
          </div>
        )}

        {plan.benefits.length > 0 && (
          <section aria-label="Benefits" className="mt-8">
            <h3 className="text-lg font-medium">What members get</h3>
            <ul className="mt-3 space-y-2">
              {plan.benefits.map((b) => (
                <li key={b} className="flex items-start gap-2">
                  <Check aria-hidden className="mt-0.5 size-5 shrink-0 text-sage-700" />
                  {b}
                </li>
              ))}
            </ul>
          </section>
        )}

        <UsdEstimateNote className="mt-3" />

        {plan.included.length > 0 && (
          <section aria-label="Included courses and resources" className="mt-8">
            <h3 className="text-lg font-medium">Included courses and resources</h3>
            <ul className="mt-3 grid gap-4 sm:grid-cols-2">
              {plan.included.map((item) => (
                <IncludedItem key={`${item.type}-${item.title}`} item={item} />
              ))}
            </ul>
          </section>
        )}
        {plan.prices.length > 0 && <BillingTerms prices={plan.prices} />}
      </article>
    </Card>
  );
}

/**
 * Public membership page (prerendered). Plans, prices and benefits come from the CMS;
 * joining stays unavailable until subscription billing opens.
 */
export function MembershipPage() {
  const { data, isLoading, isError, retry } = useMemberships();
  return (
    <>
      <Seo
        title="Membership"
        description="Membership plans for Think Positive Always: written courses and premium resources."
        path={routes.membership}
      />
      <PageHeader
        eyebrow="Membership"
        title="Grow with the Think Positive Always membership"
        description="Written courses and premium resources, together in one plan."
        breadcrumbs={[
          { name: "Home", href: routes.home },
          { name: "Membership", href: routes.membership },
        ]}
      />
      <Section>
        {isLoading ? (
          <PageLoading />
        ) : isError ? (
          <ErrorState title="We couldn't load the membership plans" onRetry={retry} />
        ) : data.plans.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="Membership is coming soon"
            description="We're preparing the membership. In the meantime, explore our courses and resources."
            action={
              <Link to={routes.courses} className="font-medium underline underline-offset-4">
                Browse courses
              </Link>
            }
          />
        ) : (
          <div className="mx-auto max-w-4xl space-y-8">
            {!data.billing.available && (
              <Notice title="Joining opens soon">
                {data.billing.message} Anything you buy separately stays yours, whether or not you
                become a member.
              </Notice>
            )}
            {data.plans.map((plan) => (
              <PlanCard key={plan.slug} plan={plan} billing={data.billing} />
            ))}
          </div>
        )}
      </Section>
    </>
  );
}
