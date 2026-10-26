import { useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { Seo } from "@/components/seo/Seo";
import { Container } from "@/components/ui/Container";
import { legacyTarget } from "./legacyTarget";

/** Old account addresses redirect in the browser (the static site has no server redirect). */
export function LegacyAuthRedirect() {
  const { pathname, search, hash } = useLocation();
  const navigate = useNavigate();
  const target = legacyTarget(pathname, search, hash);
  useEffect(() => {
    navigate(target, { replace: true });
  }, [navigate, target]);
  return (
    <>
      <Seo title="Redirecting" path={pathname} noIndex />
      <Container className="py-24 text-center text-muted" role="status">
        This page has moved.{" "}
        <Link to={target} className="underline underline-offset-4">
          Continue
        </Link>
      </Container>
    </>
  );
}
