import { vi } from "vitest";
import { ApiError } from "@/services/apiClient";

// Mirrors the Batch 05 permission catalogue (backend/app/auth/permissions.py).
export const COMMERCE_PERMS = [
  "products.view",
  "products.create",
  "products.edit",
  "products.publish",
  "products.archive",
  "products.manage_prices",
  "products.manage_files",
  "products.manage_bundles",
  "orders.view",
  "orders.manage",
  "orders.export",
  "refunds.issue",
  "payments.view_events",
  "payments.configure",
  "customers.view",
  "customers.support",
  "customers.manage",
  "entitlements.view",
  "entitlements.manage",
  "downloads.audit",
  "finance.view",
  "finance.export",
];

export const money = (minor, currency = "USD") => {
  const amount = (minor / 100).toFixed(2);
  const formatted = `${currency} ${Number(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
  })}`;
  return { amount_minor: minor, currency, amount, formatted };
};

const price = (minor, currency = "USD", extra = {}) => ({
  ...money(minor, currency),
  compare_at: null,
  promotional: false,
  promotion_ends_at: null,
  ...extra,
});

/** Public catalogue entries as returned by GET /api/v1/shop/products. */
export const catalogue = [
  {
    id: "a1a1a1a1a1a1a1a1",
    slug: "calm-mornings-workbook",
    type: "workbook",
    type_label: "Workbook",
    title: "Calm Mornings Workbook",
    subtitle: "Ten minutes to start well",
    description: "A gentle printable workbook for calmer mornings.",
    format: "Printable workbook",
    formats: ["PDF"],
    availability: "available",
    purchasable: true,
    is_free: false,
    featured: true,
    cover: null,
    cover_theme: "gold",
    prices: [price(1500, "USD"), price(195000, "KES")],
    categories: [{ slug: "workbooks", name: "Workbooks" }],
    collections: ["fresh-start"],
    highlights: ["Daily prompts", "Printable pages"],
    published_at: "2026-10-20T10:00:00.000Z",
    available_from: null,
  },
  {
    id: "b2b2b2b2b2b2b2b2",
    slug: "the-power-of-starting-again",
    type: "ebook",
    type_label: "eBook",
    title: "The Power of Starting Again",
    subtitle: "A guide to rebuilding with hope",
    description: "A compassionate guide for a new chapter.",
    format: "eBook",
    formats: [],
    availability: "coming-soon",
    purchasable: false,
    is_free: false,
    featured: true,
    cover: null,
    cover_theme: "sage",
    prices: [],
    categories: [{ slug: "ebooks", name: "eBooks" }],
    collections: ["fresh-start"],
    highlights: ["Reflections"],
    published_at: "2026-10-19T10:00:00.000Z",
    available_from: null,
  },
  {
    id: "c3c3c3c3c3c3c3c3",
    slug: "gratitude-worksheet",
    type: "worksheet",
    type_label: "Downloadable worksheet",
    title: "Gratitude Worksheet",
    subtitle: "",
    description: "A free printable worksheet.",
    format: "Printable PDF",
    formats: ["PDF"],
    availability: "free",
    purchasable: true,
    is_free: true,
    featured: false,
    cover: null,
    cover_theme: "olive",
    prices: [],
    categories: [{ slug: "workbooks", name: "Workbooks" }],
    collections: [],
    highlights: [],
    published_at: "2026-10-21T10:00:00.000Z",
    available_from: null,
  },
  {
    id: "d4d4d4d4d4d4d4d4",
    slug: "deep-reset-journal",
    type: "journal",
    type_label: "Digital journal",
    title: "Deep Reset Journal",
    subtitle: "",
    description: "A journal priced in USD only.",
    format: "Printable journal",
    formats: ["PDF"],
    availability: "available",
    purchasable: true,
    is_free: false,
    featured: false,
    cover: null,
    cover_theme: "charcoal",
    prices: [price(900, "USD")],
    categories: [{ slug: "journals", name: "Journals" }],
    collections: [],
    highlights: [],
    published_at: "2026-10-22T10:00:00.000Z",
    available_from: null,
  },
];

export const catalogueMeta = {
  total: catalogue.length,
  display_currencies: ["USD", "KES"],
  categories: [
    { slug: "workbooks", name: "Workbooks" },
    { slug: "ebooks", name: "eBooks" },
    { slug: "journals", name: "Journals" },
  ],
  collections: [{ slug: "fresh-start", name: "The Fresh Start Collection" }],
};

export function productDetail(slug) {
  const base = catalogue.find((p) => p.slug === slug);
  if (!base) return null;
  return {
    ...base,
    body: [{ type: "paragraph", text: `${base.title} body text.` }],
    benefits: ["Feel calmer", "Start with intention"],
    included: [{ title: "Workbook", description: "40 printable pages", format: "PDF" }],
    faq: [{ question: "Is it printable?", answer: "Yes, A4 and US Letter." }],
    audience: "Anyone who wants calmer mornings.",
    language: "en",
    edition: "First edition",
    page_count: base.purchasable && !base.is_free ? 40 : null,
    sample_text: "",
    gallery: [],
    author: null,
    tags: [],
    files: base.formats.length
      ? [{ title: "Workbook", description: "", format: "PDF", size_bytes: 2_400_000 }]
      : [],
    collections: [],
    seo: null,
    updated_at: base.published_at,
    related: catalogue.filter((p) => p.slug !== slug).slice(0, 2),
  };
}

const notFound = (message = "Not found") =>
  Promise.reject(new ApiError({ status: 404, code: "not_found", message }));

/** Content API additions for the storefront. */
export function shopContentApi() {
  return {
    getProducts: vi.fn(async () => ({ data: catalogue, meta: catalogueMeta })),
    getProduct: vi.fn(async (slug) => {
      const data = productDetail(slug);
      return data ? { data } : notFound(`Product '${slug}' was not found.`);
    }),
    getCollections: vi.fn(async () => ({
      data: [{ slug: "fresh-start", name: "The Fresh Start Collection", product_count: 2 }],
    })),
    getCollection: vi.fn(async (slug) =>
      slug === "fresh-start"
        ? {
            data: {
              slug,
              name: "The Fresh Start Collection",
              description: "Three companions for a new chapter.",
              products: catalogue.filter((p) => p.collections.includes(slug)),
            },
          }
        : notFound(),
    ),
  };
}

export const customerProfile = (overrides = {}) => ({
  id: "cust0001",
  email: "reader@example.com",
  display_name: "Reader",
  email_verified: true,
  created_at: "2026-10-20T10:00:00.000Z",
  status: "active",
  deletion_requested_at: null,
  ...overrides,
});

const unauthenticated = () =>
  Promise.reject(
    new ApiError({
      status: 401,
      code: "customer_auth_required",
      message: "Please sign in to your account.",
    }),
  );

export function quoteFor(ids, currency, { open = true, owned = [] } = {}) {
  const lines = ids.map((id) => {
    const p = catalogue.find((c) => c.id === id);
    const line = {
      product_id: id,
      title: p?.title ?? "Unavailable product",
      slug: p?.slug,
      type: p?.type,
      cover_theme: p?.cover_theme ?? "sage",
      unit: null,
      compare_at: null,
      available: false,
      problem: null,
    };
    if (!p) line.problem = "This product is no longer available.";
    else if (p.availability === "coming-soon")
      line.problem = "Coming soon — not available to buy yet.";
    else if (p.is_free) line.problem = "This resource is free — get it from its page instead.";
    else if (owned.includes(id)) line.problem = "Already in your library.";
    else {
      const pr = p.prices.find((x) => x.currency === currency);
      if (!pr) line.problem = `Not sold in ${currency}.`;
      else Object.assign(line, { unit: money(pr.amount_minor, currency), available: true });
    }
    return line;
  });
  const total = lines.reduce((sum, l) => sum + (l.unit?.amount_minor ?? 0), 0);
  return {
    currency,
    lines,
    subtotal: money(total, currency),
    tax: null,
    total: money(total, currency),
    tax_note: "Prices include any applicable taxes; no tax is added at checkout.",
    can_checkout: lines.length > 0 && lines.every((l) => l.available) && open,
    warnings: [],
    checkout: open
      ? {
          open: true,
          mode: "test",
          test_mode: true,
          currencies: ["USD", "KES"],
          channels: ["card", "mobile_money"],
          message: "",
          provider: "Paystack",
        }
      : {
          open: false,
          mode: "disabled",
          test_mode: false,
          currencies: [],
          channels: [],
          message: "Checkout is not open yet. No payments are being taken.",
          provider: null,
        },
  };
}

export function orderFor(status = "awaiting_payment", overrides = {}) {
  return {
    id: "order0000000000000000000000000001",
    number: "TPA-261023-ABCDEF",
    status,
    currency: "USD",
    subtotal: money(1500),
    tax: money(0),
    total: money(1500),
    refunded: money(0),
    test_mode: true,
    created_at: "2026-10-23T10:00:00.000Z",
    paid_at: status === "paid" ? "2026-10-23T10:01:00.000Z" : null,
    expires_at: "2026-10-23T11:00:00.000Z",
    items: [
      {
        product_id: "a1a1a1a1a1a1a1a1",
        title: "Calm Mornings Workbook",
        type: "workbook",
        slug: "calm-mornings-workbook",
        amount: money(1500),
        includes: [],
      },
    ],
    payment: {
      provider: "Paystack",
      status: status === "paid" ? "succeeded" : "initialized",
      reference: "TPA-261023-ABCDEF-1-abc123",
      failure_reason: status === "failed" ? "Declined" : "",
    },
    can_retry: ["awaiting_payment", "failed"].includes(status),
    ...overrides,
  };
}

/** In-memory customer API (cart quotes, checkout, account, library). */
export function createFakeShopApi({ customer = null, open = true, owned = [] } = {}) {
  let current = customer;
  const ok = (data) => Promise.resolve({ data });
  return {
    status: vi.fn(() => ok(quoteFor([], "USD", { open }).checkout)),
    quote: vi.fn((ids, currency) => ok(quoteFor(ids, currency, { open, owned }))),
    me: vi.fn(() => {
      if (current) return ok({ customer: current });
      // Like the API: a stale session cookie is reported once as ended, then cleared.
      if (typeof document !== "undefined" && document.cookie.includes("tpa_customer_csrf=")) {
        document.cookie = "tpa_customer_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
        return Promise.reject(
          new ApiError({
            status: 401,
            code: "session_expired",
            message: "Your session has ended. Please sign in again.",
          }),
        );
      }
      return unauthenticated();
    }),
    login: vi.fn((body) => {
      if (body.password !== "Correct-Horse-Battery-9") {
        return Promise.reject(
          new ApiError({
            status: 401,
            code: "authentication_failed",
            message: "The email or password is incorrect.",
          }),
        );
      }
      current = customerProfile({ email: body.email });
      return ok({ customer: current });
    }),
    register: vi.fn((body) => {
      current = customerProfile({
        email: body.email,
        display_name: body.display_name,
        email_verified: false,
      });
      return ok({ registered: true, signed_in: true, customer: current });
    }),
    logout: vi.fn(() => {
      current = null;
      return ok({ signed_out: true });
    }),
    updateProfile: vi.fn((body) => {
      current = { ...current, ...body };
      return ok({ customer: current });
    }),
    changePassword: vi.fn(() => ok({ changed: true })),
    verifyEmail: vi.fn(() => ok({ verified: true })),
    resendVerification: vi.fn(() => ok({ sent: true, delivery: "memory" })),
    requestVerification: vi.fn(() =>
      ok({
        message:
          "If that address has an account that still needs confirming, we've sent a new link.",
      }),
    ),
    accountNewsletter: vi.fn(() =>
      ok({
        available: true,
        name: "The Positive Reset",
        consent_text: "Yes, send me The Positive Reset newsletter.",
        consent_version: "v1",
        status: "none",
        preferences_token: null,
      }),
    ),
    subscribeFromAccount: vi.fn(() => ok({ status: "check_email" })),
    requestPasswordReset: vi.fn(() =>
      ok({ message: "If an account exists for that email, we've sent a reset link." }),
    ),
    completePasswordReset: vi.fn(() => ok({ reset: true })),
    exportData: vi.fn(() => ok({ profile: current })),
    deleteAccount: vi.fn(() => ok({ deleted: true })),
    orders: vi.fn(() => ok([orderFor("paid")])),
    order: vi.fn(() =>
      ok({
        ...orderFor("paid"),
        receipt: {
          number: "R-261023-ABCDEF",
          paid_at: "2026-10-23T10:01:00.000Z",
          reference: "TPA-261023-ABCDEF-1-abc123",
          items: [{ title: "Calm Mornings Workbook", amount: money(1500) }],
          total: money(1500),
          mode: "test",
        },
      }),
    ),
    library: vi.fn(() =>
      ok([
        {
          id: 7,
          product: {
            id: "a1a1a1a1a1a1a1a1",
            title: "Calm Mornings Workbook",
            slug: "calm-mornings-workbook",
            type: "workbook",
            cover_theme: "gold",
            cover: null,
          },
          source: "purchase",
          status: "active",
          revoked_reason: "",
          granted_at: "2026-10-23T10:01:00.000Z",
          order_number: "TPA-261023-ABCDEF",
          download_count: 0,
          download_limit: null,
          includes: [],
          duplicate: false,
          files: [
            {
              file_id: "f1",
              title: "Workbook",
              description: "",
              versions: [
                {
                  kind: "latest",
                  version_id: 22,
                  version: 2,
                  format: "PDF",
                  size_bytes: 2_400_000,
                  updated_at: "2026-10-23T09:00:00.000Z",
                },
                {
                  kind: "purchased",
                  version_id: 21,
                  version: 1,
                  format: "PDF",
                  size_bytes: 2_300_000,
                  updated_at: "2026-10-20T09:00:00.000Z",
                },
              ],
            },
          ],
        },
      ]),
    ),
    authorizeDownload: vi.fn((_ent, versionId) =>
      ok({ url: `/api/v1/downloads/token-${versionId}`, expires_in: 300 }),
    ),
    claimFree: vi.fn(() => ok({ entitlement_id: 9, created: true })),
    checkout: vi.fn((body) =>
      ok({
        order: orderFor("awaiting_payment"),
        authorization_url: `https://checkout.paystack.com/test-${body.currency.toLowerCase()}`,
      }),
    ),
    checkoutOrder: vi.fn(() => ok(orderFor())),
    verifyOrder: vi.fn(() => ok({ outcome: "paid", order: orderFor("paid") })),
    retryOrder: vi.fn(() =>
      ok({ order: orderFor(), authorization_url: "https://checkout.paystack.com/retry" }),
    ),
    cancelOrder: vi.fn(() => ok(orderFor("cancelled"))),
  };
}

// ---- admin ------------------------------------------------------------------------------

const adminProduct = (overrides = {}) => ({
  id: 1,
  public_id: "a1a1a1a1a1a1a1a1",
  title: "Calm Mornings Workbook",
  slug: "calm-mornings-workbook",
  published_slug: null,
  product_type: "workbook",
  status: "draft",
  sales_status: "coming_soon",
  pricing_model: "paid",
  is_featured: false,
  featured_order: 0,
  cover_media_id: null,
  cover_theme: "gold",
  prices: [],
  issues: ["No deliverable files uploaded.", "No price set."],
  purchasable: false,
  blockers: ["No deliverable files uploaded.", "No price set.", "Not published."],
  file_count: 0,
  has_unpublished_changes: false,
  available_from: null,
  updated_at: "2026-10-23T10:00:00.000Z",
  published_at: null,
  lock_version: 1,
  subtitle: "",
  short_description: "A gentle workbook.",
  description: [],
  benefits: [],
  included: [],
  faq: [],
  audience: "",
  format_label: "Printable workbook",
  language: "en",
  edition: "",
  page_count: null,
  sample_text: "",
  author_id: null,
  gallery: [],
  social_image_id: null,
  seo_title: null,
  meta_description: null,
  noindex: false,
  tax_category: "digital_goods",
  category_ids: [],
  tag_ids: [],
  collection_ids: [],
  available_until: null,
  first_published_at: null,
  archived_at: null,
  price_records: [],
  files: [],
  bundle_items: [],
  public_path: null,
  sales: { orders: [], active_entitlements: 0 },
  can: {
    create: true,
    edit: true,
    publish: true,
    archive: true,
    prices: true,
    files: true,
    bundles: true,
  },
  ...overrides,
});

const adminOrder = (overrides = {}) => ({
  id: 5,
  number: "TPA-261023-ABCDEF",
  status: "paid",
  mode: "test",
  email: "reader@example.com",
  customer_id: 3,
  currency: "USD",
  total: money(1500),
  refunded: money(0),
  item_count: 1,
  needs_review: false,
  created_at: "2026-10-23T10:00:00.000Z",
  paid_at: "2026-10-23T10:01:00.000Z",
  public_id: "order0000000000000000000000000001",
  subtotal: money(1500),
  tax: money(0),
  discount: money(0),
  refundable: money(1500),
  review_reason: "",
  terms_version: "2026-10",
  terms_accepted_at: "2026-10-23T10:00:00.000Z",
  expires_at: null,
  cancelled_at: null,
  failed_at: null,
  notes: "",
  items: [
    {
      id: 1,
      product_id: 1,
      title: "Calm Mornings Workbook",
      type: "workbook",
      amount: money(1500),
      compare_at: null,
      includes: [],
    },
  ],
  customer: { id: 3, email: "reader@example.com", display_name: "Reader", status: "active" },
  attempts: [
    {
      id: 1,
      reference: "TPA-261023-ABCDEF-1-abc123",
      status: "succeeded",
      mode: "test",
      amount: money(1500),
      provider_status: "success",
      failure_reason: "",
      created_at: "2026-10-23T10:00:00.000Z",
      verified_at: "2026-10-23T10:01:00.000Z",
    },
  ],
  transactions: [
    {
      kind: "charge",
      provider_id: "5001",
      reference: "TPA-261023-ABCDEF-1-abc123",
      status: "success",
      mode: "test",
      amount: money(1500),
      channel: "card",
      occurred_at: "2026-10-23T10:01:00.000Z",
    },
  ],
  refunds: [],
  receipt: { number: "R-261023-ABCDEF", issued_at: "2026-10-23T10:01:00.000Z" },
  emails: [
    {
      template: "order_confirmation",
      status: "development_console",
      at: "2026-10-23T10:01:00.000Z",
    },
  ],
  downloads: 2,
  can: { manage: true, refund: true, entitlements: true },
  entitlements: [],
  events: [],
  audit: [],
  ...overrides,
});

export function createCommerceAdminFake(getUser) {
  const ok = (data, meta) => Promise.resolve({ data, meta });
  const perms = () => getUser()?.permissions ?? [];
  const has = (p) => perms().includes(p);
  const forbidden = () =>
    Promise.reject(
      new ApiError({
        status: 403,
        code: "forbidden",
        message: "You do not have permission to perform this action.",
      }),
    );
  let product = adminProduct();
  let order = adminOrder();
  return {
    products: {
      list: vi.fn(() => ok([product], { total: 1 })),
      options: vi.fn(() =>
        ok({
          types: [
            { value: "ebook", label: "eBook", available: true },
            { value: "workbook", label: "Workbook", available: true },
            { value: "bundle", label: "Bundle", available: true },
            { value: "course", label: "Online course", available: false },
          ],
          currencies: [
            { code: "USD", name: "US dollar", exponent: 2 },
            { code: "KES", name: "Kenyan shilling", exponent: 2 },
          ],
          display_currencies: ["USD", "KES"],
          cover_themes: ["sage", "gold"],
          tax_categories: [{ value: "digital_goods", label: "Digital goods (standard)" }],
          tax_note: "Prices are charged exactly as shown.",
          categories: [{ id: 1, name: "Workbooks", slug: "workbooks" }],
          collections: [{ id: 1, name: "Fresh Start", slug: "fresh-start" }],
          authors: [],
          tags: [],
          products: [
            { id: 1, title: "Calm Mornings Workbook", product_type: "workbook", status: "draft" },
          ],
          shop_settings: {},
        }),
      ),
      get: vi.fn(() =>
        ok({
          ...product,
          can: {
            ...product.can,
            prices: has("products.manage_prices"),
            edit: has("products.edit"),
            publish: has("products.publish"),
            files: has("products.manage_files"),
          },
        }),
      ),
      create: vi.fn((body) => {
        product = adminProduct({ id: 2, title: body.title, product_type: body.product_type });
        return ok(product);
      }),
      update: vi.fn((_id, body) => {
        product = { ...product, ...body, lock_version: product.lock_version + 1 };
        return ok(product);
      }),
      action: vi.fn((_id, action) => {
        if (action === "publish") {
          return Promise.reject(
            new ApiError({
              status: 400,
              code: "validation_error",
              message: "This product is not ready to publish.",
              details: { publish: ["No deliverable files uploaded."] },
            }),
          );
        }
        return ok(product);
      }),
      preview: vi.fn(() => ok(productDetail("calm-mornings-workbook"))),
      revisions: vi.fn(() =>
        ok([
          {
            id: 1,
            number: 1,
            kind: "draft",
            summary: "Created",
            created_at: "2026-10-23T10:00:00.000Z",
            created_by: "Site Owner",
          },
        ]),
      ),
      restoreRevision: vi.fn(() => ok(product)),
      setPrice: vi.fn((_id, body) => {
        if (!has("products.manage_prices")) return forbidden();
        const record = {
          id: 9,
          currency: body.currency,
          kind: body.kind,
          amount_minor: body.amount_minor,
          formatted: money(body.amount_minor, body.currency).formatted,
          compare_at_minor: body.compare_at_minor ?? null,
          starts_at: null,
          ends_at: null,
          is_active: true,
        };
        product = {
          ...product,
          price_records: [...product.price_records, record],
          prices: [money(body.amount_minor, body.currency)],
        };
        return ok(product);
      }),
      removePrice: vi.fn(() => ok(product)),
      setBundleItems: vi.fn(() => ok(product)),
      files: vi.fn(() => ok({ files: product.files, scanner_configured: false, max_mb: 300 })),
      uploadFile: vi.fn(() =>
        Promise.reject(
          new ApiError({
            status: 400,
            code: "validation_error",
            message: "The file was not accepted.",
            details: { file: ["PDFs with active content (JavaScript) are not accepted."] },
          }),
        ),
      ),
      uploadVersion: vi.fn(() => ok({})),
      updateFile: vi.fn(() => ok({})),
      fileDownloadUrl: (id, fileId, versionId) =>
        `/api/v1/admin/products/${id}/files/${fileId}/versions/${versionId}/download`,
    },
    productCategories: {
      list: vi.fn(() => ok([])),
      create: vi.fn(() => ok({})),
      update: vi.fn(() => ok({})),
      remove: vi.fn(() => ok({})),
    },
    productCollections: {
      list: vi.fn(() => ok([])),
      create: vi.fn(() => ok({})),
      update: vi.fn(() => ok({})),
      remove: vi.fn(() => ok({})),
    },
    orders: {
      list: vi.fn(() => ok([order], { total: 1 })),
      get: vi.fn(() =>
        ok({
          ...order,
          can: {
            manage: has("orders.manage"),
            refund: has("refunds.issue"),
            entitlements: has("entitlements.manage"),
          },
        }),
      ),
      verify: vi.fn(() => ok({ outcome: "already_paid", order })),
      cancel: vi.fn(() => ok(order)),
      resendReceipt: vi.fn(() => ok({ delivery: "not_configured" })),
      addNote: vi.fn(() => ok(order)),
      refund: vi.fn((_id, body) => {
        const refund = {
          id: 1,
          amount: money(body.amount_minor),
          status: "manual_review",
          method: "manual",
          provider_refund_id: null,
          reason: body.reason,
          revoke_access: body.revoke_access,
          failure_reason: "",
          downloads_at_request: 2,
          requested_by: "Site Owner",
          created_at: "2026-10-23T11:00:00.000Z",
          processed_at: null,
        };
        order = { ...order, refunds: [refund], refundable: money(1500 - body.amount_minor) };
        return ok({ refund, order });
      }),
      refundAction: vi.fn((_id, _refundId, action) => {
        const refund = {
          ...order.refunds[0],
          status: action === "complete" ? "processed" : "rejected",
          provider_refund_id: "RF_1",
        };
        order = {
          ...order,
          status: action === "complete" ? "refunded" : order.status,
          refunds: [refund],
          refunded: action === "complete" ? refund.amount : order.refunded,
        };
        return ok({ refund, order });
      }),
      exportUrl: () => "/api/v1/admin/orders/export",
    },
    customers: {
      list: vi.fn(() =>
        ok(
          [
            {
              id: 3,
              email: "reader@example.com",
              display_name: "Reader",
              status: "active",
              email_verified: true,
              is_test_account: false,
              paid_orders: 1,
              created_at: "2026-10-20T10:00:00.000Z",
              last_login_at: null,
            },
          ],
          { total: 1 },
        ),
      ),
      get: vi.fn(() =>
        ok({
          id: 3,
          email: "reader@example.com",
          display_name: "Reader",
          status: "active",
          email_verified: true,
          is_test_account: false,
          paid_orders: 1,
          created_at: "2026-10-20T10:00:00.000Z",
          last_login_at: null,
          support_notes: "",
          deletion_requested_at: null,
          orders: [],
          emails: [],
          entitlements: [],
          downloads: [],
          can: {
            support: has("customers.support"),
            manage: has("customers.manage"),
            entitlements: has("entitlements.manage"),
          },
        }),
      ),
      update: vi.fn(() => ok({})),
      support: vi.fn(() => ok({ delivery: "development_console" })),
      anonymise: vi.fn(() => ok({})),
      grant: vi.fn(() => ok({})),
    },
    entitlements: { list: vi.fn(() => ok([], { total: 0 })), action: vi.fn(() => ok({})) },
    downloads: { list: vi.fn(() => ok([], { total: 0 })) },
    reports: {
      revenue: vi.fn((params = {}) =>
        ok({
          mode: params.mode ?? "live",
          date_from: null,
          date_to: null,
          currencies:
            params.mode === "test"
              ? [
                  {
                    currency: "KES",
                    orders: 1,
                    paid_orders: 1,
                    failed_orders: 0,
                    gross: money(195000, "KES"),
                    refunds: money(0, "KES"),
                    net: money(195000, "KES"),
                  },
                  {
                    currency: "USD",
                    orders: 2,
                    paid_orders: 1,
                    failed_orders: 1,
                    gross: money(1500),
                    refunds: money(500),
                    net: money(1000),
                  },
                ]
              : [],
          failed_payment_attempts: 1,
          by_product: [],
          downloads: [],
          total_downloads: 0,
          free_claims: 0,
          notes: [
            "Each currency is reported separately; amounts in different currencies are never added together because no conversion policy is configured.",
          ],
        }),
      ),
      revenueExportUrl: () => "/api/v1/admin/reports/revenue/export",
    },
    payments: {
      settings: vi.fn(() =>
        has("payments.configure")
          ? ok({
              settings: {
                provider: "paystack",
                checkout_mode: "disabled",
                currencies: [],
                channels: ["card"],
                order_expiry_minutes: 60,
                refunds_via_provider: false,
                terms_version: "",
                download_limit: null,
                live_attestation: null,
              },
              provider: {
                name: "paystack",
                label: "Paystack",
                secret_key_configured: true,
                public_key_configured: false,
                key_mode: "test",
                public_key_mode: null,
                api_base_is_official: true,
                live_allowed_by_deployment: false,
                supported_currencies: ["KES", "USD", "NGN"],
                supported_channels: ["card", "mobile_money"],
                webhook_url: "https://example.com/api/v1/payments/paystack/webhook",
                callback_url: "https://example.com/checkout/complete",
              },
              effective_mode: "disabled",
              readiness: {
                checks: [
                  {
                    key: "secret_key",
                    label: "Paystack secret key is configured on the server",
                    ok: true,
                    detail: "",
                    required_for: "test",
                  },
                  {
                    key: "live_key",
                    label: "A live secret key (sk_live_) is configured",
                    ok: false,
                    detail: "",
                    required_for: "live",
                  },
                ],
                test_ready: false,
                live_ready: false,
                attestation: {},
              },
              attestations: { merchant_verified: "The Paystack business is fully activated." },
              checkout_currencies: [],
            })
          : forbidden(),
      ),
      update: vi.fn(() => ok({ changed: ["payments.checkout_mode"] })),
      attest: vi.fn(() => ok({})),
      events: vi.fn(() => ok([])),
      reprocess: vi.fn(() => ok({})),
    },
  };
}
