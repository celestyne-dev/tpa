import { ShoppingBag } from "lucide-react";
import { Link } from "react-router";
import { routes } from "@/config/navigation";
import { useCart } from "@/hooks/useShop";
import { AccountMenu } from "./AccountMenu";
import { HeaderIconLabel, headerIconClass } from "./HeaderIconLabel";

/** Account and cart shortcuts. The count appears after hydration (the cart lives in the browser). */
export function HeaderShopLinks() {
  const count = useCart().length;
  return (
    <>
      <AccountMenu />
      <Link
        to={routes.cart}
        className={headerIconClass}
        aria-label={count ? `Cart, ${count} ${count === 1 ? "item" : "items"}` : "Cart"}
      >
        <span className="relative">
          <ShoppingBag aria-hidden className="size-5" />
          {count > 0 && (
            <span
              aria-hidden
              className="absolute -top-2.5 -right-2.5 grid size-5 place-items-center rounded-full bg-gold-500 text-[0.7rem] font-semibold text-charcoal"
            >
              {count}
            </span>
          )}
        </span>
        <HeaderIconLabel>Cart</HeaderIconLabel>
      </Link>
    </>
  );
}
