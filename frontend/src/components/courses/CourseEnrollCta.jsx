import { ArrowRight, Check, ShoppingBag } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { cartStore } from "@/commerce/cartStore";
import { priceIn } from "@/commerce/currency";
import { useShopApi } from "@/components/products/shopApiContext";
import { Button, ButtonLink } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { useAccountStatus } from "@/hooks/useAccountStatus";
import { useCart } from "@/hooks/useShop";
import { priceable } from "./courseFormat";

/**
 * What a visitor can do on a course page. Prerendered HTML shows the neutral default;
 * once the browser knows who is signed in, enrolled learners see "Continue learning".
 * Prices and access always come from the server.
 */
export function CourseEnrollCta({ course, currency }) {
  const { status } = useAccountStatus();
  const shopApi = useShopApi();
  const navigate = useNavigate();
  const cart = useCart();
  const [learner, setLearner] = useState(null);
  const [action, setAction] = useState({ busy: false, error: "" });
  const here = routes.course(course.slug);

  useEffect(() => {
    if (status !== "signed_in") return undefined;
    let live = true;
    shopApi
      .learningStatus(course.slug)
      .then((res) => live && setLearner(res.data))
      .catch(() => live && setLearner(null));
    return () => {
      live = false;
    };
  }, [status, shopApi, course.slug]);

  if (learner?.enrolled && learner.access === "active") {
    return (
      <div className="space-y-3">
        <ButtonLink to={routes.learn(course.slug)} size="lg">
          {learner.completed ? "Review the course" : "Continue learning"}
          <ArrowRight aria-hidden className="size-5" />
        </ButtonLink>
        <p className="text-sm text-muted">
          You're enrolled{learner.progress ? ` · ${learner.progress}% complete` : ""}.
        </p>
      </div>
    );
  }
  if (course.availability === "coming_soon") {
    return (
      <div className="rounded-2xl bg-gold-100/50 p-5 text-sm">
        <p className="font-semibold">Coming soon</p>
        <p className="mt-1 text-muted">This course is still being written. No payment is taken.</p>
      </div>
    );
  }
  const unverified = learner && !learner.verified;
  const verifyNote = unverified && (
    <p role="status" className="rounded-xl bg-sage-50 p-3 text-sm">
      Confirm your email address to start learning.{" "}
      <Link to={routes.accountSettings} className="underline underline-offset-4">
        Resend the confirmation email
      </Link>
    </p>
  );

  if (course.is_free) {
    if (!course.enrollment_open && !learner?.enrolled) {
      return <p className="text-sm text-muted">Enrolment for this course is closed right now.</p>;
    }
    const enroll = async () => {
      if (status !== "signed_in") {
        navigate(`${routes.signIn}?next=${encodeURIComponent(here)}`);
        return;
      }
      setAction({ busy: true, error: "" });
      try {
        await shopApi.enroll(course.slug);
        navigate(routes.learn(course.slug));
      } catch (error) {
        setAction({ busy: false, error: error.message });
      }
    };
    return (
      <div className="space-y-3">
        <Button size="lg" onClick={enroll} disabled={action.busy || unverified}>
          {action.busy
            ? "Enrolling…"
            : learner?.access === "expired"
              ? "Enrol again"
              : "Enrol for free"}
        </Button>
        <p className="text-sm text-muted">
          Free with a Think Positive Always account. Your progress is saved as you read.
        </p>
        {verifyNote}
        {action.error && (
          <p role="alert" className="text-sm text-red-800">
            {action.error}
          </p>
        )}
      </div>
    );
  }

  // Premium: bought through the normal checkout (server-authoritative price).
  if (!course.purchasable || !course.product) {
    return <p className="text-sm text-muted">This course can't be bought right now.</p>;
  }
  const price = priceIn(priceable(course), currency);
  if (!price) {
    return (
      <p className="text-sm text-muted">
        Not sold in {currency}. Choose {course.prices.map((p) => p.currency).join(" or ")} to buy
        it.
      </p>
    );
  }
  const inCart = cart.some((item) => item.id === course.product.id);
  return (
    <div className="space-y-3">
      {learner?.access === "ended" && (
        <p role="status" className="rounded-xl bg-sage-50 p-3 text-sm">
          Your previous access to this course has ended.
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        {inCart ? (
          <ButtonLink to={routes.cart} size="lg" variant="outline">
            <Check aria-hidden className="size-5" /> In your cart — view cart
          </ButtonLink>
        ) : (
          <Button
            size="lg"
            onClick={() =>
              cartStore.add({
                id: course.product.id,
                slug: course.product.slug,
                title: course.title,
              })
            }
          >
            <ShoppingBag aria-hidden className="size-5" /> Add to cart
          </Button>
        )}
      </div>
      <p className="text-sm text-muted">
        Secure checkout. You can buy as a guest; to take the course you'll sign in (or create an
        account) with the purchase email and confirm it.
      </p>
      {verifyNote}
    </div>
  );
}
