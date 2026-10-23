import { createElement, lazy, Suspense } from "react";
import { PageLoading } from "@/components/ui/PageLoading";
import { loadCommerce } from "./loadCommerce";

/** A page from the lazily loaded customer chunk, wrapped in its loading state. */
export function lazyPage(name) {
  const Page = lazy(() => loadCommerce().then((m) => ({ default: m[name] })));
  function LazyCommercePage() {
    return createElement(Suspense, { fallback: createElement(PageLoading) }, createElement(Page));
  }
  LazyCommercePage.displayName = name;
  return LazyCommercePage;
}
