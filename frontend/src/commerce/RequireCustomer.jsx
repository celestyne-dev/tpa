import { Navigate, useLocation } from "react-router";
import { Container } from "@/components/ui/Container";
import { routes } from "@/config/navigation";
import { useCustomer } from "@/hooks/useShop";

/** Signed-in customers only; others are sent to log in and brought back afterwards. */
export function RequireCustomer({ children }) {
  const { customer, isLoading, sessionExpired } = useCustomer();
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
    // The API reports an ended session once; say so on the log-in page.
    const reason = sessionExpired ? "&reason=expired" : "";
    return <Navigate to={`${routes.signIn}?next=${next}${reason}`} replace />;
  }
  return typeof children === "function" ? children(customer) : children;
}
