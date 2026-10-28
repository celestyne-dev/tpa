import { lazy, Suspense, useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Navigate, Route, Routes } from "react-router";
import { loadSession, selectAuth } from "@/store/slices/authSlice";
import { AdminIndex } from "./components/AdminIndex";
import { AdminLayout, ScreenLoading } from "./components/AdminLayout";
import { RequireAuth, RequirePermission } from "./components/Guards";
import { NotificationProvider } from "./components/Notifications";
import { PAGE_LOADERS } from "./screens";
import { ActivatePage } from "./pages/ActivatePage";
import { LoginPage } from "./pages/LoginPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import {
  ANALYTICS_ACCESS,
  ARTICLE_ACCESS,
  PAGE_READ,
  REDIRECT_READ,
  ROLE_READ,
  SEO_READ,
  SETTINGS_ACCESS,
  SHARED_ACCESS,
  TAXONOMY_READ,
} from "./permissions";

// Each admin screen is its own lazily loaded chunk: opening one page never downloads the
// others, and a guarded page's code is only requested once its permission check passes.
// Login, activation and password reset stay in the main admin chunk.
const screen = (module, name) =>
  lazy(() => PAGE_LOADERS[module]().then((m) => ({ default: m[name] })));

const AccountPage = screen("AccountPage", "AccountPage");
const AnnouncementsPage = screen("AnnouncementsPage", "AnnouncementsPage");
const BrandingPage = screen("BrandingPage", "BrandingPage");
const FooterPage = screen("FooterPage", "FooterPage");
const HomepageBuilderPage = screen("HomepageBuilderPage", "HomepageBuilderPage");
const PagePreviewPage = screen("PagePreviewPage", "PagePreviewPage");
const PreviewFramePage = screen("PreviewFramePage", "PreviewFramePage");
const SharedSectionsPage = screen("SharedSectionsPage", "SharedSectionsPage");
const ArticleEditorPage = screen("ArticleEditorPage", "ArticleEditorPage");
const ArticlePreviewPage = screen("ArticlePreviewPage", "ArticlePreviewPage");
const MediaLibraryPage = screen("MediaLibraryPage", "MediaLibraryPage");
const PublishingPage = screen("PublishingPage", "PublishingPage");
const RedirectsPage = screen("RedirectsPage", "RedirectsPage");
const SeoPage = screen("SeoPage", "SeoPage");
const WorkflowPage = screen("WorkflowPage", "WorkflowPage");
const ArticlesPage = screen("ArticlesPage", "ArticlesPage");
const AuditLogPage = screen("AuditLogPage", "AuditLogPage");
const NavigationPage = screen("NavigationPage", "NavigationPage");
const PageEditorPage = screen("PageEditorPage", "PageEditorPage");
const PagesPage = screen("PagesPage", "PagesPage");
const RoleEditorPage = screen("RoleEditorPage", "RoleEditorPage");
const RolesPage = screen("RolesPage", "RolesPage");
const SettingsPage = screen("SettingsPage", "SettingsPage");
const TaxonomyPage = screen("TaxonomyPage", "TaxonomyPage");
const UsersPage = screen("UsersPage", "UsersPage");
const CustomerDetailPage = screen("CustomersPage", "CustomerDetailPage");
const CustomersPage = screen("CustomersPage", "CustomersPage");
const EntitlementsPage = screen("EntitlementsPage", "EntitlementsPage");
const OrderDetailPage = screen("OrderDetailPage", "OrderDetailPage");
const OrdersPage = screen("OrdersPage", "OrdersPage");
const PaymentSettingsPage = screen("PaymentSettingsPage", "PaymentSettingsPage");
const AutomationDetailPage = screen("newsletter/AutomationsPage", "AutomationDetailPage");
const AutomationsPage = screen("newsletter/AutomationsPage", "AutomationsPage");
const EmailSettingsPage = screen("newsletter/EmailSettingsPage", "EmailSettingsPage");
const LeadMagnetsPage = screen("newsletter/LeadMagnetsPage", "LeadMagnetsPage");
const NewsletterEditorPage = screen("newsletter/NewsletterEditorPage", "NewsletterEditorPage");
const NewslettersPage = screen("newsletter/NewslettersPage", "NewslettersPage");
const AffiliateLinksPage = screen("partnerships/AffiliatesPage", "AffiliateLinksPage");
const AffiliatesPage = screen("partnerships/AffiliatesPage", "AffiliatesPage");
const MediaKitPage = screen("partnerships/MediaKitPage", "MediaKitPage");
const PartnersPage = screen("partnerships/PartnersPage", "PartnersPage");
const PartnershipInquiriesPage = screen("partnerships/PartnersPage", "PartnershipInquiriesPage");
const PartnershipReportsPage = screen(
  "partnerships/PartnershipReportsPage",
  "PartnershipReportsPage",
);
const SponsorshipsPage = screen("partnerships/SponsorshipsPage", "SponsorshipsPage");
const SubscriberDetailPage = screen("newsletter/SubscribersPage", "SubscriberDetailPage");
const SubscribersPage = screen("newsletter/SubscribersPage", "SubscribersPage");
const ProductCollectionsPage = screen("ProductCollectionsPage", "ProductCollectionsPage");
const ProductEditorPage = screen("ProductEditorPage", "ProductEditorPage");
const ProductPreviewPage = screen("ProductPreviewPage", "ProductPreviewPage");
const BundlesPage = screen("ProductsPage", "BundlesPage");
const ProductsPage = screen("ProductsPage", "ProductsPage");
const CourseEditorPage = screen("courses/CourseEditorPage", "CourseEditorPage");
const CoursePreviewPage = screen("courses/CoursePreviewPage", "CoursePreviewPage");
const CoursesPage = screen("courses/CoursesPage", "CoursesPage");
const GradingDashboardPage = screen("grading/GradingDashboardPage", "GradingDashboardPage");
const MembershipPlanEditorPage = screen(
  "memberships/MembershipPlanEditorPage",
  "MembershipPlanEditorPage",
);
const AnalyticsPage = screen("AnalyticsPage", "AnalyticsPage");
const MembershipGrantsPage = screen("memberships/MembershipGrantsPage", "MembershipGrantsPage");
const MembershipPlansPage = screen("memberships/MembershipPlansPage", "MembershipPlansPage");
const MembershipReportsPage = screen("memberships/MembershipReportsPage", "MembershipReportsPage");
const MembershipSubscriptionDetailPage = screen(
  "memberships/MembershipSubscriptionDetailPage",
  "MembershipSubscriptionDetailPage",
);
const MembershipSubscriptionsPage = screen(
  "memberships/MembershipSubscriptionsPage",
  "MembershipSubscriptionsPage",
);
const SubmissionReviewPage = screen("grading/SubmissionReviewPage", "SubmissionReviewPage");
const QuestionBankPage = screen("questionBanks/QuestionBankPage", "QuestionBankPage");
const QuestionBanksPage = screen("questionBanks/QuestionBanksPage", "QuestionBanksPage");
const ResourcesPage = screen("ResourcesPage", "ResourcesPage");
const RevenueReportPage = screen("RevenueReportPage", "RevenueReportPage");
const StoragePage = screen("StoragePage", "StoragePage");

const SUBSCRIBER_READ = ["memberships.manage_subscriptions", "memberships.view"];
/** `rule` is one permission key or a list of alternatives (any one suffices). */
const guarded = (rule, element) =>
  Array.isArray(rule) ? (
    <RequirePermission anyOf={rule}>{element}</RequirePermission>
  ) : (
    <RequirePermission permission={rule}>{element}</RequirePermission>
  );

/** Full-screen previews render outside the admin layout, so they need their own boundary. */
const fullScreen = (element) => <Suspense fallback={<ScreenLoading />}>{element}</Suspense>;

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
          element={<RequireAuth>{fullScreen(guarded(PAGE_READ, <PagePreviewPage />))}</RequireAuth>}
        />
        <Route
          path="products/:id/preview"
          element={
            <RequireAuth>
              {fullScreen(guarded("products.view", <ProductPreviewPage />))}
            </RequireAuth>
          }
        />
        <Route
          path="preview-frame/:id"
          element={
            <RequireAuth>{fullScreen(guarded(PAGE_READ, <PreviewFramePage />))}</RequireAuth>
          }
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
          <Route path="analytics" element={guarded(ANALYTICS_ACCESS, <AnalyticsPage />)} />
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
