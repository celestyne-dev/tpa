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
import { AutomationDetailPage, AutomationsPage } from "./pages/newsletter/AutomationsPage";
import { EmailSettingsPage } from "./pages/newsletter/EmailSettingsPage";
import { LeadMagnetsPage } from "./pages/newsletter/LeadMagnetsPage";
import { NewsletterEditorPage } from "./pages/newsletter/NewsletterEditorPage";
import { NewslettersPage } from "./pages/newsletter/NewslettersPage";
import { AffiliateLinksPage, AffiliatesPage } from "./pages/partnerships/AffiliatesPage";
import { MediaKitPage } from "./pages/partnerships/MediaKitPage";
import { PartnersPage, PartnershipInquiriesPage } from "./pages/partnerships/PartnersPage";
import { PartnershipReportsPage } from "./pages/partnerships/PartnershipReportsPage";
import { SponsorshipsPage } from "./pages/partnerships/SponsorshipsPage";
import { SubscriberDetailPage, SubscribersPage } from "./pages/newsletter/SubscribersPage";
import { ProductCollectionsPage } from "./pages/ProductCollectionsPage";
import { ProductEditorPage } from "./pages/ProductEditorPage";
import { ProductPreviewPage } from "./pages/ProductPreviewPage";
import { BundlesPage, ProductsPage } from "./pages/ProductsPage";
import { CourseEditorPage } from "./pages/courses/CourseEditorPage";
import { CoursePreviewPage } from "./pages/courses/CoursePreviewPage";
import { CoursesPage } from "./pages/courses/CoursesPage";
import { GradingDashboardPage } from "./pages/grading/GradingDashboardPage";
import { MembershipPlanEditorPage } from "./pages/memberships/MembershipPlanEditorPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { MembershipGrantsPage } from "./pages/memberships/MembershipGrantsPage";
import { MembershipPlansPage } from "./pages/memberships/MembershipPlansPage";
import { MembershipReportsPage } from "./pages/memberships/MembershipReportsPage";
import { MembershipSubscriptionDetailPage } from "./pages/memberships/MembershipSubscriptionDetailPage";
import { MembershipSubscriptionsPage } from "./pages/memberships/MembershipSubscriptionsPage";
import { SubmissionReviewPage } from "./pages/grading/SubmissionReviewPage";
import { QuestionBankPage } from "./pages/questionBanks/QuestionBankPage";
import { QuestionBanksPage } from "./pages/questionBanks/QuestionBanksPage";
import { ResourcesPage } from "./pages/ResourcesPage";
import { RevenueReportPage } from "./pages/RevenueReportPage";
import { StoragePage } from "./pages/StoragePage";
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

const SUBSCRIBER_READ = ["memberships.manage_subscriptions", "memberships.view"];
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
          <Route path="resources" element={guarded("products.view", <ResourcesPage />)} />
          <Route path="storage" element={guarded("storage.view", <StoragePage />)} />
          <Route path="courses" element={guarded("courses.view", <CoursesPage />)} />
          <Route path="courses/new" element={guarded("courses.create", <CoursesPage />)} />
          <Route path="courses/:id" element={guarded("courses.view", <CourseEditorPage />)} />
          <Route
            path="courses/:id/content"
            element={guarded("courses.view", <CourseEditorPage section="content" />)}
          />
          <Route
            path="courses/:id/assessments"
            element={guarded("courses.view", <CourseEditorPage section="assessments" />)}
          />
          <Route
            path="courses/:id/assignments"
            element={guarded("assignments.view", <CourseEditorPage section="assignments" />)}
          />
          <Route
            path="assignment-reviews"
            element={guarded("assignments.view_submissions", <GradingDashboardPage />)}
          />
          <Route
            path="assignment-reviews/:submissionId"
            element={guarded("assignments.view_submissions", <SubmissionReviewPage />)}
          />
          <Route
            path="membership-plans"
            element={guarded("memberships.view", <MembershipPlansPage />)}
          />
          <Route
            path="membership-plans/:planId"
            element={guarded("memberships.view", <MembershipPlanEditorPage />)}
          />
          {/* Server-side checks decide; read-only access also needs customers.view. */}
          <Route
            path="membership-subscriptions"
            element={guarded(SUBSCRIBER_READ, <MembershipSubscriptionsPage />)}
          />
          <Route
            path="membership-subscriptions/:subscriptionId"
            element={guarded(SUBSCRIBER_READ, <MembershipSubscriptionDetailPage />)}
          />
          <Route
            path="membership-grants"
            element={guarded(SUBSCRIBER_READ, <MembershipGrantsPage />)}
          />
          <Route path="analytics" element={guarded("analytics.view", <AnalyticsPage />)} />
          <Route
            path="membership-reports"
            element={guarded("memberships.view_reports", <MembershipReportsPage />)}
          />
          <Route
            path="question-banks"
            element={guarded("question_banks.view", <QuestionBanksPage />)}
          />
          <Route
            path="question-banks/:bankId"
            element={guarded("question_banks.view", <QuestionBankPage />)}
          />
          <Route
            path="courses/:id/enrollments"
            element={guarded(
              "courses.view_enrollments",
              <CourseEditorPage section="enrollments" />,
            )}
          />
          <Route
            path="courses/:id/preview"
            element={guarded("courses.view", <CoursePreviewPage />)}
          />
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
          <Route path="subscribers" element={guarded("subscribers.view", <SubscribersPage />)} />
          <Route
            path="subscribers/:id"
            element={guarded("subscribers.view", <SubscriberDetailPage />)}
          />
          <Route path="newsletters" element={guarded("newsletters.view", <NewslettersPage />)} />
          <Route
            path="newsletters/:id"
            element={guarded("newsletters.view", <NewsletterEditorPage />)}
          />
          <Route
            path="email-automations"
            element={guarded(["email_automations.manage", "newsletters.view"], <AutomationsPage />)}
          />
          <Route
            path="email-automations/:id"
            element={guarded(
              ["email_automations.manage", "newsletters.view"],
              <AutomationDetailPage />,
            )}
          />
          <Route
            path="lead-magnets"
            element={guarded("lead_magnets.manage", <LeadMagnetsPage />)}
          />
          <Route path="partners" element={guarded("partnerships.view", <PartnersPage />)} />
          <Route
            path="partnership-inquiries"
            element={guarded("partnerships.view", <PartnershipInquiriesPage />)}
          />
          <Route
            path="sponsorships"
            element={guarded(
              ["partnerships.view", "sponsorships.view", "advertising.view"],
              <SponsorshipsPage />,
            )}
          />
          <Route path="media-kit" element={guarded("media_kit.manage", <MediaKitPage />)} />
          <Route path="affiliates" element={guarded("affiliates.view", <AffiliatesPage />)} />
          <Route
            path="affiliate-links"
            element={guarded("affiliates.view", <AffiliateLinksPage />)}
          />
          <Route
            path="partnership-reports"
            element={guarded(
              ["partnership_finance.view", "partnership_reports.export"],
              <PartnershipReportsPage />,
            )}
          />
          <Route
            path="email-settings"
            element={guarded("email_settings.manage", <EmailSettingsPage />)}
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
