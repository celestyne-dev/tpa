"""Permission catalogue, system roles and role templates.

The catalogue below is the canonical definition of every permission key. It is
synchronised into the ``permissions`` table (migration + ``flask rbac sync``),
and roles reference permissions through ``role_permissions`` rows, so custom
roles can be created and edited from the admin without code changes.

- ``available``: the backend has endpoints that enforce this permission. Roles
  can only be granted available permissions, so a role can never silently gain
  access when a future module ships.
- ``sensitive``: reserved for the protected Super Admin role (role management,
  payment configuration, system security). Never assignable to other roles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Permission(StrEnum):
    DASHBOARD_VIEW = "dashboard.view"
    ANALYTICS_VIEW = "analytics.view"
    ARTICLES_VIEW = "articles.view"
    ARTICLES_CREATE = "articles.create"
    ARTICLES_EDIT_OWN = "articles.edit_own"
    ARTICLES_EDIT_ANY = "articles.edit_any"
    ARTICLES_SUBMIT_REVIEW = "articles.submit_review"
    ARTICLES_APPROVE = "articles.approve"
    ARTICLES_PUBLISH = "articles.publish"
    ARTICLES_UNPUBLISH = "articles.unpublish"
    ARTICLES_ARCHIVE = "articles.archive"
    ARTICLES_DELETE = "articles.delete"
    TOPICS_MANAGE = "topics.manage"
    TAGS_MANAGE = "tags.manage"
    AUTHORS_MANAGE = "authors.manage"
    MEDIA_VIEW = "media.view"
    MEDIA_UPLOAD = "media.upload"
    MEDIA_EDIT = "media.edit"
    MEDIA_REPLACE = "media.replace"
    MEDIA_DELETE = "media.delete"
    ARTICLES_VIEW_REVISIONS = "articles.view_revisions"
    ARTICLES_RESTORE_REVISIONS = "articles.restore_revisions"
    ARTICLES_PREVIEW = "articles.preview"
    SEO_VIEW = "seo.view"
    REDIRECTS_MANAGE = "redirects.manage"
    PUBLISHING_VIEW = "publishing.view"
    PUBLISHING_MANAGE = "publishing.manage"
    PAGES_VIEW = "pages.view"
    PAGES_EDIT = "pages.edit"
    PAGES_CREATE = "pages.create"
    PAGES_PUBLISH = "pages.publish"
    HOMEPAGE_VIEW = "homepage.view"
    HOMEPAGE_EDIT = "homepage.edit"
    HOMEPAGE_PUBLISH = "homepage.publish"
    REUSABLE_SECTIONS_MANAGE = "reusable_sections.manage"
    BRANDING_MANAGE = "branding.manage"
    ANNOUNCEMENTS_MANAGE = "announcements.manage"
    NAVIGATION_MANAGE = "navigation.manage"
    SETTINGS_MANAGE = "settings.manage"
    SETTINGS_SECURITY = "settings.security"
    SETTINGS_TECHNICAL = "settings.technical"
    SEO_MANAGE = "seo.manage"
    PRODUCTS_VIEW = "products.view"
    PRODUCTS_MANAGE = "products.manage"
    PRODUCTS_CREATE = "products.create"
    PRODUCTS_EDIT = "products.edit"
    PRODUCTS_PUBLISH = "products.publish"
    PRODUCTS_ARCHIVE = "products.archive"
    PRODUCTS_MANAGE_PRICES = "products.manage_prices"
    PRODUCTS_MANAGE_FILES = "products.manage_files"
    PRODUCTS_MANAGE_BUNDLES = "products.manage_bundles"
    ORDERS_VIEW = "orders.view"
    ORDERS_MANAGE = "orders.manage"
    ORDERS_EXPORT = "orders.export"
    REFUNDS_ISSUE = "refunds.issue"
    PAYMENTS_CONFIGURE = "payments.configure"
    PAYMENTS_VIEW_EVENTS = "payments.view_events"
    CUSTOMERS_VIEW = "customers.view"
    CUSTOMERS_SUPPORT = "customers.support"
    CUSTOMERS_MANAGE = "customers.manage"
    ENTITLEMENTS_VIEW = "entitlements.view"
    ENTITLEMENTS_MANAGE = "entitlements.manage"
    DOWNLOADS_AUDIT = "downloads.audit"
    PARTNERSHIPS_VIEW = "partnerships.view"
    PARTNERSHIPS_MANAGE = "partnerships.manage"
    ADVERTISING_VIEW = "advertising.view"
    ADVERTISING_MANAGE = "advertising.manage"
    AFFILIATES_VIEW = "affiliates.view"
    AFFILIATES_MANAGE = "affiliates.manage"
    AFFILIATES_MANAGE_LINKS = "affiliates.manage_links"
    SPONSORSHIPS_VIEW = "sponsorships.view"
    SPONSORSHIPS_MANAGE = "sponsorships.manage"
    SPONSORSHIPS_APPROVE = "sponsorships.approve"
    ADVERTISING_MANAGE_INVENTORY = "advertising.manage_inventory"
    ADVERTISING_MANAGE_BOOKINGS = "advertising.manage_bookings"
    MEDIA_KIT_MANAGE = "media_kit.manage"
    PARTNERSHIP_FINANCE_VIEW = "partnership_finance.view"
    PARTNERSHIP_FINANCE_MANAGE = "partnership_finance.manage"
    PARTNERSHIP_REPORTS_EXPORT = "partnership_reports.export"
    NEWSLETTERS_MANAGE = "newsletters.manage"
    SUBSCRIBERS_VIEW = "subscribers.view"
    SUBSCRIBERS_EXPORT = "subscribers.export"
    SUBSCRIBERS_MANAGE = "subscribers.manage"
    NEWSLETTERS_VIEW = "newsletters.view"
    NEWSLETTERS_CREATE = "newsletters.create"
    NEWSLETTERS_EDIT = "newsletters.edit"
    NEWSLETTERS_PUBLISH = "newsletters.publish"
    NEWSLETTERS_SEND = "newsletters.send"
    NEWSLETTERS_SCHEDULE = "newsletters.schedule"
    NEWSLETTERS_REPORTS = "newsletters.reports"
    EMAIL_TEMPLATES_MANAGE = "email_templates.manage"
    EMAIL_AUTOMATIONS_MANAGE = "email_automations.manage"
    LEAD_MAGNETS_MANAGE = "lead_magnets.manage"
    EMAIL_SETTINGS_MANAGE = "email_settings.manage"
    MEMBERSHIPS_MANAGE = "memberships.manage"
    MEMBERSHIPS_VIEW = "memberships.view"
    MEMBERSHIPS_PUBLISH = "memberships.publish"
    MEMBERSHIPS_MANAGE_SUBSCRIPTIONS = "memberships.manage_subscriptions"
    MEMBERSHIPS_VIEW_REPORTS = "memberships.view_reports"
    FINANCE_VIEW = "finance.view"
    FINANCE_EXPORT = "finance.export"
    FINANCE_MANAGE = "finance.manage"
    USERS_VIEW = "users.view"
    USERS_MANAGE = "users.manage"
    ROLES_MANAGE = "roles.manage"
    ROLES_ASSIGN = "roles.assign"
    AUDIT_VIEW = "audit.view"
    STORAGE_VIEW = "storage.view"
    COURSES_VIEW = "courses.view"
    COURSES_CREATE = "courses.create"
    COURSES_EDIT = "courses.edit"
    COURSES_PUBLISH = "courses.publish"
    COURSES_ARCHIVE = "courses.archive"
    COURSES_MANAGE_CURRICULUM = "courses.manage_curriculum"
    COURSES_MANAGE_ASSESSMENTS = "courses.manage_assessments"
    COURSES_VIEW_ENROLLMENTS = "courses.view_enrollments"
    COURSES_MANAGE_ENROLLMENTS = "courses.manage_enrollments"
    COURSES_VIEW_REPORTS = "courses.view_reports"
    COURSES_VIEW_DRAFTS = "courses.view_drafts"
    COURSES_EDIT_DRAFTS = "courses.edit_drafts"
    COURSES_PUBLISH_LESSONS = "courses.publish_lessons"
    COURSES_VIEW_REVISIONS = "courses.view_revisions"
    COURSES_RESTORE_REVISIONS = "courses.restore_revisions"
    ASSIGNMENTS_VIEW = "assignments.view"
    ASSIGNMENTS_MANAGE = "assignments.manage"
    ASSIGNMENTS_VIEW_SUBMISSIONS = "assignments.view_submissions"
    ASSIGNMENTS_GRADE = "assignments.grade"
    ASSIGNMENTS_PUBLISH_GRADES = "assignments.publish_grades"
    ASSIGNMENTS_MANAGE_EXCEPTIONS = "assignments.manage_exceptions"
    ASSIGNMENTS_VIEW_REPORTS = "assignments.view_reports"
    QUESTION_BANKS_VIEW = "question_banks.view"
    QUESTION_BANKS_MANAGE = "question_banks.manage"


P = Permission


@dataclass(frozen=True)
class PermissionDef:
    key: Permission
    label: str
    group: str
    module: str
    available: bool = True
    sensitive: bool = False
    description: str = ""


def _d(key, label, group, module, *, available=True, sensitive=False, description=""):
    return PermissionDef(key, label, group, module, available, sensitive, description)


CATALOGUE: list[PermissionDef] = [
    _d(P.DASHBOARD_VIEW, "View dashboard", "Dashboard & analytics", "dashboard"),
    _d(P.ANALYTICS_VIEW, "View content analytics", "Dashboard & analytics", "analytics"),
    _d(
        P.ARTICLES_VIEW,
        "View all articles",
        "Articles",
        "articles",
        description="See every article, including other people's drafts.",
    ),
    _d(P.ARTICLES_CREATE, "Create articles", "Articles", "articles"),
    _d(
        P.ARTICLES_EDIT_OWN,
        "Edit own drafts",
        "Articles",
        "articles",
        description="Edit articles you created while they are drafts.",
    ),
    _d(P.ARTICLES_EDIT_ANY, "Edit any article", "Articles", "articles"),
    _d(P.ARTICLES_SUBMIT_REVIEW, "Submit for review", "Articles", "articles"),
    _d(P.ARTICLES_APPROVE, "Approve articles", "Articles", "articles"),
    _d(P.ARTICLES_PUBLISH, "Publish and schedule", "Articles", "articles"),
    _d(P.ARTICLES_UNPUBLISH, "Unpublish", "Articles", "articles"),
    _d(P.ARTICLES_ARCHIVE, "Archive and restore", "Articles", "articles"),
    _d(
        P.ARTICLES_DELETE,
        "Delete unpublished drafts",
        "Articles",
        "articles",
        description="Permanently delete drafts that were never published.",
    ),
    _d(
        P.ARTICLES_VIEW_REVISIONS,
        "View revision history",
        "Articles",
        "articles",
        description="For articles you can open.",
    ),
    _d(
        P.ARTICLES_RESTORE_REVISIONS,
        "Restore revisions",
        "Articles",
        "articles",
        description="Only on articles you are allowed to edit.",
    ),
    _d(
        P.ARTICLES_PREVIEW,
        "Preview drafts",
        "Articles",
        "articles",
        description="Private, non-indexed preview of articles you can open.",
    ),
    _d(P.TOPICS_MANAGE, "Manage topics", "Topics, tags & authors", "taxonomy"),
    _d(P.TAGS_MANAGE, "Manage tags", "Topics, tags & authors", "taxonomy"),
    _d(P.AUTHORS_MANAGE, "Manage authors", "Topics, tags & authors", "taxonomy"),
    _d(P.MEDIA_VIEW, "View media library", "Media library", "media"),
    _d(
        P.MEDIA_UPLOAD,
        "Upload media",
        "Media library",
        "media",
        description="Upload images; they are validated and optimised automatically.",
    ),
    _d(
        P.MEDIA_EDIT,
        "Edit media details",
        "Media library",
        "media",
        description="Alt text, title, caption, credit and focal point.",
    ),
    _d(P.MEDIA_REPLACE, "Replace media files", "Media library", "media"),
    _d(
        P.MEDIA_DELETE,
        "Archive and delete media",
        "Media library",
        "media",
        description="Media still used by content can be archived but never deleted.",
    ),
    _d(
        P.HOMEPAGE_VIEW,
        "View homepage builder",
        "Pages & homepage",
        "homepage",
        description="See the homepage sections, drafts, previews and history.",
    ),
    _d(
        P.HOMEPAGE_EDIT,
        "Edit homepage drafts",
        "Pages & homepage",
        "homepage",
        description="Change, add, reorder and restore homepage sections as a draft.",
    ),
    _d(
        P.HOMEPAGE_PUBLISH,
        "Publish the homepage",
        "Pages & homepage",
        "homepage",
        description="Make homepage drafts live (queues a site rebuild).",
    ),
    _d(P.PAGES_VIEW, "View pages", "Pages & homepage", "pages"),
    _d(
        P.PAGES_EDIT,
        "Edit page drafts",
        "Pages & homepage",
        "pages",
        description="Edit page content, sections and SEO as a draft; restore revisions.",
    ),
    _d(P.PAGES_CREATE, "Create and duplicate pages", "Pages & homepage", "pages"),
    _d(
        P.PAGES_PUBLISH,
        "Publish pages",
        "Pages & homepage",
        "pages",
        description="Publish, schedule, unpublish, archive and restore pages.",
    ),
    _d(
        P.REUSABLE_SECTIONS_MANAGE,
        "Manage shared sections and calls to action",
        "Pages & homepage",
        "pages",
        description="Edit shared sections (changes can update every page using them).",
    ),
    _d(
        P.BRANDING_MANAGE,
        "Manage branding",
        "Site settings",
        "branding",
        description="Site name, logos, favicon, social image and approved style presets.",
    ),
    _d(
        P.ANNOUNCEMENTS_MANAGE,
        "Manage announcement banners",
        "Site settings",
        "announcements",
    ),
    _d(P.NAVIGATION_MANAGE, "Manage navigation menus", "Navigation", "navigation"),
    _d(
        P.SETTINGS_MANAGE,
        "Manage site settings",
        "Site settings",
        "settings",
        description="Contact details, social links, footer and the newsletter flag.",
    ),
    _d(
        P.SETTINGS_TECHNICAL,
        "Manage indexing and canonical URL",
        "Site settings",
        "settings",
        sensitive=True,
        description="Search engine indexing and the canonical website address (Super Admin).",
    ),
    _d(
        P.SETTINGS_SECURITY,
        "Manage security settings",
        "Site settings",
        "settings",
        available=False,
        sensitive=True,
    ),
    _d(
        P.SEO_MANAGE,
        "Manage SEO settings",
        "SEO",
        "seo",
        description="Default titles, descriptions and sharing image; article canonical URLs, "
        "indexing and post-publication slug changes.",
    ),
    _d(
        P.SEO_VIEW,
        "View SEO audit",
        "SEO",
        "seo",
        description="The SEO dashboard and per-article checks.",
    ),
    _d(P.REDIRECTS_MANAGE, "Manage redirects", "SEO", "redirects"),
    _d(
        P.PUBLISHING_VIEW,
        "View publishing jobs",
        "Publishing",
        "publishing",
        description="Static site build status and history.",
    ),
    _d(
        P.PUBLISHING_MANAGE,
        "Run and retry publishing jobs",
        "Publishing",
        "publishing",
    ),
    _d(
        P.PRODUCTS_VIEW,
        "View products",
        "Digital products",
        "products",
        description="See the product catalogue, drafts, files list and history.",
    ),
    _d(P.PRODUCTS_CREATE, "Create and duplicate products", "Digital products", "products"),
    _d(
        P.PRODUCTS_EDIT,
        "Edit product drafts",
        "Digital products",
        "products",
        description="Descriptions, images, categories, collections, FAQs and SEO (as a draft).",
    ),
    _d(
        P.PRODUCTS_PUBLISH,
        "Publish products",
        "Digital products",
        "products",
        description="Publish, unpublish, schedule availability and put products on sale.",
    ),
    _d(P.PRODUCTS_ARCHIVE, "Archive and restore products", "Digital products", "products"),
    _d(
        P.PRODUCTS_MANAGE_PRICES,
        "Set and approve prices",
        "Digital products",
        "products",
        description="Prices, compare-at and promotional prices in each currency.",
    ),
    _d(
        P.PRODUCTS_MANAGE_FILES,
        "Manage private product files",
        "Digital products",
        "products",
        description="Upload, replace, deactivate and download deliverable files.",
    ),
    _d(
        P.PRODUCTS_MANAGE_BUNDLES,
        "Manage bundles",
        "Digital products",
        "products",
        description="Choose which products a bundle includes.",
    ),
    _d(
        P.PRODUCTS_MANAGE,
        "Manage products (legacy)",
        "Digital products",
        "products",
        available=False,
        description="Replaced by the granular product permissions above.",
    ),
    _d(P.ORDERS_VIEW, "View orders", "Orders & refunds", "orders"),
    _d(
        P.ORDERS_MANAGE,
        "Manage orders",
        "Orders & refunds",
        "orders",
        description="Re-check payments, cancel unpaid orders, resend receipts and add notes.",
    ),
    _d(P.ORDERS_EXPORT, "Export orders", "Orders & refunds", "orders"),
    _d(
        P.REFUNDS_ISSUE,
        "Issue refunds",
        "Orders & refunds",
        "orders",
        description="Request and record refunds (provider refunds only when configured).",
    ),
    _d(
        P.PAYMENTS_VIEW_EVENTS,
        "View payment events",
        "Orders & refunds",
        "payments",
        description="Payment attempts, provider webhooks and verification results.",
    ),
    _d(
        P.PAYMENTS_CONFIGURE,
        "Configure payments",
        "Orders & refunds",
        "payments",
        sensitive=True,
        description="Payment provider, test/live mode, currencies and checkout availability.",
    ),
    _d(P.CUSTOMERS_VIEW, "View customers", "Customers", "customers"),
    _d(
        P.CUSTOMERS_SUPPORT,
        "Assist customers",
        "Customers",
        "customers",
        description="Resend verification and password-reset emails, add support notes.",
    ),
    _d(
        P.CUSTOMERS_MANAGE,
        "Manage customer accounts",
        "Customers",
        "customers",
        description="Disable or reactivate accounts, mark test accounts, process deletions.",
    ),
    _d(P.ENTITLEMENTS_VIEW, "View download access", "Customers", "entitlements"),
    _d(
        P.ENTITLEMENTS_MANAGE,
        "Grant and revoke download access",
        "Customers",
        "entitlements",
    ),
    _d(P.DOWNLOADS_AUDIT, "View download activity", "Customers", "entitlements"),
    _d(
        P.PARTNERSHIPS_VIEW,
        "View partners and pipeline",
        "Partnerships & sponsorships",
        "partnerships",
        description="Partner profiles, contacts, inquiries and opportunities.",
    ),
    _d(
        P.PARTNERSHIPS_MANAGE,
        "Manage partners and pipeline",
        "Partnerships & sponsorships",
        "partnerships",
        description="Create and edit partners, inquiries, opportunities and interactions.",
    ),
    _d(
        P.SPONSORSHIPS_VIEW,
        "View sponsorship campaigns",
        "Partnerships & sponsorships",
        "partnerships",
    ),
    _d(
        P.SPONSORSHIPS_MANAGE,
        "Manage sponsorship campaigns",
        "Partnerships & sponsorships",
        "partnerships",
        description="Campaigns, sponsored article and newsletter details, review states.",
    ),
    _d(
        P.SPONSORSHIPS_APPROVE,
        "Approve sponsored content",
        "Partnerships & sponsorships",
        "partnerships",
        description="Approve sponsored articles, newsletters and campaigns for publication.",
    ),
    _d(P.ADVERTISING_VIEW, "View advertising inventory and bookings", "Advertising", "advertising"),
    _d(
        P.ADVERTISING_MANAGE,
        "Manage advertising (superseded)",
        "Advertising",
        "advertising",
        available=False,
        description="Replaced in Batch 07 by manage_inventory and manage_bookings.",
    ),
    _d(
        P.ADVERTISING_MANAGE_INVENTORY,
        "Manage placements and rate cards",
        "Advertising",
        "advertising",
    ),
    _d(
        P.ADVERTISING_MANAGE_BOOKINGS,
        "Manage and approve bookings",
        "Advertising",
        "advertising",
    ),
    _d(P.MEDIA_KIT_MANAGE, "Manage the media kit and audience data", "Advertising", "advertising"),
    _d(P.AFFILIATES_VIEW, "View affiliate programs and links", "Affiliates", "affiliates"),
    _d(
        P.AFFILIATES_MANAGE,
        "Manage affiliate programs",
        "Affiliates",
        "affiliates",
        description="Programs, private account identifiers, commission imports and disclosure "
        "wording.",
    ),
    _d(P.AFFILIATES_MANAGE_LINKS, "Manage affiliate links", "Affiliates", "affiliates"),
    _d(
        P.PARTNERSHIP_FINANCE_VIEW,
        "View partnership finances",
        "Partnerships & sponsorships",
        "partnerships",
        description="Fees, invoiced and received amounts, outstanding balances.",
    ),
    _d(
        P.PARTNERSHIP_FINANCE_MANAGE,
        "Record partnership invoices and payments",
        "Partnerships & sponsorships",
        "partnerships",
        description="Manual records only: no invoices are issued and no payments initiated.",
    ),
    _d(
        P.PARTNERSHIP_REPORTS_EXPORT,
        "Export partnership reports",
        "Partnerships & sponsorships",
        "partnerships",
    ),
    _d(
        P.NEWSLETTERS_MANAGE,
        "Manage newsletters (superseded)",
        "Newsletters & subscribers",
        "newsletters",
        available=False,
        description="Replaced in Batch 06 by the specific newsletters.* permissions.",
    ),
    _d(P.SUBSCRIBERS_VIEW, "View subscribers", "Newsletters & subscribers", "newsletters"),
    _d(
        P.SUBSCRIBERS_MANAGE,
        "Manage subscribers",
        "Newsletters & subscribers",
        "newsletters",
        description="Tags, segments, imports (quarantined), unsubscribes and suppressions.",
    ),
    _d(
        P.SUBSCRIBERS_EXPORT,
        "Export subscribers",
        "Newsletters & subscribers",
        "newsletters",
        description="Download subscriber personal data and consent records (audited).",
    ),
    _d(P.NEWSLETTERS_VIEW, "View newsletters", "Newsletters & subscribers", "newsletters"),
    _d(P.NEWSLETTERS_CREATE, "Create newsletters", "Newsletters & subscribers", "newsletters"),
    _d(P.NEWSLETTERS_EDIT, "Edit newsletter drafts", "Newsletters & subscribers", "newsletters"),
    _d(
        P.NEWSLETTERS_PUBLISH,
        "Approve newsletters",
        "Newsletters & subscribers",
        "newsletters",
        description="Approve a campaign for sending (any later edit withdraws the approval).",
    ),
    _d(
        P.NEWSLETTERS_SEND,
        "Send newsletters",
        "Newsletters & subscribers",
        "newsletters",
        description="Send an approved campaign to its audience.",
    ),
    _d(
        P.NEWSLETTERS_SCHEDULE,
        "Schedule newsletters",
        "Newsletters & subscribers",
        "newsletters",
    ),
    _d(
        P.NEWSLETTERS_REPORTS,
        "View newsletter reports",
        "Newsletters & subscribers",
        "newsletters",
    ),
    _d(
        P.EMAIL_TEMPLATES_MANAGE,
        "Manage email templates",
        "Newsletters & subscribers",
        "newsletters",
    ),
    _d(
        P.EMAIL_AUTOMATIONS_MANAGE,
        "Manage email automations",
        "Newsletters & subscribers",
        "newsletters",
    ),
    _d(P.LEAD_MAGNETS_MANAGE, "Manage lead magnets", "Newsletters & subscribers", "newsletters"),
    _d(
        P.EMAIL_SETTINGS_MANAGE,
        "Configure email sending",
        "Newsletters & subscribers",
        "newsletters",
        sensitive=True,
        description="Sending mode (disabled/test/live), sender identity, consent wording and "
        "deliverability confirmations.",
    ),
    _d(
        P.MEMBERSHIPS_MANAGE,
        "Manage membership plans",
        "Courses & memberships",
        "memberships",
        description="Plan content, benefits, prices and the courses and resources included.",
    ),
    _d(
        P.FINANCE_VIEW,
        "View revenue reports",
        "Finance",
        "finance",
        description="Sales, refunds and downloads by currency and product.",
    ),
    _d(P.FINANCE_EXPORT, "Export revenue reports", "Finance", "finance"),
    _d(P.FINANCE_MANAGE, "Manage finance", "Finance", "finance", available=False),
    _d(P.USERS_VIEW, "View administrators", "Users, roles & audit", "users"),
    _d(
        P.USERS_MANAGE,
        "Manage administrator accounts",
        "Users, roles & audit",
        "users",
        description="Disable, reactivate and reset passwords of administrators with equal "
        "or fewer permissions.",
    ),
    _d(
        P.ROLES_MANAGE,
        "Manage roles and permissions",
        "Users, roles & audit",
        "roles",
        sensitive=True,
    ),
    _d(
        P.ROLES_ASSIGN,
        "Assign roles and invite administrators",
        "Users, roles & audit",
        "roles",
        sensitive=True,
    ),
    _d(P.AUDIT_VIEW, "View audit log", "Users, roles & audit", "audit"),
    _d(
        P.STORAGE_VIEW,
        "View storage health",
        "Users, roles & audit",
        "storage",
        description="Disk space, folder permissions, missing files, upload errors and backups.",
    ),
    # Batch 09: text-based courses (appended so existing permissions keep their order).
    _d(P.COURSES_VIEW, "View courses", "Courses & memberships", "courses"),
    _d(P.COURSES_CREATE, "Create courses", "Courses & memberships", "courses"),
    _d(
        P.COURSES_EDIT,
        "Edit course details",
        "Courses & memberships",
        "courses",
        description="Descriptions, outcomes, pricing link, access rules, SEO and covers.",
    ),
    _d(
        P.COURSES_PUBLISH,
        "Publish courses",
        "Courses & memberships",
        "courses",
        description="Publish, schedule and unpublish courses and lessons.",
    ),
    _d(P.COURSES_ARCHIVE, "Archive courses", "Courses & memberships", "courses"),
    _d(
        P.COURSES_MANAGE_CURRICULUM,
        "Manage course curriculum",
        "Courses & memberships",
        "courses",
        description="Modules, lessons, lesson content, order and worksheets.",
    ),
    _d(
        P.COURSES_MANAGE_ASSESSMENTS,
        "Manage assessments",
        "Courses & memberships",
        "courses",
        description="Quizzes, reflections, questions and answer keys.",
    ),
    _d(
        P.COURSES_VIEW_ENROLLMENTS,
        "View enrolments and progress",
        "Courses & memberships",
        "courses",
        description="Learners, progress, assessment results and certificates.",
    ),
    _d(
        P.COURSES_MANAGE_ENROLLMENTS,
        "Manage enrolments and certificates",
        "Courses & memberships",
        "courses",
        description="Enrol or remove learners, revoke or correct certificates.",
    ),
    _d(P.COURSES_VIEW_REPORTS, "View course reports", "Courses & memberships", "courses"),
    # Batch 09.1: lesson drafts and revisions (appended; existing order unchanged).
    _d(
        P.COURSES_VIEW_DRAFTS,
        "Read lesson drafts",
        "Courses & memberships",
        "courses",
        description="Open lesson drafts and preview unpublished lesson changes.",
    ),
    _d(
        P.COURSES_EDIT_DRAFTS,
        "Edit lesson drafts",
        "Courses & memberships",
        "courses",
        description="Change lesson text and settings in the draft (learners don't see it).",
    ),
    _d(
        P.COURSES_PUBLISH_LESSONS,
        "Publish lessons",
        "Courses & memberships",
        "courses",
        description="Publish lesson changes to learners, or unpublish lessons.",
    ),
    _d(
        P.COURSES_VIEW_REVISIONS,
        "View lesson revisions",
        "Courses & memberships",
        "courses",
        description="Revision history and comparisons between lesson versions.",
    ),
    _d(
        P.COURSES_RESTORE_REVISIONS,
        "Restore lesson revisions",
        "Courses & memberships",
        "courses",
        description="Copy an earlier published version back into the lesson draft.",
    ),
    # Batch 09.2: written assignments, submissions and grading (appended).
    _d(P.ASSIGNMENTS_VIEW, "View assignments", "Courses & memberships", "courses"),
    _d(
        P.ASSIGNMENTS_MANAGE,
        "Manage assignments",
        "Courses & memberships",
        "courses",
        description="Assignment definitions, rubrics, publishing and course assessors.",
    ),
    _d(
        P.ASSIGNMENTS_VIEW_SUBMISSIONS,
        "View submissions",
        "Courses & memberships",
        "courses",
        description="Read learners' submitted work and documents (assigned courses only).",
    ),
    _d(
        P.ASSIGNMENTS_GRADE,
        "Grade submissions",
        "Courses & memberships",
        "courses",
        description="Score submissions and save draft grades and feedback.",
    ),
    _d(
        P.ASSIGNMENTS_PUBLISH_GRADES,
        "Publish grades",
        "Courses & memberships",
        "courses",
        description="Release grades and feedback to learners, request revisions, retract.",
    ),
    _d(
        P.ASSIGNMENTS_MANAGE_EXCEPTIONS,
        "Manage grading exceptions",
        "Courses & memberships",
        "courses",
        description="Deadline extensions and extra attempts for individual learners.",
    ),
    _d(P.ASSIGNMENTS_VIEW_REPORTS, "View assignment reports", "Courses & memberships", "courses"),
    # Batch 09.2 phase 2: reusable question banks (appended).
    _d(
        P.QUESTION_BANKS_VIEW,
        "View question banks",
        "Courses & memberships",
        "courses",
        description="List banks and their questions, without answer keys.",
    ),
    _d(
        P.QUESTION_BANKS_MANAGE,
        "Manage question banks",
        "Courses & memberships",
        "courses",
        description="Create and edit banks and questions, including answer keys.",
    ),
    # Batch 10.1: membership plans (appended).
    _d(P.MEMBERSHIPS_VIEW, "View membership plans", "Courses & memberships", "memberships"),
    _d(
        P.MEMBERSHIPS_PUBLISH,
        "Publish membership plans",
        "Courses & memberships",
        "memberships",
        description="Publish, unpublish and archive plans shown on the membership page.",
    ),
    # Batch 10.4: subscription administration and reporting (appended).
    _d(
        P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS,
        "Manage member subscriptions",
        "Courses & memberships",
        "memberships",
        description="View subscribers, reconcile with Paystack, cancel, extend grace periods "
        "and grant complimentary memberships. Refunds still need the refund permission.",
    ),
    _d(
        P.MEMBERSHIPS_VIEW_REPORTS,
        "View membership reports",
        "Courses & memberships",
        "memberships",
        description="Subscriber counts, renewals, churn and verified membership revenue.",
    ),
]

CATALOGUE_BY_KEY: dict[str, PermissionDef] = {d.key.value: d for d in CATALOGUE}
ALL_PERMISSIONS: frozenset[str] = frozenset(CATALOGUE_BY_KEY)
AVAILABLE_PERMISSIONS: frozenset[str] = frozenset(
    k for k, d in CATALOGUE_BY_KEY.items() if d.available
)
SENSITIVE_PERMISSIONS: frozenset[str] = frozenset(
    k for k, d in CATALOGUE_BY_KEY.items() if d.sensitive
)


class RoleName(StrEnum):
    SUPER_ADMIN = "super_admin"
    EDITOR = "editor"
    MODERATOR = "moderator"
    ANALYST = "analyst"


@dataclass(frozen=True)
class RoleSpec:
    key: str
    label: str
    description: str
    kind: str  # "system" (protected) or "template" (editable starting point)
    permissions: frozenset[str] = frozenset()
    grants_all: bool = False
    # Permissions this template is intended to receive once their modules ship.
    planned: frozenset[str] = field(default_factory=frozenset)


def _set(*perms: Permission) -> frozenset[str]:
    return frozenset(p.value for p in perms)


ARTICLE_EDITING = _set(P.ARTICLES_VIEW, P.ARTICLES_CREATE, P.ARTICLES_EDIT_OWN, P.ARTICLES_EDIT_ANY)

SYSTEM_ROLES: list[RoleSpec] = [
    RoleSpec(
        "super_admin",
        "Super Admin",
        "Full access to everything, including roles, users and sensitive settings.",
        "system",
        grants_all=True,
    ),
    RoleSpec(
        "editor",
        "Editor",
        "Creates, edits, approves and publishes editorial content.",
        "system",
        ARTICLE_EDITING
        | _set(
            P.DASHBOARD_VIEW,
            P.ARTICLES_SUBMIT_REVIEW,
            P.ARTICLES_APPROVE,
            P.ARTICLES_PUBLISH,
            P.ARTICLES_UNPUBLISH,
            P.ARTICLES_ARCHIVE,
            P.TOPICS_MANAGE,
            P.TAGS_MANAGE,
            P.AUTHORS_MANAGE,
            P.MEDIA_VIEW,
            P.PAGES_VIEW,
            P.PAGES_EDIT,
        ),
    ),
    RoleSpec(
        "moderator",
        "Moderator",
        "Reviews content and can take published content offline.",
        "system",
        _set(
            P.DASHBOARD_VIEW,
            P.ARTICLES_VIEW,
            P.ARTICLES_UNPUBLISH,
            P.ARTICLES_ARCHIVE,
            P.MEDIA_VIEW,
            P.PAGES_VIEW,
        ),
    ),
    RoleSpec(
        "analyst",
        "Analyst",
        "Read-only access to the dashboard, content and analytics.",
        "system",
        _set(P.DASHBOARD_VIEW, P.ANALYTICS_VIEW, P.ARTICLES_VIEW, P.MEDIA_VIEW),
    ),
]

TEMPLATE_ROLES: list[RoleSpec] = [
    RoleSpec(
        "administrator",
        "Administrator",
        "Runs day-to-day operations across content and the website (no role management).",
        "template",
        ARTICLE_EDITING
        | _set(
            P.DASHBOARD_VIEW,
            P.ANALYTICS_VIEW,
            P.ARTICLES_SUBMIT_REVIEW,
            P.ARTICLES_APPROVE,
            P.ARTICLES_PUBLISH,
            P.ARTICLES_UNPUBLISH,
            P.ARTICLES_ARCHIVE,
            P.ARTICLES_DELETE,
            P.TOPICS_MANAGE,
            P.TAGS_MANAGE,
            P.AUTHORS_MANAGE,
            P.MEDIA_VIEW,
            P.PAGES_VIEW,
            P.PAGES_EDIT,
            P.NAVIGATION_MANAGE,
            P.SETTINGS_MANAGE,
            P.SEO_MANAGE,
            P.USERS_VIEW,
            P.USERS_MANAGE,
            P.AUDIT_VIEW,
        ),
    ),
    RoleSpec(
        "editor_in_chief",
        "Editor-in-Chief",
        "Owns the editorial calendar: approves, publishes and curates all content.",
        "template",
        ARTICLE_EDITING
        | _set(
            P.DASHBOARD_VIEW,
            P.ANALYTICS_VIEW,
            P.ARTICLES_SUBMIT_REVIEW,
            P.ARTICLES_APPROVE,
            P.ARTICLES_PUBLISH,
            P.ARTICLES_UNPUBLISH,
            P.ARTICLES_ARCHIVE,
            P.ARTICLES_DELETE,
            P.TOPICS_MANAGE,
            P.TAGS_MANAGE,
            P.AUTHORS_MANAGE,
            P.MEDIA_VIEW,
            P.PAGES_VIEW,
        ),
    ),
    RoleSpec(
        "content_editor",
        "Content Editor",
        "Edits and prepares articles and submits them for approval.",
        "template",
        ARTICLE_EDITING
        | _set(P.DASHBOARD_VIEW, P.ARTICLES_SUBMIT_REVIEW, P.TAGS_MANAGE, P.MEDIA_VIEW),
        planned=_set(P.MEDIA_UPLOAD),
    ),
    RoleSpec(
        "content_writer",
        "Content Writer",
        "Writes and edits their own drafts and submits them for review.",
        "template",
        _set(
            P.DASHBOARD_VIEW,
            P.ARTICLES_CREATE,
            P.ARTICLES_EDIT_OWN,
            P.ARTICLES_SUBMIT_REVIEW,
            P.MEDIA_VIEW,
        ),
        planned=_set(P.MEDIA_UPLOAD),
    ),
    RoleSpec(
        "product_manager",
        "Product Manager",
        "Manages the digital product catalogue, files, prices and bundles.",
        "template",
        _set(P.DASHBOARD_VIEW),
        planned=frozenset(),
    ),
    RoleSpec(
        "orders_manager",
        "Orders Manager",
        "Manages orders, refunds and customer download access.",
        "template",
        _set(P.DASHBOARD_VIEW),
        planned=frozenset(),
    ),
    RoleSpec(
        "customer_support",
        "Customer Support",
        "Helps customers with orders, downloads and account questions.",
        "template",
        _set(P.DASHBOARD_VIEW),
        planned=frozenset(),
    ),
    RoleSpec(
        "partnerships_manager",
        "Partnerships Manager",
        "Manages partners, inquiries, opportunities, campaigns and bookings.",
        "template",
        _set(P.DASHBOARD_VIEW),
        planned=frozenset(),
    ),
    RoleSpec(
        "affiliate_manager",
        "Affiliate Manager",
        "Manages affiliate programs, links, disclosures and commission records.",
        "template",
        _set(P.DASHBOARD_VIEW),
        planned=frozenset(),
    ),
    RoleSpec(
        "marketing_manager",
        "Marketing Manager",
        "Reviews content performance, drafts newsletters and lead magnets, runs campaigns "
        "and marketing placements.",
        "template",
        _set(P.DASHBOARD_VIEW, P.ANALYTICS_VIEW, P.ARTICLES_VIEW),
        planned=frozenset(),
    ),
    RoleSpec(
        "newsletter_manager",
        "Newsletter Manager",
        "Manages The Positive Reset newsletter, subscribers, automations and lead magnets.",
        "template",
        _set(P.DASHBOARD_VIEW),
        planned=frozenset(),
    ),
    RoleSpec(
        "seo_manager",
        "SEO Manager",
        "Manages SEO defaults and reviews content for search visibility.",
        "template",
        _set(P.DASHBOARD_VIEW, P.ANALYTICS_VIEW, P.ARTICLES_VIEW, P.SEO_MANAGE, P.PAGES_VIEW),
    ),
    RoleSpec(
        "website_manager",
        "Website Manager",
        "Maintains pages, homepage sections, navigation and site settings.",
        "template",
        _set(
            P.DASHBOARD_VIEW,
            P.PAGES_VIEW,
            P.PAGES_EDIT,
            P.NAVIGATION_MANAGE,
            P.SETTINGS_MANAGE,
            P.MEDIA_VIEW,
        ),
        planned=_set(P.MEDIA_UPLOAD),
    ),
    RoleSpec(
        "finance_manager",
        "Finance Manager",
        "Reviews revenue reports, payments and refunds.",
        "template",
        _set(P.DASHBOARD_VIEW),
        planned=_set(P.FINANCE_MANAGE),
    ),
]

# Batch 03 additions (media, revisions, previews, SEO, redirects, publishing).
# The migration that introduced these permissions grants the same sets to the
# existing system roles and templates; edited templates keep their other changes.
MEDIA_ALL = _set(P.MEDIA_VIEW, P.MEDIA_UPLOAD, P.MEDIA_EDIT, P.MEDIA_REPLACE, P.MEDIA_DELETE)
REVISIONS = _set(P.ARTICLES_VIEW_REVISIONS, P.ARTICLES_RESTORE_REVISIONS, P.ARTICLES_PREVIEW)
BATCH_03_GRANTS: dict[str, frozenset[str]] = {
    "editor": _set(P.MEDIA_UPLOAD, P.MEDIA_EDIT, P.MEDIA_REPLACE, P.SEO_VIEW, P.PUBLISHING_VIEW)
    | REVISIONS,
    "moderator": _set(P.ARTICLES_VIEW_REVISIONS, P.ARTICLES_PREVIEW, P.PUBLISHING_VIEW),
    "analyst": _set(P.ARTICLES_PREVIEW, P.SEO_VIEW, P.PUBLISHING_VIEW),
    "administrator": MEDIA_ALL
    | REVISIONS
    | _set(P.SEO_VIEW, P.REDIRECTS_MANAGE, P.PUBLISHING_VIEW, P.PUBLISHING_MANAGE),
    "editor_in_chief": MEDIA_ALL
    | REVISIONS
    | _set(P.SEO_VIEW, P.PUBLISHING_VIEW, P.PUBLISHING_MANAGE),
    "content_editor": _set(P.MEDIA_UPLOAD, P.MEDIA_EDIT) | REVISIONS,
    "content_writer": _set(P.MEDIA_UPLOAD) | REVISIONS,
    "marketing_manager": _set(P.ARTICLES_PREVIEW, P.SEO_VIEW),
    "seo_manager": _set(
        P.MEDIA_VIEW,
        P.MEDIA_EDIT,
        P.ARTICLES_VIEW_REVISIONS,
        P.ARTICLES_PREVIEW,
        P.SEO_VIEW,
        P.REDIRECTS_MANAGE,
    ),
    "website_manager": _set(
        P.MEDIA_UPLOAD, P.MEDIA_EDIT, P.MEDIA_REPLACE, P.SEO_VIEW, P.PUBLISHING_VIEW
    ),
}


# Batch 04 additions (homepage builder, page publishing, shared sections, branding,
# announcements). Roles only gain what matches their existing responsibilities:
# editors keep editing homepage drafts (as before) but cannot publish the homepage.
WEBSITE_ALL = _set(
    P.HOMEPAGE_VIEW,
    P.HOMEPAGE_EDIT,
    P.HOMEPAGE_PUBLISH,
    P.PAGES_CREATE,
    P.PAGES_PUBLISH,
    P.REUSABLE_SECTIONS_MANAGE,
    P.BRANDING_MANAGE,
    P.ANNOUNCEMENTS_MANAGE,
)
BATCH_04_GRANTS: dict[str, frozenset[str]] = {
    "editor": _set(P.HOMEPAGE_VIEW, P.HOMEPAGE_EDIT),
    "moderator": _set(P.HOMEPAGE_VIEW),
    "administrator": WEBSITE_ALL,
    "editor_in_chief": _set(P.HOMEPAGE_VIEW),
    "seo_manager": _set(P.HOMEPAGE_VIEW),
    "marketing_manager": _set(P.HOMEPAGE_VIEW, P.ANNOUNCEMENTS_MANAGE),
    "website_manager": WEBSITE_ALL,
}
# Custom roles: permissions implied by what a role could already do.
BATCH_04_IMPLIED: dict[str, frozenset[str]] = {
    P.PAGES_VIEW.value: _set(P.HOMEPAGE_VIEW),
    P.PAGES_EDIT.value: _set(P.HOMEPAGE_VIEW, P.HOMEPAGE_EDIT),
    P.SETTINGS_MANAGE.value: _set(P.BRANDING_MANAGE),
}


# Batch 05 additions (digital products, orders, customers, payments, downloads).
# Editorial-only roles gain nothing; refunds, exports and payment configuration stay
# with the roles responsible for them (payments.configure is Super Admin only).
PRODUCTS_ALL = _set(
    P.PRODUCTS_VIEW,
    P.PRODUCTS_CREATE,
    P.PRODUCTS_EDIT,
    P.PRODUCTS_PUBLISH,
    P.PRODUCTS_ARCHIVE,
    P.PRODUCTS_MANAGE_PRICES,
    P.PRODUCTS_MANAGE_FILES,
    P.PRODUCTS_MANAGE_BUNDLES,
)
BATCH_05_GRANTS: dict[str, frozenset[str]] = {
    "administrator": PRODUCTS_ALL
    | _set(
        P.ORDERS_VIEW,
        P.ORDERS_MANAGE,
        P.ORDERS_EXPORT,
        P.CUSTOMERS_VIEW,
        P.CUSTOMERS_SUPPORT,
        P.CUSTOMERS_MANAGE,
        P.ENTITLEMENTS_VIEW,
        P.ENTITLEMENTS_MANAGE,
        P.DOWNLOADS_AUDIT,
        P.PAYMENTS_VIEW_EVENTS,
        P.FINANCE_VIEW,
    ),
    "product_manager": PRODUCTS_ALL | _set(P.MEDIA_VIEW, P.MEDIA_UPLOAD, P.MEDIA_EDIT),
    "orders_manager": _set(
        P.PRODUCTS_VIEW,
        P.ORDERS_VIEW,
        P.ORDERS_MANAGE,
        P.ORDERS_EXPORT,
        P.REFUNDS_ISSUE,
        P.CUSTOMERS_VIEW,
        P.CUSTOMERS_SUPPORT,
        P.ENTITLEMENTS_VIEW,
        P.ENTITLEMENTS_MANAGE,
        P.DOWNLOADS_AUDIT,
        P.PAYMENTS_VIEW_EVENTS,
    ),
    "customer_support": _set(
        P.PRODUCTS_VIEW,
        P.ORDERS_VIEW,
        P.CUSTOMERS_VIEW,
        P.CUSTOMERS_SUPPORT,
        P.ENTITLEMENTS_VIEW,
        P.DOWNLOADS_AUDIT,
    ),
    "finance_manager": _set(
        P.PRODUCTS_VIEW,
        P.ORDERS_VIEW,
        P.ORDERS_EXPORT,
        P.REFUNDS_ISSUE,
        P.PAYMENTS_VIEW_EVENTS,
        P.FINANCE_VIEW,
        P.FINANCE_EXPORT,
    ),
    "marketing_manager": _set(P.PRODUCTS_VIEW),
}

NEWSLETTER_EDITING = _set(
    P.NEWSLETTERS_VIEW, P.NEWSLETTERS_CREATE, P.NEWSLETTERS_EDIT, P.NEWSLETTERS_REPORTS
)
NEWSLETTER_ALL = NEWSLETTER_EDITING | _set(
    P.NEWSLETTERS_PUBLISH,
    P.NEWSLETTERS_SEND,
    P.NEWSLETTERS_SCHEDULE,
    P.EMAIL_TEMPLATES_MANAGE,
    P.EMAIL_AUTOMATIONS_MANAGE,
    P.LEAD_MAGNETS_MANAGE,
)
BATCH_06_GRANTS: dict[str, frozenset[str]] = {
    # Bulk exports and sending settings stay with the Newsletter Manager / Super Admin.
    "administrator": NEWSLETTER_ALL | _set(P.SUBSCRIBERS_VIEW, P.SUBSCRIBERS_MANAGE),
    "newsletter_manager": NEWSLETTER_ALL
    | _set(
        P.SUBSCRIBERS_VIEW,
        P.SUBSCRIBERS_MANAGE,
        P.SUBSCRIBERS_EXPORT,
        P.MEDIA_VIEW,
        P.ARTICLES_VIEW,
        P.PRODUCTS_VIEW,
    ),
    "marketing_manager": NEWSLETTER_EDITING
    | _set(P.SUBSCRIBERS_VIEW, P.LEAD_MAGNETS_MANAGE, P.MEDIA_VIEW),
}

PARTNERSHIP_CORE = _set(
    P.PARTNERSHIPS_VIEW,
    P.PARTNERSHIPS_MANAGE,
    P.SPONSORSHIPS_VIEW,
    P.SPONSORSHIPS_MANAGE,
    P.ADVERTISING_VIEW,
    P.ADVERTISING_MANAGE_BOOKINGS,
    P.MEDIA_KIT_MANAGE,
)
AFFILIATE_ALL = _set(P.AFFILIATES_VIEW, P.AFFILIATES_MANAGE, P.AFFILIATES_MANAGE_LINKS)
BATCH_07_GRANTS: dict[str, frozenset[str]] = {
    "administrator": PARTNERSHIP_CORE
    | AFFILIATE_ALL
    | _set(
        P.SPONSORSHIPS_APPROVE,
        P.ADVERTISING_MANAGE_INVENTORY,
        P.PARTNERSHIP_FINANCE_VIEW,
        P.PARTNERSHIP_REPORTS_EXPORT,
    ),
    "partnerships_manager": PARTNERSHIP_CORE
    | _set(P.ADVERTISING_MANAGE_INVENTORY, P.MEDIA_VIEW, P.ARTICLES_VIEW),
    "marketing_manager": _set(
        P.SPONSORSHIPS_VIEW,
        P.SPONSORSHIPS_MANAGE,
        P.ADVERTISING_VIEW,
        P.ADVERTISING_MANAGE_BOOKINGS,
        P.AFFILIATES_VIEW,
        P.AFFILIATES_MANAGE_LINKS,
    ),
    "affiliate_manager": AFFILIATE_ALL | _set(P.ARTICLES_VIEW, P.PRODUCTS_VIEW),
    "editor_in_chief": _set(P.SPONSORSHIPS_VIEW, P.SPONSORSHIPS_APPROVE),
    "finance_manager": _set(
        P.PARTNERSHIPS_VIEW,
        P.SPONSORSHIPS_VIEW,
        P.ADVERTISING_VIEW,
        P.AFFILIATES_VIEW,
        P.PARTNERSHIP_FINANCE_VIEW,
        P.PARTNERSHIP_FINANCE_MANAGE,
        P.PARTNERSHIP_REPORTS_EXPORT,
    ),
}


BATCH_08_GRANTS: dict[str, frozenset[str]] = {
    "administrator": _set(P.STORAGE_VIEW),
    "website_manager": _set(P.STORAGE_VIEW),
}

COURSE_AUTHORING = _set(
    P.COURSES_VIEW,
    P.COURSES_CREATE,
    P.COURSES_EDIT,
    P.COURSES_MANAGE_CURRICULUM,
    P.COURSES_MANAGE_ASSESSMENTS,
)
COURSE_PUBLISHING = COURSE_AUTHORING | _set(P.COURSES_PUBLISH, P.COURSES_ARCHIVE)
COURSES_ALL = COURSE_PUBLISHING | _set(
    P.COURSES_VIEW_ENROLLMENTS, P.COURSES_MANAGE_ENROLLMENTS, P.COURSES_VIEW_REPORTS
)
BATCH_09_GRANTS: dict[str, frozenset[str]] = {
    "editor": COURSE_PUBLISHING,
    "analyst": _set(P.COURSES_VIEW, P.COURSES_VIEW_REPORTS),
    "administrator": COURSES_ALL,
    "editor_in_chief": COURSE_PUBLISHING | _set(P.COURSES_VIEW_REPORTS),
    "content_editor": COURSE_AUTHORING,
    "customer_support": _set(
        P.COURSES_VIEW, P.COURSES_VIEW_ENROLLMENTS, P.COURSES_MANAGE_ENROLLMENTS
    ),
    "marketing_manager": _set(P.COURSES_VIEW, P.COURSES_VIEW_REPORTS),
    "product_manager": _set(P.COURSES_VIEW),
    "website_manager": _set(P.COURSES_VIEW),
}


LESSON_DRAFTING = _set(P.COURSES_VIEW_DRAFTS, P.COURSES_EDIT_DRAFTS, P.COURSES_VIEW_REVISIONS)
LESSON_PUBLISHING = LESSON_DRAFTING | _set(P.COURSES_PUBLISH_LESSONS, P.COURSES_RESTORE_REVISIONS)
BATCH_091_GRANTS: dict[str, frozenset[str]] = {
    "editor": LESSON_PUBLISHING,
    "administrator": LESSON_PUBLISHING,
    "editor_in_chief": LESSON_PUBLISHING,
    "content_editor": LESSON_DRAFTING,
}


ASSIGNMENT_GRADING = _set(P.ASSIGNMENTS_VIEW, P.ASSIGNMENTS_VIEW_SUBMISSIONS, P.ASSIGNMENTS_GRADE)
ASSIGNMENTS_ALL = ASSIGNMENT_GRADING | _set(
    P.ASSIGNMENTS_MANAGE,
    P.ASSIGNMENTS_PUBLISH_GRADES,
    P.ASSIGNMENTS_MANAGE_EXCEPTIONS,
    P.ASSIGNMENTS_VIEW_REPORTS,
)
BATCH_092_GRANTS: dict[str, frozenset[str]] = {
    "administrator": ASSIGNMENTS_ALL,
    "editor_in_chief": ASSIGNMENTS_ALL,
    "editor": ASSIGNMENTS_ALL - _set(P.ASSIGNMENTS_MANAGE_EXCEPTIONS),
    "content_editor": ASSIGNMENT_GRADING | _set(P.ASSIGNMENTS_MANAGE),
    "analyst": _set(P.ASSIGNMENTS_VIEW, P.ASSIGNMENTS_VIEW_REPORTS),
    "customer_support": _set(P.ASSIGNMENTS_VIEW, P.ASSIGNMENTS_MANAGE_EXCEPTIONS),
}


QUESTION_BANKS_ALL = _set(P.QUESTION_BANKS_VIEW, P.QUESTION_BANKS_MANAGE)
BATCH_092_BANK_GRANTS: dict[str, frozenset[str]] = {
    "administrator": QUESTION_BANKS_ALL,
    "editor_in_chief": QUESTION_BANKS_ALL,
    "editor": QUESTION_BANKS_ALL,
    "content_editor": QUESTION_BANKS_ALL,
}


MEMBERSHIP_PLANS_ALL = _set(P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE, P.MEMBERSHIPS_PUBLISH)
BATCH_10_GRANTS: dict[str, frozenset[str]] = {
    "administrator": MEMBERSHIP_PLANS_ALL,
    "editor_in_chief": MEMBERSHIP_PLANS_ALL,
    "product_manager": _set(P.MEMBERSHIPS_VIEW, P.MEMBERSHIPS_MANAGE),
    "marketing_manager": _set(P.MEMBERSHIPS_VIEW),
    "customer_support": _set(P.MEMBERSHIPS_VIEW),
    "finance_manager": _set(P.MEMBERSHIPS_VIEW),
}


MEMBERSHIP_OPERATIONS = _set(P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS, P.MEMBERSHIPS_VIEW_REPORTS)
BATCH_104_GRANTS: dict[str, frozenset[str]] = {
    "administrator": MEMBERSHIP_OPERATIONS,
    "customer_support": _set(P.MEMBERSHIPS_MANAGE_SUBSCRIPTIONS),
    "finance_manager": _set(P.MEMBERSHIPS_VIEW_REPORTS),
    "analyst": _set(P.MEMBERSHIPS_VIEW_REPORTS),
}


def _with_batch_03(spec: RoleSpec) -> RoleSpec:
    extra = (
        BATCH_03_GRANTS.get(spec.key, frozenset())
        | BATCH_04_GRANTS.get(spec.key, frozenset())
        | BATCH_05_GRANTS.get(spec.key, frozenset())
        | BATCH_06_GRANTS.get(spec.key, frozenset())
        | BATCH_07_GRANTS.get(spec.key, frozenset())
        | BATCH_08_GRANTS.get(spec.key, frozenset())
        | BATCH_09_GRANTS.get(spec.key, frozenset())
        | BATCH_091_GRANTS.get(spec.key, frozenset())
        | BATCH_092_GRANTS.get(spec.key, frozenset())
        | BATCH_092_BANK_GRANTS.get(spec.key, frozenset())
        | BATCH_10_GRANTS.get(spec.key, frozenset())
        | BATCH_104_GRANTS.get(spec.key, frozenset())
    )
    if not extra:
        return spec
    return RoleSpec(
        spec.key,
        spec.label,
        spec.description,
        spec.kind,
        spec.permissions | extra,
        spec.grants_all,
        spec.planned - extra,
    )


SYSTEM_ROLES = [_with_batch_03(r) for r in SYSTEM_ROLES]
TEMPLATE_ROLES = [_with_batch_03(r) for r in TEMPLATE_ROLES]
ROLE_SPECS: dict[str, RoleSpec] = {r.key: r for r in SYSTEM_ROLES + TEMPLATE_ROLES}

for _spec in ROLE_SPECS.values():
    assert _spec.permissions <= AVAILABLE_PERMISSIONS, _spec.key
    assert not (_spec.permissions & SENSITIVE_PERMISSIONS), _spec.key
