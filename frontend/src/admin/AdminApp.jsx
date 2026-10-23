import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Navigate, Route, Routes } from "react-router";
import { loadSession, selectAuth } from "@/store/slices/authSlice";
import { AdminIndex } from "./components/AdminIndex";
import { AdminLayout } from "./components/AdminLayout";
import { RequireAuth, RequirePermission } from "./components/Guards";
import { NotificationProvider } from "./components/Notifications";
import { AccountPage } from "./pages/AccountPage";
import { AnnouncementsPage } from "./pages/AnnouncementsPage";
import { BrandingPage } from "./pages/BrandingPage";
import { FooterPage } from "./pages/FooterPage";
import { HomepageBuilderPage } from "./pages/HomepageBuilderPage";
import { PagePreviewPage } from "./pages/PagePreviewPage";
import { PreviewFramePage } from "./pages/PreviewFramePage";
import { SharedSectionsPage } from "./pages/SharedSectionsPage";
import { ActivatePage } from "./pages/ActivatePage";
import { ArticleEditorPage } from "./pages/ArticleEditorPage";
import { ArticlePreviewPage } from "./pages/ArticlePreviewPage";
import { MediaLibraryPage } from "./pages/MediaLibraryPage";
import { PublishingPage } from "./pages/PublishingPage";
import { RedirectsPage } from "./pages/RedirectsPage";
import { SeoPage } from "./pages/SeoPage";
import { WorkflowPage } from "./pages/WorkflowPage";
import { ArticlesPage } from "./pages/ArticlesPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { LoginPage } from "./pages/LoginPage";
import { NavigationPage } from "./pages/NavigationPage";
import { PageEditorPage } from "./pages/PageEditorPage";
import { PagesPage } from "./pages/PagesPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { RoleEditorPage } from "./pages/RoleEditorPage";
import { RolesPage } from "./pages/RolesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TaxonomyPage } from "./pages/TaxonomyPage";
import { UsersPage } from "./pages/UsersPage";
import { CustomerDetailPage, CustomersPage } from "./pages/CustomersPage";
import { EntitlementsPage } from "./pages/EntitlementsPage";
import { OrderDetailPage } from "./pages/OrderDetailPage";
import { OrdersPage } from "./pages/OrdersPage";
import { PaymentSettingsPage } from "./pages/PaymentSettingsPage";
import { ProductCollectionsPage } from "./pages/ProductCollectionsPage";
import { ProductEditorPage } from "./pages/ProductEditorPage";
import { ProductPreviewPage } from "./pages/ProductPreviewPage";
import { BundlesPage, ProductsPage } from "./pages/ProductsPage";
import { RevenueReportPage } from "./pages/RevenueReportPage";
import {
  ARTICLE_ACCESS,
  PAGE_READ,
  REDIRECT_READ,
  ROLE_READ,
  SEO_READ,
  SETTINGS_ACCESS,
  SHARED_ACCESS,
  TAXONOMY_READ,
} from "./permissions";

/** `rule` is one permission key or a list of alternatives (any one suffices). */
const guarded = (rule, element) =>
  Array.isArray(rule) ? (
    <RequirePermission anyOf={rule}>{element}</RequirePermission>
  ) : (
    <RequirePermission permission={rule}>{element}</RequirePermission>
  );

/** Admin area (/admin/*). Hiding UI is a convenience; Flask authorises every request. */
export default function AdminApp() {
  const dispatch = useDispatch();
  const { status } = useSelector(selectAuth);

  useEffect(() => {
    if (status === "idle") dispatch(loadSession());
  }, [status, dispatch]);

  return (
    <NotificationProvider>
      <Routes>
        <Route path="login" element={<LoginPage />} />
        <Route path="activate" element={<ActivatePage />} />
        <Route path="reset-password" element={<ResetPasswordPage />} />
        {/* Full-screen private previews (no admin chrome; still require a session). */}
        <Route
          path="pages/:id/preview"
          element={<RequireAuth>{guarded(PAGE_READ, <PagePreviewPage />)}</RequireAuth>}
        />
        <Route
          path="products/:id/preview"
          element={<RequireAuth>{guarded("products.view", <ProductPreviewPage />)}</RequireAuth>}
        />
        <Route
          path="preview-frame/:id"
          element={<RequireAuth>{guarded(PAGE_READ, <PreviewFramePage />)}</RequireAuth>}
        />
        <Route
          element={
            <RequireAuth>
              <AdminLayout />
            </RequireAuth>
          }
        >
          <Route index element={<AdminIndex />} />
          <Route path="products" element={guarded("products.view", <ProductsPage />)} />
          <Route path="products/:id" element={guarded("products.view", <ProductEditorPage />)} />
          <Route path="bundles" element={guarded("products.view", <BundlesPage />)} />
          <Route
            path="product-collections"
            element={guarded("products.view", <ProductCollectionsPage />)}
          />
          <Route path="orders" element={guarded("orders.view", <OrdersPage />)} />
          <Route path="orders/:id" element={guarded("orders.view", <OrderDetailPage />)} />
          <Route path="customers" element={guarded("customers.view", <CustomersPage />)} />
          <Route path="customers/:id" element={guarded("customers.view", <CustomerDetailPage />)} />
          <Route
            path="entitlements"
            element={guarded(["entitlements.view", "downloads.audit"], <EntitlementsPage />)}
          />
          <Route path="reports/revenue" element={guarded("finance.view", <RevenueReportPage />)} />
          <Route
            path="payments"
            element={guarded(
              ["payments.configure", "payments.view_events"],
              <PaymentSettingsPage />,
            )}
          />
          <Route path="articles" element={guarded(ARTICLE_ACCESS, <ArticlesPage />)} />
          <Route path="articles/new" element={guarded("articles.create", <ArticleEditorPage />)} />
          <Route
            path="articles/:id/edit"
            element={guarded(ARTICLE_ACCESS, <ArticleEditorPage />)}
          />
          <Route
            path="articles/:id/preview"
            element={guarded("articles.preview", <ArticlePreviewPage />)}
          />
          <Route path="workflow" element={guarded(ARTICLE_ACCESS, <WorkflowPage />)} />
          <Route path="media" element={guarded("media.view", <MediaLibraryPage />)} />
          <Route path="seo" element={guarded(SEO_READ, <SeoPage />)} />
          <Route path="redirects" element={guarded(REDIRECT_READ, <RedirectsPage />)} />
          <Route path="publishing" element={guarded("publishing.view", <PublishingPage />)} />
          <Route path="topics" element={guarded(TAXONOMY_READ, <TaxonomyPage kind="topics" />)} />
          <Route path="tags" element={guarded(TAXONOMY_READ, <TaxonomyPage kind="tags" />)} />
          <Route path="authors" element={guarded(TAXONOMY_READ, <TaxonomyPage kind="authors" />)} />
          <Route path="homepage" element={guarded("homepage.view", <HomepageBuilderPage />)} />
          <Route path="pages" element={guarded("pages.view", <PagesPage />)} />
          <Route path="pages/:id" element={guarded(PAGE_READ, <PageEditorPage />)} />
          <Route path="shared-sections" element={guarded(SHARED_ACCESS, <SharedSectionsPage />)} />
          <Route path="navigation" element={guarded("navigation.manage", <NavigationPage />)} />
          <Route path="footer" element={guarded("settings.manage", <FooterPage />)} />
          <Route path="branding" element={guarded("branding.manage", <BrandingPage />)} />
          <Route
            path="announcements"
            element={guarded("announcements.manage", <AnnouncementsPage />)}
          />
          <Route path="settings" element={guarded(SETTINGS_ACCESS, <SettingsPage />)} />
          <Route path="users" element={guarded("users.view", <UsersPage />)} />
          <Route path="roles" element={guarded(ROLE_READ, <RolesPage />)} />
          <Route path="roles/new" element={guarded("roles.manage", <RoleEditorPage />)} />
          <Route path="roles/:id" element={guarded(ROLE_READ, <RoleEditorPage />)} />
          <Route path="audit-log" element={guarded("audit.view", <AuditLogPage />)} />
          <Route path="account" element={<AccountPage />} />
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Route>
      </Routes>
    </NotificationProvider>
  );
}
