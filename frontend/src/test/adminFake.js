import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";
import { createBuilderFake } from "./builderFake";
import { COMMERCE_PERMS, createCommerceAdminFake } from "./commerceFake";
import { COURSE_PERMS, createCourseAdminFake } from "./courseFake";
import { NEWSLETTER_EDITING, NEWSLETTER_PERMS, createNewsletterAdminFake } from "./newsletterFake";
import {
  PARTNERSHIP_PERMS,
  PARTNERSHIP_ROLES,
  createPartnershipAdminFake,
} from "./partnershipFake";

// Mirrors backend/app/auth/permissions.py (available permissions only, plus sensitive ones).
const ARTICLES = ["articles.view", "articles.create", "articles.edit_own", "articles.edit_any"];
const ALL = [
  "dashboard.view",
  "analytics.view",
  ...ARTICLES,
  "articles.submit_review",
  "articles.approve",
  "articles.publish",
  "articles.unpublish",
  "articles.archive",
  "articles.delete",
  "topics.manage",
  "tags.manage",
  "authors.manage",
  "media.view",
  "media.upload",
  "media.edit",
  "media.replace",
  "media.delete",
  "articles.view_revisions",
  "articles.restore_revisions",
  "articles.preview",
  "homepage.view",
  "homepage.edit",
  "homepage.publish",
  "pages.view",
  "pages.edit",
  "pages.create",
  "pages.publish",
  "reusable_sections.manage",
  "branding.manage",
  "announcements.manage",
  "navigation.manage",
  "settings.manage",
  "settings.technical",
  "seo.manage",
  "seo.view",
  "redirects.manage",
  "publishing.view",
  "publishing.manage",
  "users.view",
  "users.manage",
  "roles.manage",
  "roles.assign",
  "audit.view",
  "storage.view",
  ...COURSE_PERMS,
  ...COMMERCE_PERMS,
  ...NEWSLETTER_PERMS,
  ...PARTNERSHIP_PERMS,
];

export const ROLE_PERMS = {
  super_admin: ALL,
  partnerships_manager: PARTNERSHIP_ROLES.partnerships_manager,
  editor: [
    "dashboard.view",
    ...ARTICLES,
    "articles.submit_review",
    "articles.approve",
    "articles.publish",
    "articles.unpublish",
    "articles.archive",
    "topics.manage",
    "tags.manage",
    "authors.manage",
    "media.view",
    "media.upload",
    "media.edit",
    "media.replace",
    "articles.view_revisions",
    "articles.restore_revisions",
    "articles.preview",
    "seo.view",
    "publishing.view",
    "pages.view",
    "pages.edit",
    "homepage.view",
    "homepage.edit",
    // Batch 09: editors author and publish courses (like the backend's Editor role).
    "courses.view",
    "courses.create",
    "courses.edit",
    "courses.publish",
    "courses.archive",
    "courses.manage_curriculum",
    "courses.manage_assessments",
    // Batch 09.1: lesson drafts and revisions.
    "courses.view_drafts",
    "courses.edit_drafts",
    "courses.publish_lessons",
    "courses.view_revisions",
    "courses.restore_revisions",
  ],
  moderator: [
    "dashboard.view",
    "articles.view",
    "articles.unpublish",
    "articles.archive",
    "media.view",
    "pages.view",
    "homepage.view",
    "articles.view_revisions",
    "articles.preview",
    "publishing.view",
  ],
  analyst: [
    "dashboard.view",
    "analytics.view",
    "articles.view",
    "media.view",
    "articles.preview",
    "seo.view",
    "publishing.view",
    "courses.view",
    "courses.view_reports",
  ],
  content_writer: [
    "dashboard.view",
    "articles.create",
    "articles.edit_own",
    "articles.submit_review",
    "media.view",
    "media.upload",
    "articles.view_revisions",
    "articles.restore_revisions",
    "articles.preview",
  ],
  content_editor: [
    "dashboard.view",
    ...ARTICLES,
    "articles.submit_review",
    "media.view",
    "media.upload",
    "media.edit",
    "articles.view_revisions",
    "articles.restore_revisions",
    "articles.preview",
    // Courses: authoring and lesson drafts, no publishing (like the backend role).
    "courses.view",
    "courses.create",
    "courses.edit",
    "courses.manage_curriculum",
    "courses.manage_assessments",
    "courses.view_drafts",
    "courses.edit_drafts",
    "courses.view_revisions",
  ],
  administrator: ALL.filter(
    (p) =>
      ![
        "roles.manage",
        "roles.assign",
        "settings.technical",
        "payments.configure",
        "refunds.issue",
        "finance.export",
      ].includes(p),
  ),
  product_manager: [
    "dashboard.view",
    ...COMMERCE_PERMS.filter((p) => p.startsWith("products.")),
    "media.view",
    "media.upload",
    "media.edit",
  ],
  orders_manager: [
    "dashboard.view",
    "products.view",
    "orders.view",
    "orders.manage",
    "orders.export",
    "refunds.issue",
    "customers.view",
    "customers.support",
    "entitlements.view",
    "entitlements.manage",
    "downloads.audit",
    "payments.view_events",
  ],
  customer_support: [
    "dashboard.view",
    "products.view",
    "orders.view",
    "customers.view",
    "customers.support",
    "entitlements.view",
    "downloads.audit",
  ],
  finance_manager: [
    "dashboard.view",
    "products.view",
    "orders.view",
    "orders.export",
    "refunds.issue",
    "payments.view_events",
    "finance.view",
    "finance.export",
    ...PARTNERSHIP_ROLES.finance_manager.filter((p) => p !== "dashboard.view"),
  ],
  website_manager: [
    "dashboard.view",
    "homepage.view",
    "homepage.edit",
    "homepage.publish",
    "pages.view",
    "pages.edit",
    "pages.create",
    "pages.publish",
    "reusable_sections.manage",
    "branding.manage",
    "announcements.manage",
    "navigation.manage",
    "settings.manage",
    "media.view",
    "media.upload",
    "publishing.view",
  ],
  marketing_manager: [
    "dashboard.view",
    "analytics.view",
    "homepage.view",
    "announcements.manage",
    ...NEWSLETTER_EDITING,
    "subscribers.view",
    "lead_magnets.manage",
  ],
  newsletter_manager: [
    "dashboard.view",
    ...NEWSLETTER_PERMS.filter((p) => p !== "email_settings.manage"),
  ],
  // A specialised role without dashboard access, used to test landing routes.
  pages_only: ["pages.view"],
};

/** Simplified mirror of article_admin.capabilities() for the fake API. */
export function articleCan(article, permissions = ALL, userId = 1) {
  const has = (p) => permissions.includes(p);
  const owner = article.created_by?.id === userId;
  const { status } = article;
  return {
    edit: has("articles.edit_any") || (has("articles.edit_own") && owner && status === "draft"),
    submit:
      has("articles.submit_review") &&
      (owner || has("articles.edit_any")) &&
      status === "draft" &&
      article.review_status !== "submitted",
    approve: has("articles.approve") && article.review_status === "submitted",
    publish: has("articles.publish") && ["draft", "scheduled"].includes(status),
    unpublish: has("articles.unpublish") && ["published", "scheduled"].includes(status),
    archive: has("articles.archive") && status !== "archived",
    restore: has("articles.archive") && status === "archived",
    delete: has("articles.delete") && !article.slug_locked && status === "draft",
    publish_changes:
      has("articles.publish") && status === "published" && article.has_pending_changes,
    discard_changes:
      Boolean(article.has_pending_changes) &&
      (has("articles.edit_any") || (has("articles.edit_own") && owner && status === "draft")),
    view_revisions: has("articles.view_revisions"),
    restore_revision:
      has("articles.restore_revisions") &&
      (has("articles.edit_any") || (has("articles.edit_own") && owner && status === "draft")),
    preview: has("articles.preview"),
    edit_slug: !article.first_published_at || has("seo.manage"),
    edit_indexing: has("seo.manage"),
    save_live: has("articles.publish"),
  };
}

export function adminUser(role = "super_admin") {
  return {
    id: 1,
    email: `${role}@example.org`,
    display_name: `Test ${role}`,
    status: "active",
    roles: [role],
    permissions: ROLE_PERMS[role],
  };
}

const unauthorized = () =>
  Promise.reject(
    new ApiError({
      status: 401,
      code: "authentication_required",
      message: "Authentication is required.",
    }),
  );

export function makeMedia(overrides = {}) {
  return {
    id: 3,
    filename: "calm-lake",
    title: "Calm lake",
    alt_text: "A calm lake at dawn",
    caption: "",
    credit: "",
    source_url: null,
    url: "/media/abc/v1/calm-lake-1280.jpg",
    thumbnail_url: "/media/abc/v1/calm-lake-320.webp",
    mime_type: "image/jpeg",
    width: 1600,
    height: 1000,
    size_bytes: 250000,
    status: "active",
    managed: true,
    usage_count: 1,
    missing_alt: false,
    focal_point: { x: 0.5, y: 0.5 },
    created_at: "2026-10-20T10:00:00.000Z",
    updated_at: "2026-10-20T10:00:00.000Z",
    ...overrides,
  };
}

export function mediaDetail(item) {
  return {
    ...item,
    version: item.version ?? 1,
    original: {
      filename: `${item.filename}.jpg`,
      mime_type: "image/jpeg",
      size_bytes: 400000,
      retained: true,
    },
    variants: [
      {
        preset: "responsive",
        format: "webp",
        width: 320,
        height: 200,
        size_bytes: 12000,
        url: item.thumbnail_url,
      },
      {
        preset: "responsive",
        format: "jpeg",
        width: 1280,
        height: 800,
        size_bytes: 140000,
        url: item.url,
      },
    ],
    variants_size_bytes: 152000,
    image: { src: item.url, alt: item.alt_text, width: item.width, height: item.height },
    usage: item.usage_count
      ? [{ type: "article", id: 7, label: "Finding Calm", field: "featured image", public: false }]
      : [],
  };
}

export function makeArticle(overrides = {}) {
  return {
    id: 7,
    title: "Finding Calm",
    slug: "finding-calm",
    status: "draft",
    featured: false,
    is_public: false,
    published_at: null,
    updated_at: "2026-10-20T10:00:00.000Z",
    author: { id: 1, display_name: "TPA Editorial" },
    primary_topic: { id: 1, name: "Positive Mindset" },
    source: "original",
    subtitle: null,
    excerpt: "Small habits.",
    body: [{ type: "paragraph", text: "Hello world." }],
    author_id: 1,
    primary_topic_id: 1,
    secondary_topic_ids: [],
    tag_ids: [],
    featured_image_id: 3,
    social_image_id: null,
    seo_title: null,
    meta_description: null,
    canonical_url: null,
    noindex: false,
    original_url: null,
    original_slug: null,
    slug_locked: false,
    review_status: "none",
    lock_version: 1,
    has_pending_changes: false,
    pending_fields: [],
    social_title: null,
    social_description: null,
    submitted_at: null,
    approved_at: null,
    created_by: { id: 1, display_name: "Site Owner" },
    ...overrides,
  };
}

export const CATALOGUE = [
  {
    name: "Articles",
    permissions: [
      { key: "articles.view", label: "View all articles", available: true, sensitive: false },
      { key: "articles.create", label: "Create articles", available: true, sensitive: false },
      { key: "articles.edit_own", label: "Edit own drafts", available: true, sensitive: false },
      { key: "articles.edit_any", label: "Edit any article", available: true, sensitive: false },
      { key: "articles.publish", label: "Publish articles", available: true, sensitive: false },
    ],
  },
  {
    name: "Digital products",
    permissions: [
      { key: "products.view", label: "View products", available: false, sensitive: false },
    ],
  },
  {
    name: "Users, roles & audit",
    permissions: [
      { key: "users.view", label: "View users", available: true, sensitive: false },
      { key: "roles.manage", label: "Manage roles", available: true, sensitive: true },
    ],
  },
];

const role = (id, name, label, kind, permissions, extra = {}) => ({
  id,
  name,
  label,
  description: `${label} role.`,
  kind,
  is_active: true,
  is_protected: kind === "system",
  grants_all: false,
  permissions,
  planned_permissions: [],
  user_count: 1,
  updated_at: "2026-10-20T10:00:00.000Z",
  ...extra,
});

export function makeRoles() {
  return [
    role(1, "super_admin", "Super Admin", "system", ALL, { grants_all: true }),
    role(2, "editor", "Editor", "system", ROLE_PERMS.editor),
    role(3, "moderator", "Moderator", "system", ROLE_PERMS.moderator),
    role(4, "analyst", "Analyst", "system", ROLE_PERMS.analyst),
    role(5, "content_writer", "Content Writer", "template", ROLE_PERMS.content_writer, {
      user_count: 0,
    }),
    role(6, "product_manager", "Product Manager", "template", ["dashboard.view"], {
      user_count: 0,
      planned_permissions: ["products.view"],
    }),
    role(7, "old_reviewers", "Old Reviewers", "custom", ["articles.view"], {
      is_active: false,
      user_count: 0,
    }),
  ];
}

/** In-memory admin API double. `role` null means "not signed in". */
const VALID_TOKEN = "valid-link-token-0123456789abcdef";
export { VALID_TOKEN };

export function createFakeAdminApi({ role = "super_admin", article = makeArticle() } = {}) {
  let user = role ? adminUser(role) : null;
  let current = article;
  let roles = makeRoles();
  let media = [
    makeMedia(),
    makeMedia({ id: 4, filename: "old-sign", title: "Old sign", status: "archived" }),
  ];
  let redirects = [
    {
      id: 1,
      source_path: "/2019/05/old-post",
      destination: "/articles/finding-calm",
      status_code: 301,
      is_active: true,
      origin: "import",
      note: "",
      updated_at: "2026-10-20T10:00:00.000Z",
    },
  ];
  const jobs = [
    {
      id: 2,
      status: "failed",
      reasons: ["article_published"],
      attempts: 3,
      max_attempts: 3,
      created_at: "2026-10-21T10:00:00.000Z",
      duration_seconds: 12.5,
      error: "The build command failed (exit code 1).",
      log_tail: "vite build failed",
      release: null,
    },
    {
      id: 1,
      status: "succeeded",
      reasons: ["manual_request"],
      attempts: 1,
      max_attempts: 3,
      created_at: "2026-10-20T10:00:00.000Z",
      finished_at: "2026-10-20T10:01:00.000Z",
      duration_seconds: 48.2,
      release: "20261020-100000-job1",
      error: null,
      log_tail: "built",
    },
  ];
  let revisions = [
    {
      id: 12,
      number: 2,
      kind: "manual",
      summary: "Changed title",
      editor: { id: 1, display_name: "Site Owner" },
      updated_at: "2026-10-21T10:00:00.000Z",
    },
    {
      id: 11,
      number: 1,
      kind: "manual",
      summary: "Created",
      editor: { id: 1, display_name: "Site Owner" },
      updated_at: "2026-10-20T10:00:00.000Z",
    },
  ];
  const ok = (data, meta) => Promise.resolve({ data, meta });
  // Articles carry server-computed capabilities for the signed-in user.
  const withCan = (a) => ({ ...a, can: articleCan(a, user?.permissions ?? [], user?.id) });
  const settings = {
    groups: [
      {
        name: "Branding",
        settings: [
          {
            key: "site.name",
            label: "Site name",
            type: "string",
            max_length: 80,
            help: "",
            value: "Think Positive Always",
            is_default: true,
          },
          {
            key: "branding.logo_media_id",
            label: "Logo image",
            type: "media",
            max_length: 200,
            help: "Optional.",
            value: null,
            is_default: true,
          },
          {
            key: "branding.palette",
            label: "Colour palette",
            type: "choice",
            max_length: 40,
            help: "",
            value: "classic",
            is_default: true,
            choices: [
              { value: "classic", label: "Classic: ivory, sage and gold" },
              { value: "evergreen", label: "Evergreen: deeper greens" },
              { value: "golden_hour", label: "Golden hour: warmer gold accents" },
            ],
          },
        ],
      },
      {
        name: "Footer",
        settings: [
          {
            key: "footer.text",
            label: "Footer introduction",
            type: "text",
            max_length: 400,
            help: "",
            value: "Encouragement.",
            is_default: true,
          },
          {
            key: "footer.copyright",
            label: "Copyright line",
            type: "string",
            max_length: 160,
            help: "{year} and {site_name} are filled in automatically.",
            value: "© {year} {site_name}. All rights reserved.",
            is_default: true,
          },
        ],
      },
      {
        name: "Header",
        settings: [
          {
            key: "header.cta_label",
            label: "Header button label",
            type: "string",
            max_length: 30,
            help: "",
            value: "Newsletter",
            is_default: true,
          },
        ],
      },
      {
        name: "Contact",
        settings: [
          {
            key: "contact.email",
            label: "Contact email",
            type: "email",
            max_length: 254,
            help: "",
            value: "",
            is_default: true,
          },
        ],
      },
    ],
  };

  return {
    onSessionExpired: vi.fn(),
    auth: {
      me: vi.fn(() => (user ? ok({ user }) : unauthorized())),
      login: vi.fn(({ email, password }) => {
        if (password === "Correct-Horse-Battery-9") {
          user = { ...adminUser("editor"), email };
          return ok({ user });
        }
        return Promise.reject(
          new ApiError({
            status: 401,
            code: "authentication_failed",
            message: "Invalid email or password.",
          }),
        );
      }),
      logout: vi.fn(() => {
        user = null;
        return ok({ logged_out: true });
      }),
      changePassword: vi.fn(() => ok({ user })),
      verifyInvitation: vi.fn((token) =>
        token === VALID_TOKEN
          ? ok({
              email: "invitee@example.org",
              display_name: "Invitee",
              roles: ["editor"],
              expires_at: "2026-10-25T10:00:00.000Z",
            })
          : Promise.reject(
              new ApiError({ status: 400, code: "link_invalid", message: "This link is invalid." }),
            ),
      ),
      acceptInvitation: vi.fn(({ display_name }) => {
        user = { ...adminUser("editor"), email: "invitee@example.org", display_name };
        return ok({ user });
      }),
      verifyPasswordReset: vi.fn((token) =>
        token === VALID_TOKEN
          ? ok({ email: "writer@example.org", expires_at: "2026-10-22T10:00:00.000Z" })
          : Promise.reject(
              new ApiError({ status: 400, code: "link_invalid", message: "This link is invalid." }),
            ),
      ),
      completePasswordReset: vi.fn(() => ok({ reset: true })),
    },
    analytics: vi.fn(() =>
      ok({
        articles_by_status: { draft: 1, scheduled: 0, published: 5, archived: 0 },
        published_by_topic: [{ topic: "Positive Mindset", count: 3 }],
        published_by_month: [{ month: "2026-09", count: 5 }],
        note: "Traffic analytics arrive later.",
      }),
    ),
    dashboard: vi.fn(() =>
      ok({
        articles: ARTICLES.some((p) => user?.permissions.includes(p))
          ? { total: 6, draft: 1, scheduled: 0, published: 5, archived: 0 }
          : null,
        topics_total: 8,
        authors_total: 1,
        tags_total: 18,
        recent_articles: ARTICLES.some((p) => user?.permissions.includes(p))
          ? [makeArticle()]
          : null,
        recent_audit: user?.permissions.includes("audit.view")
          ? [
              {
                id: 1,
                action: "auth.login",
                resource_type: "user",
                resource_id: "1",
                details: {},
                actor: { id: 1, display_name: "Owner" },
                created_at: "2026-10-20T10:00:00.000Z",
              },
            ]
          : null,
        publishing: {
          last_build_at: null,
          build_manifest_found: false,
          latest_public_change_at: null,
          rebuild_required: false,
          scheduled_due_count: 0,
          rebuild_command: "./scripts/build-production.sh",
        },
      }),
    ),
    articles: {
      list: vi.fn((params = {}) => {
        const rows = [
          current,
          makeArticle({
            id: 8,
            title: "Quiet Confidence",
            slug: "quiet-confidence",
            status: "published",
          }),
        ];
        const filtered = params.status ? rows.filter((r) => r.status === params.status) : rows;
        return ok(filtered, {
          pagination: {
            page: 1,
            page_size: 20,
            total: filtered.length,
            total_pages: 1,
            has_next: false,
            has_prev: false,
          },
          counts: { draft: 1, scheduled: 0, published: 1, archived: 0 },
        });
      }),
      get: vi.fn(() => ok(withCan(current))),
      create: vi.fn((body) => {
        current = makeArticle({ ...body, id: 9, created_by: { id: user.id } });
        return ok(withCan(current));
      }),
      update: vi.fn((id, body) => {
        // eslint-disable-next-line no-unused-vars
        const { mode, lock_version, change_summary, ...content } = body;
        current = {
          ...current,
          ...content,
          lock_version: (current.lock_version ?? 1) + 1,
          updated_at: new Date().toISOString(),
        };
        return Promise.resolve({ data: withCan(current), meta: { save_result: "saved" } });
      }),
      submit: vi.fn(() => {
        current = { ...current, review_status: "submitted", updated_at: new Date().toISOString() };
        return ok(withCan(current));
      }),
      approve: vi.fn(() => {
        current = { ...current, review_status: "approved", updated_at: new Date().toISOString() };
        return ok(withCan(current));
      }),
      remove: vi.fn(() => ok({ deleted: true })),
      publishChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      discardChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      revisions: vi.fn(() => ok(revisions)),
      revision: vi.fn((id, rid) => ok({ ...revisions.find((r) => r.id === rid), snapshot: {} })),
      compareRevisions: vi.fn(() =>
        ok({
          from: revisions[1],
          to: revisions[0],
          fields: [{ field: "title", label: "title", from: "Old title", to: "Finding Calm" }],
          blocks: [
            { index: 0, change: "changed", from: "paragraph: Hi", to: "paragraph: Hello world." },
          ],
        }),
      ),
      restoreRevision: vi.fn((id, rid) => {
        current = { ...current, title: "Old title", lock_version: (current.lock_version ?? 1) + 1 };
        revisions = [
          {
            id: 13,
            number: 3,
            kind: "restore",
            summary: `Restored revision #${rid === 11 ? 1 : 2}`,
            editor: null,
            updated_at: "2026-10-22T10:00:00.000Z",
          },
          ...revisions,
        ];
        return Promise.resolve({ data: withCan(current), meta: { save_result: "saved" } });
      }),
      seoChecks: vi.fn(() =>
        ok({
          checks: [
            {
              code: "missing_meta_description",
              severity: "warning",
              message: "No meta description.",
              field: "meta_description",
            },
          ],
          counts: { error: 0, warning: 1, info: 0 },
          preview: {
            title: current.title,
            url: "https://example.org/articles/finding-calm",
            description: "",
            indexable: true,
          },
        }),
      ),
      slugCheck: vi.fn((slug) => ok({ slug, valid: true, available: slug !== "taken" })),
      publish: vi.fn(() => {
        current = {
          ...current,
          status: "published",
          is_public: true,
          published_at: "2026-10-21T09:00:00.000Z",
          slug_locked: true,
          updated_at: new Date().toISOString(),
        };
        return ok(withCan(current));
      }),
      unpublish: vi.fn(() => {
        current = { ...current, status: "draft", updated_at: new Date().toISOString() };
        return ok(withCan(current));
      }),
      archive: vi.fn(() => ok(withCan(current))),
      restore: vi.fn(() => ok(withCan(current))),
      preview: vi.fn(() => ok({})),
    },
    topics: {
      list: vi.fn(() =>
        ok([
          {
            id: 1,
            name: "Positive Mindset",
            slug: "positive-mindset",
            status: "active",
            article_count: 2,
          },
        ]),
      ),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      reassign: vi.fn(),
    },
    authors: {
      list: vi.fn(() =>
        ok([
          {
            id: 1,
            display_name: "TPA Editorial",
            slug: "tpa-editorial",
            status: "active",
            article_count: 6,
          },
        ]),
      ),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      reassign: vi.fn(),
    },
    tags: {
      list: vi.fn(() => ok([{ id: 1, name: "mindset", slug: "mindset", article_count: 1 }])),
      create: vi.fn(() => ok({ id: 2 })),
      update: vi.fn(),
      remove: vi.fn(),
      reassign: vi.fn(),
    },
    media: {
      list: vi.fn((params = {}) => {
        const rows = media.filter(
          (m) =>
            (params.status === "archived" ? m.status === "archived" : m.status !== "archived") &&
            (!params.q || m.filename.includes(params.q) || m.title.includes(params.q)) &&
            (params.usage !== "missing_alt" || m.missing_alt),
        );
        return ok(rows, {
          pagination: {
            page: 1,
            page_size: 30,
            total: rows.length,
            total_pages: 1,
            has_next: false,
            has_prev: false,
          },
        });
      }),
      get: vi.fn((id) => ok(mediaDetail(media.find((m) => m.id === Number(id)) ?? media[0]))),
      stats: vi.fn(() =>
        ok({
          assets: 1,
          originals_bytes: 400000,
          variants_bytes: 250000,
          superseded_bytes: 0,
          max_upload_mb: 20,
          avif_enabled: true,
          accepted_types: ["image/jpeg", "image/png"],
          presets: [],
        }),
      ),
      upload: vi.fn((file, fields, onProgress) => {
        onProgress?.(60);
        const created = makeMedia({
          id: 50 + media.length,
          filename: file.name.replace(/\..*$/, ""),
        });
        media = [created, ...media];
        return ok({ ...mediaDetail(created), duplicate: false });
      }),
      update: vi.fn((id, body) => {
        media = media.map((m) =>
          m.id === Number(id) ? { ...m, ...body, missing_alt: !body.alt_text && m.missing_alt } : m,
        );
        return ok(mediaDetail(media.find((m) => m.id === Number(id))));
      }),
      replace: vi.fn((id) =>
        ok({ ...mediaDetail(media.find((m) => m.id === Number(id))), version: 2 }),
      ),
      archive: vi.fn((id) => {
        media = media.map((m) => (m.id === Number(id) ? { ...m, status: "archived" } : m));
        return ok(mediaDetail(media.find((m) => m.id === Number(id))));
      }),
      restore: vi.fn((id) => ok(mediaDetail(media.find((m) => m.id === Number(id))))),
      remove: vi.fn(() => ok({ deleted: true })),
      publishChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      discardChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      revisions: vi.fn(() => ok(revisions)),
      revision: vi.fn((id, rid) => ok({ ...revisions.find((r) => r.id === rid), snapshot: {} })),
      compareRevisions: vi.fn(() =>
        ok({
          from: revisions[1],
          to: revisions[0],
          fields: [{ field: "title", label: "title", from: "Old title", to: "Finding Calm" }],
          blocks: [
            { index: 0, change: "changed", from: "paragraph: Hi", to: "paragraph: Hello world." },
          ],
        }),
      ),
      restoreRevision: vi.fn((id, rid) => {
        current = { ...current, title: "Old title", lock_version: (current.lock_version ?? 1) + 1 };
        revisions = [
          {
            id: 13,
            number: 3,
            kind: "restore",
            summary: `Restored revision #${rid === 11 ? 1 : 2}`,
            editor: null,
            updated_at: "2026-10-22T10:00:00.000Z",
          },
          ...revisions,
        ];
        return Promise.resolve({ data: withCan(current), meta: { save_result: "saved" } });
      }),
      seoChecks: vi.fn(() =>
        ok({
          checks: [
            {
              code: "missing_meta_description",
              severity: "warning",
              message: "No meta description.",
              field: "meta_description",
            },
          ],
          counts: { error: 0, warning: 1, info: 0 },
          preview: {
            title: current.title,
            url: "https://example.org/articles/finding-calm",
            description: "",
            indexable: true,
          },
        }),
      ),
      slugCheck: vi.fn((slug) => ok({ slug, valid: true, available: slug !== "taken" })),
    },
    publishing: {
      status: vi.fn(() => ok({ jobs: {} })),
      jobs: vi.fn(() =>
        ok(jobs, {
          pagination: { page: 1, page_size: 20, total: jobs.length, total_pages: 1 },
          summary: {
            running: null,
            pending: null,
            last_success: jobs.find((j) => j.status === "succeeded") ?? null,
            last_failure: jobs.find((j) => j.status === "failed") ?? null,
          },
        }),
      ),
      request: vi.fn(() => ok({ id: 99, status: "pending" })),
      retry: vi.fn(() => ok({ id: 100, status: "pending" })),
      cancel: vi.fn(() => ok({ id: 3, status: "cancelled" })),
    },
    seo: {
      overview: vi.fn(() =>
        ok({
          published_articles: 6,
          totals: {
            missing_seo_title: 6,
            missing_meta_description: 2,
            featured_alt_missing: 0,
            missing_featured_image: 0,
            noindex: 1,
            broken_internal_link: 1,
            external_canonical: 0,
          },
          articles_with_issues: [
            {
              id: 8,
              title: "Quiet Confidence",
              slug: "quiet-confidence",
              issues: [
                {
                  code: "broken_internal_link",
                  severity: "warning",
                  message: "The link /articles/gone does not point to a published page.",
                },
              ],
            },
          ],
          articles_with_issues_total: 1,
          redirects: { total: 2, active: 1 },
          sitemap: { urls: 25, articles: 5, images: 9, indexing_enabled_in_build: false },
          build: { last_build_at: null, indexing_enabled: false, rebuild_required: true },
        }),
      ),
    },
    redirects: {
      list: vi.fn(() =>
        ok(redirects, {
          pagination: { page: 1, page_size: 50, total: redirects.length, total_pages: 1 },
        }),
      ),
      create: vi.fn((body) => {
        if (body.source_path === body.destination)
          return Promise.reject(
            new ApiError({
              status: 400,
              code: "validation_error",
              message: "One or more parameters are invalid.",
              details: { destination: ["A path cannot redirect to itself."] },
            }),
          );
        const created = { id: 10 + redirects.length, origin: "manual", ...body };
        redirects = [created, ...redirects];
        return ok(created);
      }),
      update: vi.fn((id, body) => ok({ id, ...body })),
      remove: vi.fn(() => ok({ deleted: true })),
      publishChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      discardChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      revisions: vi.fn(() => ok(revisions)),
      revision: vi.fn((id, rid) => ok({ ...revisions.find((r) => r.id === rid), snapshot: {} })),
      compareRevisions: vi.fn(() =>
        ok({
          from: revisions[1],
          to: revisions[0],
          fields: [{ field: "title", label: "title", from: "Old title", to: "Finding Calm" }],
          blocks: [
            { index: 0, change: "changed", from: "paragraph: Hi", to: "paragraph: Hello world." },
          ],
        }),
      ),
      restoreRevision: vi.fn((id, rid) => {
        current = { ...current, title: "Old title", lock_version: (current.lock_version ?? 1) + 1 };
        revisions = [
          {
            id: 13,
            number: 3,
            kind: "restore",
            summary: `Restored revision #${rid === 11 ? 1 : 2}`,
            editor: null,
            updated_at: "2026-10-22T10:00:00.000Z",
          },
          ...revisions,
        ];
        return Promise.resolve({ data: withCan(current), meta: { save_result: "saved" } });
      }),
      seoChecks: vi.fn(() =>
        ok({
          checks: [
            {
              code: "missing_meta_description",
              severity: "warning",
              message: "No meta description.",
              field: "meta_description",
            },
          ],
          counts: { error: 0, warning: 1, info: 0 },
          preview: {
            title: current.title,
            url: "https://example.org/articles/finding-calm",
            description: "",
            indexable: true,
          },
        }),
      ),
      slugCheck: vi.fn((slug) => ok({ slug, valid: true, available: slug !== "taken" })),
      import: vi.fn((csv, dryRun) =>
        ok({
          created: dryRun ? 0 : 1,
          valid: 1,
          errors: [{ row: 2, source_path: "/admin", error: "This path cannot be redirected." }],
        }),
      ),
      exportUrl: () => "/api/v1/admin/redirects/export",
    },
    pages: {
      list: vi.fn(() => ok([])),
      get: vi.fn(),
      update: vi.fn(),
      sectionTypes: vi.fn(() => ok([])),
      updateSection: vi.fn(),
      reorder: vi.fn(),
    },
    navigation: {
      list: vi.fn(() =>
        ok([
          {
            key: "primary",
            name: "Header navigation",
            help: "",
            is_default: false,
            allows_groups: true,
            warnings: ["/old-page does not point to a published page yet."],
            items: [
              {
                label: "Home",
                link_type: "internal",
                url: "/",
                open_in_new_tab: false,
                is_visible: true,
                visibility: "all",
                children: [],
              },
              {
                label: "Old",
                link_type: "internal",
                url: "/old-page",
                open_in_new_tab: false,
                is_visible: true,
                visibility: "all",
                children: [],
              },
            ],
          },
          {
            key: "mobile",
            name: "Mobile navigation",
            help: "Leave empty to use the header navigation on mobile.",
            is_default: true,
            allows_groups: true,
            warnings: [],
            items: [],
          },
          {
            key: "legal",
            name: "Footer legal links",
            help: "",
            is_default: true,
            allows_groups: false,
            warnings: [],
            items: [],
          },
        ]),
      ),
      save: vi.fn((key, items) =>
        ok({
          key,
          name: key,
          help: "",
          is_default: false,
          allows_groups: key !== "legal",
          warnings: [],
          items,
        }),
      ),
    },
    settings: {
      get: vi.fn((groups) =>
        ok({
          groups: settings.groups.filter((g) => !groups || groups.includes(g.name)),
        }),
      ),
      save: vi.fn((values, groups) => {
        settings.groups.forEach((g) =>
          g.settings.forEach((s) => s.key in values && (s.value = values[s.key])),
        );
        return ok({ groups: settings.groups.filter((g) => !groups || groups.includes(g.name)) });
      }),
    },
    users: {
      list: vi.fn((params = {}) => {
        const rows = [
          {
            ...adminUser("super_admin"),
            id: 1,
            display_name: "Site Owner",
            email: "owner@example.org",
            last_login_at: null,
          },
          {
            ...adminUser("editor"),
            id: 2,
            display_name: "Ngozi Writer",
            email: "ngozi@example.org",
            last_login_at: null,
          },
          {
            ...adminUser("analyst"),
            id: 3,
            display_name: "Old Analyst",
            email: "old@example.org",
            status: "disabled",
            last_login_at: null,
          },
        ];
        return ok(
          rows.filter(
            (u) =>
              (!params.q ||
                u.email.includes(params.q) ||
                u.display_name.toLowerCase().includes(params.q.toLowerCase())) &&
              (!params.status || u.status === params.status) &&
              (!params.role || u.roles.includes(params.role)),
          ),
        );
      }),
      get: vi.fn((id) =>
        ok({
          ...adminUser("editor"),
          id,
          display_name: "Ngozi Writer",
          email: "ngozi@example.org",
          created_at: "2026-10-01T10:00:00.000Z",
          email_verified_at: null,
          is_last_super_admin: false,
          account_links: [],
          recent_activity: [
            { id: 9, action: "auth.login", created_at: "2026-10-20T10:00:00.000Z" },
          ],
        }),
      ),
      create: vi.fn((body) => ok({ id: 4, ...body })),
      update: vi.fn((id, body) => ok({ id, ...body })),
      resetPassword: vi.fn(() => ok({ reset: true })),
      sendPasswordReset: vi.fn(() =>
        ok({ id: 5, purpose: "password_reset", delivery: "development_console" }),
      ),
      roles: vi.fn(() => ok(roles)),
      permissions: vi.fn(() => ok(CATALOGUE)),
    },
    roles: {
      list: vi.fn(() => ok(roles)),
      get: vi.fn((id) => {
        const found = roles.find((r) => r.id === Number(id));
        return found
          ? ok({ ...found, users: [], pending_invitations: 0 })
          : Promise.reject(new ApiError({ status: 404, code: "not_found", message: "Not found." }));
      }),
      create: vi.fn((body) => {
        const created = role(20, "guest_reviewer", body.label, "custom", body.permissions, {
          user_count: 0,
        });
        roles = [...roles, created];
        return ok({ ...created, users: [], pending_invitations: 0 });
      }),
      update: vi.fn((id, body) => {
        roles = roles.map((r) => (r.id === Number(id) ? { ...r, ...body } : r));
        const updated = roles.find((r) => r.id === Number(id));
        return ok({ ...updated, users: [], pending_invitations: 0 });
      }),
      remove: vi.fn(() => ok({ deleted: true })),
      publishChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      discardChanges: vi.fn(() => {
        current = { ...current, has_pending_changes: false, pending_fields: [] };
        return ok(withCan(current));
      }),
      revisions: vi.fn(() => ok(revisions)),
      revision: vi.fn((id, rid) => ok({ ...revisions.find((r) => r.id === rid), snapshot: {} })),
      compareRevisions: vi.fn(() =>
        ok({
          from: revisions[1],
          to: revisions[0],
          fields: [{ field: "title", label: "title", from: "Old title", to: "Finding Calm" }],
          blocks: [
            { index: 0, change: "changed", from: "paragraph: Hi", to: "paragraph: Hello world." },
          ],
        }),
      ),
      restoreRevision: vi.fn((id, rid) => {
        current = { ...current, title: "Old title", lock_version: (current.lock_version ?? 1) + 1 };
        revisions = [
          {
            id: 13,
            number: 3,
            kind: "restore",
            summary: `Restored revision #${rid === 11 ? 1 : 2}`,
            editor: null,
            updated_at: "2026-10-22T10:00:00.000Z",
          },
          ...revisions,
        ];
        return Promise.resolve({ data: withCan(current), meta: { save_result: "saved" } });
      }),
      seoChecks: vi.fn(() =>
        ok({
          checks: [
            {
              code: "missing_meta_description",
              severity: "warning",
              message: "No meta description.",
              field: "meta_description",
            },
          ],
          counts: { error: 0, warning: 1, info: 0 },
          preview: {
            title: current.title,
            url: "https://example.org/articles/finding-calm",
            description: "",
            indexable: true,
          },
        }),
      ),
      slugCheck: vi.fn((slug) => ok({ slug, valid: true, available: slug !== "taken" })),
      permissions: vi.fn(() => ok(CATALOGUE)),
    },
    invitations: {
      list: vi.fn(() =>
        ok([
          {
            id: 11,
            email: "pending@example.org",
            display_name: null,
            roles: ["moderator"],
            status: "pending",
            expires_at: "2026-10-25T10:00:00.000Z",
            created_by: { id: 1, display_name: "Site Owner" },
          },
        ]),
      ),
      create: vi.fn((body) =>
        ok({
          id: 12,
          email: body.email,
          roles: body.roles,
          status: "pending",
          delivery: "development_console",
        }),
      ),
      revoke: vi.fn(() => ok({ id: 11, status: "revoked" })),
      resend: vi.fn(() => ok({ id: 11, status: "pending", delivery: "development_console" })),
    },
    audit: { list: vi.fn(() => ok([], { pagination: null })) },
    ...createBuilderFake(() => user),
    ...createCommerceAdminFake(() => user),
    ...createCourseAdminFake(() => user),
    ...createNewsletterAdminFake(() => user),
    ...createPartnershipAdminFake(),
  };
}

/**
 * The explicit "Save changes" call to `articles.update`. Autosave also calls it
 * (with `mode: "autosave"`) whenever typing pauses, which on a slow machine can
 * happen mid-test, so tests about manual saves must not assume call order.
 */
export const manualSave = (update) =>
  update.mock.calls.find(([, body]) => body.mode !== "autosave");
