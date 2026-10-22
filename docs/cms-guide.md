# Website management guide (Batch 04)

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

**Collections update themselves.** _Featured articles_, _Latest articles_, _Selected article collection_ and _Topic cards_ draw from published content. An unpublished article never appears, even if you picked it. _Digital product showcase_ shows planned products as "Coming soon", with no prices and no purchase buttons, until the shop exists.

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
| Digital product showcase    | Coming-soon eBooks and resources; purchasing is disabled                                        |
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
- **Footer** (`/admin/footer`): footer text, the newsletter link, whether to show the contact email and social links, the copyright line and an optional promotion (text and link).

## 7. Announcements (`/admin/announcements`)

A slim bar above the header. It is never a popup. Each announcement has a message, an optional link, a colour, optional start and end times, and a target (every page, homepage only, or chosen pages). It can be dismissible, in which case a reader's choice is remembered on their device. Only the first matching announcement is shown, so use the arrows to set priority. Saving an enabled announcement queues a rebuild.

## 8. Settings (`/admin/settings`)

Contact details, social profiles, SEO defaults (title pattern, default description, organisation details for structured data) and sitemap options. **Technical** settings (allowing search-engine indexing and the canonical site address) are visible to Super Admins only. They can only make indexing _stricter_ than the deployment configuration, never looser. Settings save and publish together, so the button reads **Save and publish**.

## 9. Who can do what

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
