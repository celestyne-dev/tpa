import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";
import sectionTypes from "./sectionTypes.json";

/** Stateful fake of the page-builder endpoints (mirrors backend page_admin behaviour). */
export function createBuilderFake(getUser) {
  const perms = { has: (p) => (getUser()?.permissions ?? []).includes(p) };
  const ok = (data, meta) => Promise.resolve({ data, meta });
  const fail = (status, code, message, details) =>
    Promise.reject(new ApiError({ status, code, message, details }));
  let nextId = 100;

  const hero = {
    id: 1,
    key: "hero",
    name: "Hero",
    section_type: "hero",
    type_label: "Hero banner",
    variant: "split",
    content: {
      eyebrow: "Think Positive Always",
      heading: "A Better Mindset.",
      highlight: "A Brighter Life.",
      body: "Practical encouragement.",
      media: null,
      primary_cta: {
        label: "Explore Our Resources",
        url: "/free-resources",
        style: "",
        cta_id: null,
      },
      secondary_cta: { label: "", url: "", style: "", cta_id: null },
    },
    design: { background: "ivory", spacing: "lg", align: "left" },
    visibility: { devices: "all", starts_at: null, ends_at: null },
    is_visible: true,
    reusable_section_id: null,
  };
  const quote = {
    ...hero,
    id: 2,
    key: "quote",
    name: "Quote",
    section_type: "quote",
    type_label: "Motivational quote",
    variant: "minimal",
    content: { quote: "Small steps count.", attribution: "", attribution_role: "" },
    design: { background: "ivory", spacing: "md", align: "center" },
  };

  const pages = {
    1: {
      id: 1,
      slug: "home",
      title: "Homepage",
      path: "/",
      live_path: "/",
      status: "published",
      template: "home",
      template_label: "Homepage",
      is_system: true,
      is_home: true,
      parent_id: null,
      noindex: false,
      seo_title: null,
      meta_description: null,
      canonical_url: null,
      social_title: null,
      social_description: null,
      social_image_id: null,
      has_unpublished_changes: false,
      published_at: "2026-10-20T10:00:00.000Z",
      scheduled_at: null,
      draft_updated_at: null,
      updated_at: "2026-10-20T10:00:00.000Z",
      updated_by: null,
      lock_version: 3,
      warnings: [],
      sections: [hero, quote],
    },
    7: {
      id: 7,
      slug: "spring-reset",
      title: "Spring Reset",
      path: "/spring-reset",
      live_path: null,
      status: "draft",
      template: "landing",
      template_label: "Landing page",
      is_system: false,
      is_home: false,
      parent_id: null,
      noindex: false,
      seo_title: null,
      meta_description: null,
      canonical_url: null,
      social_title: null,
      social_description: null,
      social_image_id: null,
      has_unpublished_changes: true,
      published_at: null,
      scheduled_at: null,
      draft_updated_at: "2026-10-21T10:00:00.000Z",
      updated_at: "2026-10-21T10:00:00.000Z",
      updated_by: { id: 1, name: "Site Owner" },
      lock_version: 1,
      warnings: [],
      sections: [{ ...hero, id: 70, key: "hero-1", variant: "centered" }],
    },
  };
  const revisions = {
    1: [
      {
        id: 11,
        number: 2,
        kind: "published",
        kind_label: "Published",
        summary: null,
        title: "Homepage",
        section_count: 2,
        created_at: "2026-10-20T10:00:00.000Z",
        created_by: { id: 1, name: "Site Owner" },
      },
      {
        id: 10,
        number: 1,
        kind: "published",
        kind_label: "Published",
        summary: "Default homepage",
        title: "Homepage",
        section_count: 9,
        created_at: "2026-10-01T10:00:00.000Z",
        created_by: null,
      },
    ],
  };

  const capabilities = (page) => {
    const home = page.is_home;
    const view = perms.has(home ? "homepage.view" : "pages.view");
    const edit = perms.has(home ? "homepage.edit" : "pages.edit") && page.status !== "archived";
    const publish =
      perms.has(home ? "homepage.publish" : "pages.publish") && page.status !== "archived";
    return {
      view,
      edit,
      publish,
      unpublish: !home && perms.has("pages.publish") && page.status === "published",
      archive: !home && perms.has("pages.publish") && page.status !== "archived",
      restore: perms.has("pages.publish") && page.status === "archived",
      duplicate: !home && perms.has("pages.create"),
      change_slug: !home && edit,
      restore_revisions: edit,
      manage_shared: perms.has("reusable_sections.manage"),
    };
  };
  const detail = (page) => ({
    ...structuredClone(page),
    capabilities: capabilities(page),
    revision_count: (revisions[page.id] ?? []).length,
  });
  const summary = ({ sections, ...page }) => ({ ...page, section_count: sections.length });
  const get = (id) => pages[Number(id)];

  const api = {
    pages: {
      list: vi.fn((params = {}) =>
        ok(
          Object.values(pages)
            .filter((p) => (params.status ? p.status === params.status : p.status !== "archived"))
            .filter((p) => perms.has("homepage.view") || !p.is_home)
            .map(summary),
        ),
      ),
      homepage: vi.fn(() => ok(detail(pages[1]))),
      get: vi.fn((id) =>
        get(id) ? ok(detail(get(id))) : fail(404, "not_found", "Page not found."),
      ),
      create: vi.fn((body) => {
        if (!body.title)
          return fail(400, "validation_error", "Invalid", { title: ["A title is required."] });
        const id = (nextId += 1);
        pages[id] = {
          ...structuredClone(pages[7]),
          id,
          title: body.title,
          slug: body.slug,
          path: `/${body.slug}`,
          template: body.template,
          lock_version: 1,
        };
        return ok(detail(pages[id]));
      }),
      saveDraft: vi.fn((id, body) => {
        const page = get(id);
        if (body.lock_version !== page.lock_version) {
          return fail(
            409,
            "edit_conflict",
            "This page was changed by someone else since you opened it.",
            {
              lock_version: page.lock_version,
              updated_by: "Ngozi",
            },
          );
        }
        const bad = (body.sections ?? []).findIndex(
          (s) => s.section_type === "hero" && !s.reusable_section_id && !s.content?.heading,
        );
        if (bad >= 0) {
          return fail(
            400,
            "validation_error",
            "Some fields need attention before the draft can be saved.",
            {
              [`sections.${bad}.content.heading`]: ["This field is required."],
            },
          );
        }
        Object.assign(page, body.page ?? {});
        if (body.sections) {
          page.sections = body.sections.map((s, i) => ({
            ...structuredClone(s),
            id: s.id ?? (nextId += 1),
            key: s.key ?? `${s.section_type}-${i}`,
            type_label: sectionTypes.find((t) => t.type === s.section_type)?.label,
          }));
        }
        page.lock_version += 1;
        page.has_unpublished_changes = true;
        return ok(detail(page));
      }),
      publish: vi.fn((id, lockVersion) => {
        const page = get(id);
        if (lockVersion !== page.lock_version) return fail(409, "edit_conflict", "Changed", {});
        Object.assign(page, {
          status: "published",
          has_unpublished_changes: false,
          live_path: page.path,
        });
        page.lock_version += 1;
        return ok(detail(page));
      }),
      schedule: vi.fn((id, at) => {
        const page = get(id);
        page.scheduled_at = at;
        page.lock_version += 1;
        return ok(detail(page));
      }),
      unschedule: vi.fn((id) => ok(detail(Object.assign(get(id), { scheduled_at: null })))),
      unpublish: vi.fn((id) =>
        ok(detail(Object.assign(get(id), { status: "draft", live_path: null }))),
      ),
      archive: vi.fn((id) => ok(detail(Object.assign(get(id), { status: "archived" })))),
      restore: vi.fn((id) => ok(detail(Object.assign(get(id), { status: "draft" })))),
      discard: vi.fn((id) =>
        ok(detail(Object.assign(get(id), { has_unpublished_changes: false }))),
      ),
      duplicate: vi.fn((id) => {
        const copy = {
          ...structuredClone(get(id)),
          id: (nextId += 1),
          title: `Copy of ${get(id).title}`,
          status: "draft",
        };
        pages[copy.id] = copy;
        return ok(detail(copy));
      }),
      preview: vi.fn((id, body) => {
        const page = get(id);
        const sections = (body?.sections ?? page.sections).map((s, i) => ({
          key: s.key ?? `preview-${i}`,
          type: s.section_type,
          variant: s.variant,
          design: s.design ?? {},
          devices: s.visibility?.devices ?? "all",
          data: { ...s.content, primary_cta: null, secondary_cta: null, media: null },
        }));
        return ok({
          page: { path: page.path, title: page.title, seo: {}, breadcrumbs: [], sections },
          errors: {},
        });
      }),
      seoChecks: vi.fn(() =>
        ok({
          checks: [
            {
              code: "missing_meta_description",
              severity: "warning",
              message: "Add a meta description so search results show a helpful summary.",
              field: "meta_description",
            },
          ],
        }),
      ),
      revisions: vi.fn((id) => ok(revisions[Number(id)] ?? [])),
      revision: vi.fn((id, rid) =>
        ok({
          ...(revisions[Number(id)] ?? []).find((r) => r.id === rid),
          sections: [
            {
              key: "hero",
              name: "Hero",
              type_label: "Hero banner",
              is_visible: true,
              heading: "A Better Mindset.",
            },
          ],
        }),
      ),
      restoreRevision: vi.fn((id) => {
        const page = get(id);
        page.lock_version += 1;
        page.has_unpublished_changes = true;
        page.sections = [hero];
        return ok(detail(page));
      }),
      slugCheck: vi.fn((params) =>
        ok(
          ["admin", "articles"].includes(params.slug)
            ? {
                slug: params.slug,
                path: null,
                available: false,
                errors: {
                  slug: [
                    `“/${params.slug}” is reserved by the website and cannot be used for a page.`,
                  ],
                },
              }
            : {
                slug: params.slug,
                path: `/${params.slug}`,
                available: true,
                errors: {},
                overrides_builtin: params.slug === "about",
              },
        ),
      ),
      templates: vi.fn(() =>
        ok([
          {
            key: "standard",
            label: "Standard content page",
            description: "A page header and free-form content.",
            sections: ["Page header", "Custom content"],
          },
          {
            key: "landing",
            label: "Landing page",
            description: "A hero, highlights and a call to action.",
            sections: ["Hero banner", "Feature list", "Call to action"],
          },
          {
            key: "coming_soon",
            label: "Coming-soon product page",
            description: "No purchase button.",
            sections: ["Hero banner", "Digital product showcase"],
          },
        ]),
      ),
      sectionTypes: vi.fn(() => ok(sectionTypes)),
      shareSection: vi.fn((id, sectionId, name) => {
        const shared = {
          id: (nextId += 1),
          name,
          section_type: "quote",
          type_label: "Motivational quote",
          variant: "minimal",
          content: quote.content,
          design: quote.design,
          usage: [],
          live_pages: 0,
          lock_version: 1,
        };
        sharedList.push(shared);
        const section = get(id).sections.find((s) => s.id === sectionId);
        Object.assign(section, { reusable_section_id: shared.id, reusable_name: name });
        return ok(shared);
      }),
      update: vi.fn(),
      updateSection: vi.fn(),
      reorder: vi.fn(),
    },
  };

  const sharedList = [
    {
      id: 5,
      name: "Join the newsletter",
      description: null,
      section_type: "call_to_action",
      type_label: "Call to action",
      variant: "banner",
      content: {
        heading: "Join The Positive Reset",
        body: "",
        primary_cta: { label: "Subscribe", url: "/newsletter", style: "", cta_id: null },
        secondary_cta: { label: "", url: "", style: "", cta_id: null },
      },
      design: { background: "sage_dark", spacing: "md", width: "default" },
      lock_version: 2,
      usage: [{ type: "page", id: 1, title: "Homepage", path: "/", live: true }],
      live_pages: 1,
    },
  ];
  const ctas = [
    {
      id: 3,
      name: "Subscribe",
      label: "Join The Positive Reset",
      url: "/newsletter",
      style: "primary",
      description: null,
      usage: [],
    },
  ];
  const announcements = [
    {
      id: 1,
      name: "Journal launch",
      message: "A new guided journal is coming soon.",
      cta_label: "Join",
      cta_url: "/newsletter",
      variant: "sage",
      target: "all",
      target_paths: [],
      starts_at: null,
      ends_at: null,
      is_enabled: true,
      is_dismissible: true,
      display_order: 0,
      state: "active",
    },
    {
      id: 2,
      name: "Spring series",
      message: "Spring reset series starts soon.",
      cta_label: null,
      cta_url: null,
      variant: "gold",
      target: "home",
      target_paths: [],
      starts_at: "2027-03-01T09:00:00.000Z",
      ends_at: null,
      is_enabled: true,
      is_dismissible: true,
      display_order: 1,
      state: "scheduled",
    },
  ];

  api.shared = {
    list: vi.fn(() => ok(structuredClone(sharedList))),
    get: vi.fn((id) => ok(sharedList.find((s) => s.id === id))),
    create: vi.fn((body) => {
      const created = {
        ...body,
        id: (nextId += 1),
        type_label: body.section_type,
        usage: [],
        live_pages: 0,
        lock_version: 1,
      };
      sharedList.push(created);
      return ok(created);
    }),
    update: vi.fn((id, body) => {
      const shared = sharedList.find((s) => s.id === id);
      Object.assign(shared, body, { lock_version: shared.lock_version + 1 });
      return ok({
        ...shared,
        propagated: body.propagate !== false,
        detached: body.propagate === false ? 1 : 0,
      });
    }),
    remove: vi.fn(() => ok({ deleted: true })),
  };
  api.ctas = {
    list: vi.fn(() => ok(structuredClone(ctas))),
    create: vi.fn((body) => {
      if (!body.url?.startsWith("/") && !body.url?.startsWith("https://")) {
        return fail(400, "validation_error", "The call to action is invalid.", {
          url: ["Use a site path starting with / or a full https:// link."],
        });
      }
      const created = { ...body, id: (nextId += 1), usage: [] };
      ctas.push(created);
      return ok(created);
    }),
    update: vi.fn((id, body) =>
      ok(
        Object.assign(
          ctas.find((c) => c.id === id),
          body,
        ),
      ),
    ),
    remove: vi.fn(() => ok({ deleted: true })),
  };
  api.announcements = {
    list: vi.fn(() => ok(structuredClone(announcements))),
    create: vi.fn((body) => {
      if (!body.message)
        return fail(400, "validation_error", "Invalid", { message: ["This field is required."] });
      const created = {
        ...body,
        id: (nextId += 1),
        display_order: announcements.length,
        state: body.is_enabled ? "active" : "disabled",
      };
      announcements.push(created);
      return ok(created);
    }),
    update: vi.fn((id, body) =>
      ok(
        Object.assign(
          announcements.find((a) => a.id === id),
          body,
        ),
      ),
    ),
    remove: vi.fn(() => ok({ deleted: true })),
    reorder: vi.fn((order) => {
      announcements.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
      return ok(structuredClone(announcements));
    }),
  };
  api.linkOptions = vi.fn(() =>
    ok([
      { label: "About", url: "/about", group: "Website pages" },
      {
        label: "Spring Reset",
        url: "/spring-reset",
        group: "CMS pages",
        note: "Not published yet",
      },
    ]),
  );
  api.builderOptions = vi.fn(() =>
    ok({
      articles: [
        { id: 21, title: "How to Reframe a Negative Thought", slug: "reframing-negative-thoughts" },
        { id: 22, title: "Why a Weekly Reflection Helps", slug: "weekly-reflection" },
      ],
      topics: [{ id: 31, name: "Positive Mindset", slug: "positive-mindset", featured: true }],
      authors: [{ id: 41, name: "Think Positive Always" }],
    }),
  );
  return api;
}
