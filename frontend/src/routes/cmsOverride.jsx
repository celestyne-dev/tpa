import { useSelector } from "react-redux";
import { CmsPage } from "@/pages/CmsPage";
import { selectSite } from "@/store/slices/siteSlice";

/**
 * Built-in pages a published CMS page may replace (see backend app/cms/routing.py):
 * once a CMS page is live at the same path, it is rendered instead.
 */
export function withCmsOverride(BuiltIn, path) {
  function CmsOverridable() {
    const overrides = useSelector(selectSite)?.data?.cms_overrides ?? [];
    return overrides.includes(path) ? <CmsPage path={path} /> : <BuiltIn />;
  }
  CmsOverridable.displayName = `CmsOverridable(${BuiltIn.name})`;
  return CmsOverridable;
}
