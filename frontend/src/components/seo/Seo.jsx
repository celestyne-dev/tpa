import { useContext, useEffect } from "react";
import { useSelector } from "react-redux";
import { selectSite } from "@/store/slices/siteSlice";
import { applyHead, buildHead } from "./head";
import { HeadContext } from "./headContext";

/**
 * Declares the page's title, description, canonical URL, Open Graph tags and
 * JSON-LD. Prerendered pages receive these in static HTML; client-side
 * navigation updates document.head.
 */
export function Seo(props) {
  const collector = useContext(HeadContext);
  const site = useSelector(selectSite)?.data;
  const head = buildHead({
    ...props,
    defaults: site?.seo,
    siteName: site?.name,
    branding: site?.branding,
  });
  collector?.setHead(head);
  const signature = JSON.stringify(head);

  useEffect(() => {
    applyHead(JSON.parse(signature));
  }, [signature]);

  return null;
}
