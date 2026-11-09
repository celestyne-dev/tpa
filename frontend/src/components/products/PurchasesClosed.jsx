/**
 * Shown instead of buy buttons while purchases aren't open (no payment provider is set up
 * yet: site.shop.purchases_open is false), so nobody starts a checkout that can't take a
 * payment. Free products stay available.
 */
export function PurchasesClosed() {
  return (
    <div role="status" className="rounded-2xl bg-gold-100/50 p-5 text-sm text-charcoal">
      <p className="font-semibold">Purchases aren't open yet</p>
      <p className="mt-1 text-muted">
        Online payments haven't been set up yet, so this can't be bought for now. No payment is
        taken.
      </p>
    </div>
  );
}
