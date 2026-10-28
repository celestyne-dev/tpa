import { Link } from "react-router";
import { useAdminApi } from "../../adminApiContext";
import { useAdminQuery } from "../../hooks/useAdminQuery";

/** Read-only note on product and course editors: which membership plans include it. */
export function MembershipInclusion({ productId }) {
  const api = useAdminApi();
  const { data } = useAdminQuery(
    () => (productId ? api.memberships.inclusion(productId) : Promise.resolve({ data: [] })),
    [productId],
  );
  if (!productId || !data) return null;
  return (
    <p className="text-xs text-muted" data-testid="membership-inclusion">
      {data.length === 0
        ? "Not included in any membership plan."
        : "Included in membership plans: "}
      {data.map((p, i) => (
        <span key={p.id}>
          {i > 0 && ", "}
          <Link to={`/admin/membership-plans/${p.id}`} className="underline underline-offset-2">
            {p.name}
          </Link>{" "}
          ({p.status})
        </span>
      ))}
    </p>
  );
}
