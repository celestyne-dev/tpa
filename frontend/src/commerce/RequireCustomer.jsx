import { Navigate, useLocation } from "react-router";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { useCustomer } from "@/hooks/useShop";

/** Signed-in customers only; others are sent to sign in and brought back afterwards. */
export function RequireCustomer({ children }) {
  const { customer, isLoading } = useCustomer();
  const location = useLocation();
  if (isLoading) {
    return (
      <Container className="py-24 text-center text-muted" role="status">
        Loading your account…
      </Container>
    );
  }
  if (!customer) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${routes.signIn}?next=${next}`} replace />;
  }
  return typeof children === "function" ? children(customer) : children;
}
