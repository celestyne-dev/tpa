# Website management guide (Batches 04–05)

This guide is for the people who run the website day to day. Everything described here happens in the admin dashboard at `/admin`. You never need to edit code to change the homepage, add a page, update the menus or run an announcement.

**How changes reach the website.** The public site is static HTML, rebuilt by the publishing worker. When you publish something, a rebuild is queued, and the change is live once the rebuild finishes. This usually takes a minute or two, and you can follow it at **Publishing**. A draft is never visible to the public, whatever you do in the editor.

## 1. The homepage (`/admin/homepage`)

The homepage is a list of **sections**. The left column (the outline) shows them in order. The right column shows a live preview.

- **Add a section:** press **Add section** and pick a type. The dialog explains what each type is for. Hero banner and Page header can each be used once per page.
- **Reorder:** drag a section by its handle. With the keyboard, use each section's **Move up** and **Move down** buttons, or press Alt+Up or Alt+Down on a focused section. Moves are announced to screen readers.
- **Hide without deleting:** switch a section off. It stays in the draft, but readers don't see it.
- **Duplicate or delete:** use the section's menu. Deleting asks for confirmation, and nothing is final until you publish.
- **Edit:** select a section to open its fields. Each type shows only the fields it uses, and some fields appear only for a particular layout. Errors appear next to the field and on the section in the outline.
- **Style:** under **Appearance**, choose the background, spacing, width, alignment, card style, image shape, button style and heading size. These are fixed presets from the brand design, so the site always stays on-brand. There is no free-form CSS.
- **Show between dates (optional):** a section can be given a start and/or end time, which is useful for campaigns. The scheduler queues a rebuild when a window opens or closes.
- **Images and links:** **Choose image** opens the media library. Link fields suggest the site's pages, articles and topics as you type, or accept any site path or https address. Broken internal links are flagged.

### Saving and publishing

| Button               | What it does                                                                                                                                              |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Save draft**       | Stores your work. The website does not change.                                                                                                            |
| **Preview**          | Opens a private, full-page preview of the draft (not indexed by search engines, visible only to signed-in staff).                                         |
| **Desktop / Mobile** | Switches the live preview width.                                                                                                                          |
| **Publish**          | Makes the draft the live version and queues a rebuild. You need the publish permission. Without it, you can only save drafts for someone else to publish. |
| **Discard changes**  | Throws away the draft and goes back to what is live.                                                                                                      |
| **History**          | Lists every published version, scheduled publication and draft backup. **Restore** loads a version into the draft. It goes live only when you publish it. |

If you try to leave with unsaved changes, the editor warns you. If somebody else saved the same page while you were editing, you will see an **edit conflict** message. You can then load their version or keep yours. Work is never silently overwritten.

**Collections update themselves.** _Featured articles_, _Latest articles_, _Selected article collection_ and _Topic cards_ draw from published content. An unpublished article never appears, even if you picked it. _Digital product showcase_ draws from the shop catalogue (featured, newest, hand-picked in your order, one collection, or bundles). Prices and buttons appear only for products that can really be bought. Anything else shows as an honest "Coming soon" preview, and drafts never appear.

## 2. Section types

| Type                        | Use it for                                                                                      |
| --------------------------- | ----------------------------------------------------------------------------------------------- |
| Hero banner                 | The opening headline with up to two buttons and artwork or an image (once per page)             |
| Page header                 | The title area of an inner page, with breadcrumbs for sub-pages (once per page)                 |
| Brand mission               | Who TPA is and why it exists                                                                    |
| Featured articles           | Articles marked as featured, or a hand-picked selection                                         |
| Latest articles             | The newest published articles, optionally from one topic                                        |
| Selected article collection | A hand-picked reading list in your order                                                        |
| Topic cards                 | Featured topics, all topics or a selection                                                      |
| Motivational quote          | A short quote with optional attribution                                                         |
| Inspirational message       | A short encouraging message with an optional button                                             |
| Image and text feature      | An image beside a heading, text and buttons                                                     |
| Newsletter signup           | The Positive Reset panel: an honest “opening soon” notice; it collects no email addresses yet   |
| Digital product showcase    | Real products from the shop: choose the mode, products or collection, count, prices and CTA     |
| Promotional banner          | A bold banner for a campaign, series or release                                                 |
| Call to action              | A focused invitation with one or two buttons                                                    |
| Testimonials                | Genuine words from readers or partners, shared with permission (no invented reviews or ratings) |
| Statistics                  | A row of key figures (use only figures you can stand behind)                                    |
| FAQ                         | Questions and answers in an accessible expandable list                                          |
| Custom content              | Free-form text, headings, lists, images and quotes                                              |
| Feature list                | Short benefits or principles, each with an icon                                                 |
| Partnership invitation      | An invitation for brands, with a list of opportunities                                          |
| Author introduction         | An author's portrait, name and bio from their profile                                           |
| Resource recommendations    | Recommended resources, guides or pages, each with a link                                        |
| Contact details             | Contact email addresses from Settings; there is deliberately no form                            |
| Shared section group        | Several shared sections shown together (shared sections only)                                   |
| Sponsor logo strip          | Logos from approved bookings currently running on a placement, labelled “Sponsored”             |
| Sponsored banner            | The live approved booking on a placement; hidden when none is live; links are `rel="sponsored"` |
| Brand spotlight             | Features the brand from the live booking on a placement, with its sponsor disclosure            |
| Affiliate recommendations   | Chosen affiliate links with the affiliate disclosure always shown beside them                   |
| Media kit block             | A summary with verified, dated audience measurements and a link to `/advertise`                 |
| Partnership inquiry form    | The partnership inquiry form (privacy notice, spam protection, rate limits)                     |

## 3. Pages (`/admin/pages`)

- **New page:** choose a **template** (Standard, Landing, Newsletter, Lead magnet, Campaign, Partnership or Coming soon). The template provides starter sections, which you then edit like the homepage.
- **Address:** a page has a **slug** and an optional **parent** (for example `/guides/spring-reset`, at most 3 levels). The availability check explains when an address can't be used.
  - **Reserved addresses** such as `/admin`, `/api`, `/articles`, `/topics`, `/shop`, `/media` and `/auth` belong to the site's own features and can never be used for pages.
  - **Replaceable built-in pages:** About, Contact, Newsletter, Partner with us, Free resources, Privacy policy, Terms and Affiliate disclosure. If you publish a page at one of these addresses, your page replaces the built-in one. If you unpublish it, the built-in page comes back.
- **Changing the address of a published page** automatically creates a permanent (301) redirect from the old address once you publish.
- **SEO tab:** search title, description, social image, canonical address and "hide from search engines". Pages marked as hidden, drafts and archived pages are left out of the sitemap.
- **Schedule:** choose a date and time to publish the current draft. The worker publishes it on time and queues a rebuild.
- **Duplicate** copies a page as a new draft. **Archive** takes it offline, so its address shows the real "Page not found" page. Archived pages can be restored.
- **Revisions** work the same as on the homepage.

## 4. Shared sections and global CTAs (`/admin/shared-sections`)

A **shared section** is written once and used on many pages. Insert one from **Add section → Shared**.

- When you save a change to a section that is live on pages, you choose **Update all live pages** or **Keep those pages unchanged**. With the second option, those pages get their own copy of the previous content.
- The usage list shows every page that uses a section. A shared section that is in use can't be deleted.
- **Section groups** can contain other shared sections, up to 3 levels deep. A group can never contain itself, either directly or indirectly.
- **Global CTAs** are saved buttons (label, link and style). Any section button can use one instead of its own label and link, and editing the CTA updates every place it is used. The usage list shows where each CTA appears.

## 5. Branding (`/admin/branding`)

Site name, tagline, wordmark subline, logo (and a light version for dark backgrounds), favicon source image, default social sharing image, and the presets for colour palette, typography, button shape and image corners. Uploading a favicon image generates every size the site needs (16, 32 and 48 px ICO, 180 px Apple touch icon, and 192 and 512 px app icons). Logos and favicons must be raster images; SVG uploads are refused for safety.

## 6. Navigation and footer

- **Navigation** (`/admin/navigation`): header menu (with one level of dropdown groups), mobile menu, footer columns and legal links. Header items can be shown on all devices, the desktop header only or the mobile menu only, and any item can be hidden without being deleted. Internal links must point to real site paths and external links must use https. Links to missing pages are flagged.
- **Header button** (on the Navigation screen): show or hide it, and set its label and link. A menu link to the same address is hidden on desktop to avoid repetition.
- **Account menu** (built in, not editable): the person icon in the header and an "Account" group in the mobile menu offer **Log in** and **Create account**, or **My account**, **My library**, **Orders**, **Settings** and **Log out** once someone is signed in. You don't need to add account links to the menus.
- **Footer** (`/admin/footer`): footer text, the newsletter link, whether to show the contact email and social links, the copyright line and an optional promotion (text and link).

## 7. Announcements (`/admin/announcements`)

A slim bar above the header. It is never a popup. Each announcement has a message, an optional link, a colour, optional start and end times, and a target (every page, homepage only, or chosen pages). It can be dismissible, in which case a reader's choice is remembered on their device. Only the first matching announcement is shown, so use the arrows to set priority. Saving an enabled announcement queues a rebuild.

## 8. Settings (`/admin/settings`)

Contact details, social profiles, SEO defaults (title pattern, default description, organisation details for structured data) and sitemap options. **Technical** settings (allowing search-engine indexing and the canonical site address) are visible to Super Admins only. They can only make indexing _stricter_ than the deployment configuration, never looser. Settings save and publish together, so the button reads **Save and publish**.

## 9. The shop (Batch 05)

The full reference is in `docs/commerce.md`. Day to day:

**Products (`/admin/products`).** Create a product, choose its type and write the details on the editor tabs:

- **Details:** title, subtitle, type and categories.
- **Description & FAQ:** description, benefits, who it is for, what is included, FAQs.
- **Images:** cover image from the media library, or a designed cover.
- **Files:** private files.
- **Pricing:** one price per currency, typed as a normal amount such as `12.50`; an optional compare-at price and promotion dates.
- **Bundle:** for bundles only.
- **SEO.**
- **Sales & publishing:** coming soon or on sale, and the availability dates.
- **History.**

Then:

- **Save draft** keeps your changes private. **Preview** shows exactly how the page will look.
- **Publish** makes the published version public. A product can be published as _Coming soon_, so it is visible but cannot be bought, or _On sale_.
- Publishing refuses, with the reason, when something is missing (for example "No deliverable files uploaded.").
- The **Problems** filter ("Missing files or invalid setup") lists every product with missing files, missing prices or another problem.
- **Duplicate** copies a product as a new draft. **Archive** removes it from the shop without deleting orders or customers' access.

Write only what is true: no invented page counts, testimonials, reviews or results.

**Prices and currencies.** Each currency has its own price, and nothing is converted automatically. A product with no KES price simply can't be bought in KES. Changing a price never changes past orders: each order keeps the price that was paid.

**Files.** Upload PDF, EPUB or ZIP files on the **Files** tab.

- They go to private storage, never the media library, and customers only get them through their library after a confirmed payment.
- A file can be refused, with the reason shown (for example a PDF containing JavaScript, or a ZIP with unsafe contents).
- **Upload a new version** to correct a file. New buyers get the latest version, and earlier buyers get both the latest version and the one they bought.
- **Deactivate** stops offering a file to new buyers.

**Collections and categories (`/admin/product-collections`).** Collections have their own shop page and can be shown on the homepage. Categories power the shop filters.

**Bundles (`/admin/bundles`).** A bundle includes other products. Buyers receive every included product, and keep them even if you later change the bundle.

**Orders, customers and access.**

- `/admin/orders` shows each order with its payment verification (what Paystack confirmed), the provider events, emails (and whether they were really sent), downloads and history.
- Staff can add notes, resend a receipt, re-check a payment with Paystack, or start a refund.
- `/admin/customers` helps customers: resend a verification or password-reset email, see their library, grant access with a reason.
- `/admin/entitlements` lists and audits access and downloads.

**Refunds.**

- Unless Paystack refunds are switched on in Payment settings, a refund is a two-step manual process. First record the request. Then refund the customer in the Paystack dashboard, and press **Record completed refund** with the Paystack reference.
- Nothing is ever shown as refunded before that.
- Choose whether access to the files ends when the refund completes.

**Reports (`/admin/reports/revenue`).** Totals are per currency, never added together, and test payments are kept apart from live ones.

**Payment settings (`/admin/payments`, Super Admin only).** Checkout is **disabled** until you change it here.

- **Test mode** uses Paystack test keys, no real money moves, and only customers you mark as test accounts can pay.
- **Live mode** stays locked until every readiness check passes, including the deployment switch and your confirmations.
- Secret keys are never shown or entered here; they live in the server configuration.

Paid sections never show anything that isn't approved and inside its booking dates, in drafts, previews and published pages alike. They follow the usual draft → preview → publish flow and page revisions. See `docs/partnerships.md` for sponsorship, affiliate and media kit workflows.

## 10. Who can do what

| Task                                     | Permission                                 | Built-in roles                               |
| ---------------------------------------- | ------------------------------------------ | -------------------------------------------- |
| See the homepage builder                 | `homepage.view`                            | Super Admin, Editor, Moderator               |
| Edit the homepage draft                  | `homepage.edit`                            | Super Admin, Editor                          |
| Publish the homepage                     | `homepage.publish`                         | Super Admin                                  |
| See / edit page drafts                   | `pages.view` / `pages.edit`                | Super Admin, Editor (edit), Moderator (view) |
| Create pages / publish or schedule pages | `pages.create` / `pages.publish`           | Super Admin                                  |
| Manage shared sections and global CTAs   | `reusable_sections.manage`                 | Super Admin                                  |
| Branding / announcements                 | `branding.manage` / `announcements.manage` | Super Admin                                  |
| Navigation, footer and general settings  | `navigation.manage`, `settings.manage`     | Super Admin                                  |
| Technical SEO settings                   | `settings.technical` (sensitive)           | Super Admin only                             |

The Administrator and Website Manager templates receive all of the website permissions above, except the sensitive one. Marketing Manager gets announcements. Editor-in-Chief and SEO Manager can view the homepage builder. Analyst and Content Writer gain nothing new. Other people can be given exactly what they need at `/admin/roles`.

Shop permissions:

| Task                            | Permission                                                                   | Typical roles                                                                          |
| ------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| View / create / edit products   | `products.view` / `products.create` / `products.edit`                        | Product Manager, Administrator (Marketing Manager: view)                               |
| Publish or archive products     | `products.publish` / `products.archive`                                      | Product Manager, Administrator                                                         |
| Prices, files, bundles          | `products.manage_prices`, `products.manage_files`, `products.manage_bundles` | Product Manager, Administrator                                                         |
| Orders (view, manage, export)   | `orders.view`, `orders.manage`, `orders.export`                              | Orders Manager, Administrator, Customer Support (view), Finance Manager (view, export) |
| Refunds                         | `refunds.issue`                                                              | Orders Manager, Finance Manager                                                        |
| Customers                       | `customers.view`, `customers.support`, `customers.manage`                    | Customer Support, Orders Manager, Administrator                                        |
| Access and downloads            | `entitlements.view`, `entitlements.manage`, `downloads.audit`                | Orders Manager, Administrator, Customer Support (view, audit)                          |
| Revenue reports                 | `finance.view`, `finance.export`                                             | Finance Manager (Administrator: view)                                                  |
| Payment events                  | `payments.view_events`                                                       | Orders Manager, Finance Manager, Administrator                                         |
| Payment settings and going live | `payments.configure` (sensitive)                                             | Super Admin only                                                                       |

Editorial roles (Editor, Content Editor, Content Writer, Moderator, Analyst) have no shop permissions.
