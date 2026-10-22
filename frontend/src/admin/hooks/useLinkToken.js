import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";

/**
 * Reads a one-time token from the URL fragment (#token=...) and then removes
 * it from the address bar and history. Fragments are never sent to servers or
 * in Referer headers.
 */
export function useLinkToken() {
  const location = useLocation();
  const navigate = useNavigate();
  const [token] = useState(() => new URLSearchParams(location.hash.slice(1)).get("token") ?? "");

  useEffect(() => {
    if (location.hash) navigate(location.pathname + location.search, { replace: true });
    // Only on first mount: the token has already been captured above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return token;
}
