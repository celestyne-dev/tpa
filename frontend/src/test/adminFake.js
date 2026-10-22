import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

const ALL = [
  "dashboard.view",
  "analytics.view",
  "content.read",
  "content.write",
  "content.publish",
  "content.moderate",
  "taxonomy.manage",
  "pages.read",
  "pages.write",
  "navigation.manage",
  "settings.manage",
  "users.manage",
  "roles.assign",
  "audit.read",
];

export const ROLE_PERMS = {
  super_admin: ALL,
  editor: [
    "dashboard.view",
    "content.read",
    "content.write",
    "content.publish",
    "content.moderate",
    "taxonomy.manage",
    "pages.read",
    "pages.write",
  ],
  moderator: ["dashboard.view", "content.read", "content.moderate", "pages.read"],
  analyst: ["dashboard.view", "analytics.view", "content.read"],
  // A future specialised role without dashboard access, used to test landing routes.
  pages_only: ["pages.read"],
};

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
    ...overrides,
  };
}

/** In-memory admin API double. `role` null means "not signed in". */
const VALID_TOKEN = "valid-link-token-0123456789abcdef";
export { VALID_TOKEN };

export function createFakeAdminApi({ role = "super_admin", article = makeArticle() } = {}) {
  let user = role ? adminUser(role) : null;
  let current = article;
  const ok = (data, meta) => Promise.resolve({ data, meta });
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
        articles: { total: 6, draft: 1, scheduled: 0, published: 5, archived: 0 },
        topics_total: 8,
        authors_total: 1,
        tags_total: 18,
        recent_articles: [makeArticle()],
        recent_audit: user?.permissions.includes("audit.read")
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
      get: vi.fn(() => ok(current)),
      create: vi.fn((body) => {
        current = makeArticle({ ...body, id: 9 });
        return ok(current);
      }),
      update: vi.fn((id, body) => {
        current = { ...current, ...body, updated_at: new Date().toISOString() };
        return ok(current);
      }),
      publish: vi.fn(() => {
        current = {
          ...current,
          status: "published",
          is_public: true,
          published_at: "2026-10-21T09:00:00.000Z",
          slug_locked: true,
          updated_at: new Date().toISOString(),
        };
        return ok(current);
      }),
      unpublish: vi.fn(() => {
        current = { ...current, status: "draft", updated_at: new Date().toISOString() };
        return ok(current);
      }),
      archive: vi.fn(() => ok(current)),
      restore: vi.fn(() => ok(current)),
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
      roles: vi.fn(() =>
        ok([
          {
            name: "super_admin",
            label: "Super admin",
            description: "Full access.",
            permissions: ALL,
          },
          {
            name: "editor",
            label: "Editor",
            description: "Edits content.",
            permissions: ROLE_PERMS.editor,
          },
          {
            name: "moderator",
            label: "Moderator",
            description: "Moderates.",
            permissions: ROLE_PERMS.moderator,
          },
          {
            name: "analyst",
            label: "Analyst",
            description: "Reads.",
            permissions: ROLE_PERMS.analyst,
          },
        ]),
      ),
      permissions: vi.fn(() => ok([])),
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
