import { Check, Download, ShoppingBag } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { cartStore } from "@/commerce/cartStore";
import { priceIn } from "@/commerce/currency";
import { Button, ButtonLink } from "@/components/ui/Button";
import { routes } from "@/config/navigation";
import { useCart } from "@/hooks/useShop";
import { useShopApi } from "./shopApiContext";

/**
 * Purchase actions. Only products the server reports as purchasable get them:
 * drafts, coming-soon, archived or incomplete products never show a buy button.
 */
export function ProductActions({ product, currency }) {
  const navigate = useNavigate();
  const cart = useCart();
  const shopApi = useShopApi();
  const [claim, setClaim] = useState({ status: "idle", message: "" });
  const inCart = cart.some((item) => item.id === product.id);

  if (product.availability === "coming-soon") {
    return (
      <div className="rounded-2xl bg-gold-100/50 p-5 text-sm text-charcoal">
        <p className="font-semibold">Coming soon</p>
        <p className="mt-1 text-muted">
          This title is still being written, so it can't be bought yet. No payment is taken for
          coming-soon products.
        </p>
      </div>
    );
  }
  if (!product.purchasable) {
    return <p className="text-sm text-muted">This product isn't available right now.</p>;
  }
  if (product.is_free) {
    const get = async () => {
      setClaim({ status: "loading", message: "" });
      try {
        await shopApi.claimFree(product.id);
        navigate(routes.accountLibrary);
      } catch (error) {
        if (error.status === 401) {
          navigate(`${routes.signIn}?next=${encodeURIComponent(routes.product(product.slug))}`);
          return;
        }
        setClaim({ status: "error", message: error.message });
      }
    };
    return (
      <div className="space-y-3">
        <Button size="lg" onClick={get} disabled={claim.status === "loading"}>
          <Download aria-hidden className="size-5" />
          {claim.status === "loading" ? "Adding to your library…" : "Get it free"}
        </Button>
        <p className="text-sm text-muted">Free with an account. It stays in your library.</p>
        {claim.status === "error" && (
          <p role="alert" className="text-sm text-red-800">
            {claim.message}
          </p>
        )}
      </div>
    );
  }
  const price = priceIn(product, currency);
  if (!price) {
    return (
      <p className="text-sm text-muted">
        Not sold in {currency}. Choose {product.prices.map((p) => p.currency).join(" or ")} above to
        buy it.
      </p>
    );
  }
  const add = () => cartStore.add(product);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        {inCart ? (
          <ButtonLink to={routes.cart} size="lg" variant="outline">
            <Check aria-hidden className="size-5" /> In your cart — view cart
          </ButtonLink>
        ) : (
          <Button size="lg" variant="outline" onClick={add}>
            <ShoppingBag aria-hidden className="size-5" /> Add to cart
          </Button>
        )}
        <Button
          size="lg"
          onClick={() => {
            add();
            navigate(routes.checkout);
          }}
        >
          Buy now
        </Button>
      </div>
      <p className="text-sm text-muted">
        Instant digital download from your account library after payment is confirmed.{" "}
        <Link to={routes.terms} className="underline underline-offset-4">
          Terms apply
        </Link>
        .
      </p>
    </div>
  );
}
