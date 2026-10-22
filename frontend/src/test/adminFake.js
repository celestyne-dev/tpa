import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

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
  "pages.view",
  "pages.edit",
  "navigation.manage",
  "settings.manage",
  "seo.manage",
  "users.view",
  "users.manage",
  "roles.manage",
  "roles.assign",
  "audit.view",
];

export const ROLE_PERMS = {
  super_admin: ALL,
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
    "pages.view",
    "pages.edit",
  ],
  moderator: [
    "dashboard.view",
    "articles.view",
    "articles.unpublish",
    "articles.archive",
    "media.view",
    "pages.view",
  ],
  analyst: ["dashboard.view", "analytics.view", "articles.view", "media.view"],
  content_writer: [
    "dashboard.view",
    "articles.create",
    "articles.edit_own",
    "articles.submit_review",
    "media.view",
  ],
  administrator: ALL.filter((p) => !["roles.manage", "roles.assign"].includes(p)),
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
            key: "footer.text",
            label: "Footer introduction",
            type: "text",
            max_length: 400,
            help: "",
            value: "Encouragement.",
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
        current = { ...current, ...body, updated_at: new Date().toISOString() };
        return ok(withCan(current));
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
      list: vi.fn(() =>
        ok([
          {
            id: 3,
            filename: "calm.svg",
            url: "/images/articles/calm.svg",
            alt_text: "Calm",
            mime_type: "image/svg+xml",
          },
        ]),
      ),
    },
    publishing: { status: vi.fn() },
    pages: {
      list: vi.fn(() => ok([])),
      get: vi.fn(),
      update: vi.fn(),
      sectionTypes: vi.fn(() => ok([])),
      updateSection: vi.fn(),
      reorder: vi.fn(),
    },
    navigation: { list: vi.fn(() => ok([])), save: vi.fn() },
    settings: {
      get: vi.fn(() => ok(settings)),
      save: vi.fn((values) => {
        settings.groups.forEach((g) =>
          g.settings.forEach((s) => s.key in values && (s.value = values[s.key])),
        );
        return ok(settings);
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
  };
}
