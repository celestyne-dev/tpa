import { useContext, useEffect } from "react";
import { applyHead, buildHead } from "./head";
import { HeadContext } from "./headContext";

/**
 * Declares the page's title, description, canonical URL, Open Graph tags and
 * JSON-LD. Prerendered pages receive these in static HTML; client-side
 * navigation updates document.head.
 */
export function Seo(props) {
  const collector = useContext(HeadContext);
  const head = buildHead(props);
  collector?.setHead(head);
  const signature = JSON.stringify(head);

  useEffect(() => {
    applyHead(JSON.parse(signature));
  }, [signature]);

  return null;
}
