# Text-based courses and learning (Batch 09)

Think Positive Always courses are **self-paced written learning**: modules of lessons made
of text, images, examples, exercises, checklists, quizzes, reflections and downloadable
worksheets. There are no videos, streaming services or external learning platforms, and no
video fields anywhere in the system. Everything is managed in the admin (**Learning →
Courses**) and stored on the Hostinger VPS like the rest of the site.

## 1. How it fits together

| Need                                               | Where it lives                                                                                  |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Course pages, outline, outcomes, SEO               | `courses`, `course_modules`, `course_lessons` (published lessons only are shown)                |
| Price, checkout, Paystack, guest checkout, refunds | the existing commerce system: a premium course links to **one product of type “Online course”** |
| Access to a premium course                         | a usable **entitlement** to that product (purchase, bundle, manual grant, future membership)    |
| Worksheets and written resources                   | the course product's **private files** (Batch 08 storage and secure download links)             |
| Quizzes, reflections, self-assessments             | `course_assessments`, `assessment_questions`, `assessment_attempts`                             |
| Learners, progress, completion                     | `course_enrollments`, `lesson_progress`                                                         |
| Certificates                                       | `course_certificates` (verifiable code, PDF)                                                    |
| Scheduling                                         | the existing `flask content publish-due` timer                                                  |

There is no second pricing system: prices are always read from the product, on the server.

## 2. Creating a course

1. **Learning → Courses → New course.** Give it a title, a short summary (shown in the
   catalogue and search results) and choose **Free** or **Premium**.
2. In **Details**: subtitle, description (text blocks), learning outcomes, intended
   audience, prerequisites, level, estimated reading time (leave empty to add up the
   lessons), category, topics, author/instructor (an existing author profile), cover and
   social images from the Media Library, and SEO title/description/noindex.
3. Categories are managed with the **Categories** button on the course list. Topics are the
   site's existing topics.
4. The address (`/courses/<slug>`) can change until the course is first published; after
   that it is fixed so links keep working.

## 3. Modules and lessons (Curriculum tab)

- **Course → modules → lessons.** Each module has a title, description and optional
  learning objectives. Add lessons to a module by title; they start as drafts.
- **Reordering:** use the ↑/↓ buttons (keyboard accessible) to move modules and lessons,
  and “Move to…” to put a lesson in another module. The browser sends the complete layout;
  the server checks that every module and lesson appears exactly once and renumbers them
  safely (unique positions per module/course), so the order can never become inconsistent.
- **Lesson editor:** title, address, summary, estimated time (or estimated from the text at
  225 words per minute), _Required for course completion_, _Free preview_ and the content.
- **Lesson content blocks:** paragraphs, headings, lists, quotes, callouts, images and
  galleries from the Media Library, tables, dividers, plus lesson blocks:
  - **Key points** (highlighted takeaways), **Example / case study**;
  - **Exercise / reflection**: a prompt; learners can write private notes and mark it done.
    A _required_ exercise must be marked done before the lesson can be completed. Notes are
    private to the learner and never graded;
  - **Checklist**: items learners can tick while reading (not stored);
  - **Worksheet download**: one of the course product's files (see §5);
  - **Further reading**: links to articles, resources or https pages.
    Video and embed blocks are not accepted in lessons.
- **Publishing lessons:** only published lessons are visible to learners (and in the public
  outline as titles). Lessons with learner progress can't be deleted — unpublish them.

## 4. Publishing, scheduling and previews

- **Preview** shows the course page as visitors will see it (drafts marked) and lets staff
  read any lesson, privately. Nothing in a preview is public.
- **Publish** checks readiness first: at least one published lesson, a summary, and for
  premium courses a linked paid course product; published assessments must have questions
  (and quizzes at least one scored question). Warnings (draft lessons, unbuyable product,
  no outcomes) are shown but don't block.
- **Schedule** by choosing a date and time in the publish dialog; `flask content
publish-due` (the existing timer) publishes it when due and queues a site rebuild.
- **Unpublish** removes the course from the catalogue; **Archive** hides it permanently
  (enrolled learners keep access, nobody new can enrol); **Restore** returns it to draft.
- **Duplicate** copies details, curriculum and assessments as drafts (no learners, no
  product link, no worksheet downloads).
- **Coming soon** courses have a public page but no enrolment and no price.

## 5. Pricing, enrolment and worksheets

**Free courses.** Learners need a Think Positive Always account with a **confirmed email**.
_Enrol for free_ creates one enrolment per learner (a repeated click or a second tab is
harmless). An optional access period (days) ends access afterwards; the learner can enrol
again. _Open for new enrolments_ can be switched off at any time (existing learners keep
access).

**Premium courses.**

1. In **Commerce → Products**, create a product of type **Online course**, set its price
   (USD and any other currencies), access period if any, and upload its worksheets.
2. Link it on the course (_Course product_). Publish the course, then mark the product _on
   sale_ and publish it — a course product can't be sold until its course is published and
   available.
3. Visitors add the course to the cart from the course page and pay through the normal
   checkout (Paystack test mode until live payments are explicitly approved).

Access is granted only after a provider-verified payment (the existing webhook/verify
flow); repeated webhooks and retries never create a second entitlement or enrolment.
Refunds that revoke access, revoked entitlements and expired access periods end course
access immediately: every learner request re-checks it.

**Worksheets.** Upload PDF workbooks, eBooks, worksheets, templates, planners or learning
packs (the approved formats from Batch 08) to the course product, then add _Worksheet
download_ blocks to lessons. Files stay in private storage; learners get short-lived,
logged download links through the same authorisation as the shop library (version policy,
download limits and revocation apply). Free courses with a linked product grant those files
through a course entitlement when someone enrols; nothing else is unlocked.

## 6. Assessments (Assessments tab)

- **Quiz** — scored automatically: single choice, multiple select (all correct options
  required) and true/false questions, with points per question and a passing score (%).
  Written answers in a quiz are saved but never scored.
- **Written reflection** — written answers and rating scales; never marked right or wrong.
  Submitting counts as done.
- **Self-assessment** — rating scales (with labels) and notes for the learner.
- Each assessment can follow a lesson or sit after the modules (course-level), can be
  required for completion, and can limit attempts. _Reveal correct answers_: after each
  submission, only after passing, or never (score only).
- **Answer keys are protected:** correct answers and explanations are never sent to
  learners before they submit; staff roles without _Manage assessments_ can't see them in
  the admin either. All validation and scoring happen on the server; past attempts keep a
  copy of each question so history stays readable after edits.

## 7. Learners, progress and completion

- **Learner area:** _My learning_ (`/account/learning`) lists courses with progress and a
  Continue button; `/learn/<course>` shows the outline with completed lessons and
  assessments; `/learn/<course>/<lesson>` is the reader (adjustable text size, previous /
  next, exercises, downloads, inline quizzes, _Mark as complete_).
- **Completion** is computed from stored records only: every _required_ published lesson
  completed (or every published lesson if none is marked required) **and** every required
  published assessment passed (quizzes) or submitted (reflections, self-assessments).
- **Learners tab (admin):** search and filter learners, see progress per lesson and
  assessment results (scores only — private notes and written reflections are not shown),
  enrol an existing customer manually (with a reason), end or restore an enrolment.
- **Reports:** the course list shows real counts (courses by status, enrolments, active
  learners in the last 30 days, completions, completion rate, certificates and quiz pass
  rates); each course's Learners tab shows its own figures. Site-wide analytics remain a
  planned module.

## 8. Certificates

- Issued automatically when a learner completes a course with certificates enabled, using
  their account name; if the account has no name, the learner enters the name to show.
- Each certificate has a random code (`TPA-XXXX-XXXX-XXXX`). Anyone can check it at
  `/certificates/<code>` (valid or revoked, name, course, date). Learners download a PDF
  (US Letter) from My learning.
- The certificate and the verification page state that it is **a platform-issued
  certificate of completion, not an accredited qualification**.
- Staff with _Manage enrolments and certificates_ can correct the name, revoke or reinstate
  a certificate; each change needs a note and is recorded in the audit log.
- The PDF uses the standard Helvetica font: names outside Western European characters are
  transliterated in the PDF (the verification page shows the exact name).

## 9. Guest purchases and claiming

A guest can buy a premium course without an account (Batch 07.6 guest checkout). Taking the
course needs an account so progress belongs to someone:

1. After paying, the guest sees: _sign in or create an account with the purchase email and
   confirm it_.
2. Once that account's email address is **confirmed**, the purchase counts in the account
   and the course appears in My learning automatically.
3. Registering with someone else's purchase email is not enough: until the mailbox is
   confirmed, learning pages answer _Confirm your email to start learning_ and nothing is
   claimed. Guest purchase recovery (`/purchases`) and refunds work as before.

## 10. Permissions

| Permission                   | Allows                                                        |
| ---------------------------- | ------------------------------------------------------------- |
| `courses.view`               | see courses in the admin (required for everything below)      |
| `courses.create`             | create and duplicate courses                                  |
| `courses.edit`               | details, access rules, product link, SEO, categories          |
| `courses.publish`            | publish, schedule, unpublish; publish lessons and assessments |
| `courses.archive`            | archive, restore, delete never-published drafts               |
| `courses.manage_curriculum`  | modules, lessons, content, order, worksheets                  |
| `courses.manage_assessments` | assessments, questions, answer keys                           |
| `courses.view_enrollments`   | learners, progress, results, certificates                     |
| `courses.manage_enrollments` | enrol/remove learners, correct/revoke certificates            |
| `courses.view_reports`       | course dashboards and pass rates                              |

Default grants: Super Admin (all), Administrator (all), Editor and Editor-in-Chief
(authoring and publishing; Editor-in-Chief also reports), Content Editor (authoring, no
publishing), Analyst and Marketing Manager (view and reports), Customer Support (view,
learners, enrolments), Product Manager and Website Manager (view). Every endpoint checks its
permission on the server.

## 11. Search, SEO and privacy

- `/courses` (search, category, topic, free/premium, level, sort) and published course
  pages are prerendered and listed in the sitemap (unless _noindex_), with schema.org
  `Course` data (provider, real offers, free flag, workload, outcomes).
- Lesson content, assessments, answers, learner records and certificates are **never**
  prerendered or listed: `/learn/*` and `/certificates/*` are client-only shells (no-store,
  noindex, disallowed in robots.txt), and the course page only lists lesson titles.
  Lessons marked _free preview_ can be read by anyone from the outline (worksheets stay
  behind enrolment).
- Customer data exports include enrolments, progress, notes, answers and certificates;
  deleting an account erases notes and written answers, ends enrolments and revokes its
  certificates.

## 12. Backups, migrations and deployment

- Migration **`d4f9a2c61e58`** adds the course tables only (no existing table changes) and
  the ten permissions with their default grants; `flask --app wsgi rbac sync` reports zeros
  afterwards. Its downgrade refuses to run while any course exists.
- All course data is in PostgreSQL, and worksheets are product files in
  `PRODUCT_FILES_ROOT`, so the Batch 08 backups (`deploy/backup/tpa-backup.sh`) already
  include everything; restore as described in `docs/backups.md`.
- Deployment steps are in `docs/deployment.md` (Upgrading from Batch 08.1).

## 13. Limitations

- Exercise notes and written reflections are for the learner; there is no staff marking or
  feedback workflow for subjective answers.
- Checklist ticks in lessons are not stored.
- Certificates use a fixed design and US Letter size; non-Latin names are transliterated in
  the PDF.
- Course prices follow the product's currencies; there is no currency conversion.
- Lesson content edits on a published course go live when saved (there is no separate
  draft copy of a published lesson; unpublish a lesson to rework it privately).
- Memberships are still planned; `access.grant(source="membership")` already works for
  membership-eligible course products.
