import { ShoppingBag, UserRound } from "lucide-react";
import { Link } from "react-router";
import { routes } from "@/config/navigation";
import { useCart } from "@/hooks/useShop";

/** Account and cart shortcuts. The count appears after hydration (the cart lives in the browser). */
export function HeaderShopLinks() {
  const count = useCart().length;
  const link =
    "relative grid size-10 place-items-center rounded-full text-charcoal transition-colors hover:bg-sage-100";
  return (
    <>
      <Link to={routes.account} className={link} aria-label="Your account">
        <UserRound aria-hidden className="size-5" />
      </Link>
      <Link
        to={routes.cart}
        className={link}
        aria-label={count ? `Cart, ${count} ${count === 1 ? "item" : "items"}` : "Cart"}
      >
        <ShoppingBag aria-hidden className="size-5" />
        {count > 0 && (
          <span
            aria-hidden
            className="absolute -top-0.5 -right-0.5 grid size-5 place-items-center rounded-full bg-gold-500 text-[0.7rem] font-semibold text-charcoal"
          >
            {count}
          </span>
        )}
      </Link>
    </>
  );
}
