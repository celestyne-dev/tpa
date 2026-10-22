"""Page builder: homepage drafts and publishing, CMS pages, shared sections, CTAs,
announcements, navigation visibility and Batch 04 permissions.

Incremental and non-destructive:
- new tables: page_revisions, reusable_sections, global_ctas, announcements;
- new columns on pages (template, path, parent, SEO/social fields, lock version,
  published snapshot and publish/schedule timestamps), page_sections (name,
  design, visibility, shared section link) and navigation_items (visibility),
  added with ALTER TABLE ... ADD COLUMN only;
- data: existing homepage sections are converted to the Batch 04 format.
  Sections still equal to the Batch 02 defaults are replaced by the Batch 04
  defaults (which reproduce the current hand-built homepage); sections that
  were edited keep their text, converted field by field. A homepage that is
  already published gets its first published snapshot (revision #1) built
  from those sections, so the live homepage is unchanged. Rows are only
  converted once (rows with a design are skipped), so the step is idempotent;
- permissions: new catalogue entries and grants for the built-in roles and the
  templates that still exist; any role (custom roles included) that could edit
  pages, view pages or manage settings keeps the equivalent homepage/branding
  permission. No role gains unrelated access.

Users, roles, assignments, articles, media, redirects, settings, publishing
jobs and menus are preserved.

Downgrade removes the new tables, columns and permissions and converts section
content back to the Batch 02 field format where possible. On SQLite, pages and
page_sections are never rebuilt (that would cascade-delete sections): their
four new reference columns stay behind as unused nullable columns.

Revision ID: de3d968df6ce
Revises: a817c9636960
Create Date: 2026-10-22 20:29:13.162522

"""
import copy
import json
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text  # noqa: F401  (used by rendered JSONB types)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'de3d968df6ce'
down_revision = 'a817c9636960'
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql')

# Frozen snapshot of app/auth/permissions.py at this revision.
# (key, label, description, group, module, available, sensitive)
PERMISSIONS = [('dashboard.view', 'View dashboard', '', 'Dashboard & analytics', 'dashboard', True, False),
 ('analytics.view',
  'View content analytics',
  '',
  'Dashboard & analytics',
  'analytics',
  True,
  False),
 ('articles.view',
  'View all articles',
  "See every article, including other people's drafts.",
  'Articles',
  'articles',
  True,
  False),
 ('articles.create', 'Create articles', '', 'Articles', 'articles', True, False),
 ('articles.edit_own',
  'Edit own drafts',
  'Edit articles you created while they are drafts.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.edit_any', 'Edit any article', '', 'Articles', 'articles', True, False),
 ('articles.submit_review', 'Submit for review', '', 'Articles', 'articles', True, False),
 ('articles.approve', 'Approve articles', '', 'Articles', 'articles', True, False),
 ('articles.publish', 'Publish and schedule', '', 'Articles', 'articles', True, False),
 ('articles.unpublish', 'Unpublish', '', 'Articles', 'articles', True, False),
 ('articles.archive', 'Archive and restore', '', 'Articles', 'articles', True, False),
 ('articles.delete',
  'Delete unpublished drafts',
  'Permanently delete drafts that were never published.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.view_revisions',
  'View revision history',
  'For articles you can open.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.restore_revisions',
  'Restore revisions',
  'Only on articles you are allowed to edit.',
  'Articles',
  'articles',
  True,
  False),
 ('articles.preview',
  'Preview drafts',
  'Private, non-indexed preview of articles you can open.',
  'Articles',
  'articles',
  True,
  False),
 ('topics.manage', 'Manage topics', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('tags.manage', 'Manage tags', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('authors.manage', 'Manage authors', '', 'Topics, tags & authors', 'taxonomy', True, False),
 ('media.view', 'View media library', '', 'Media library', 'media', True, False),
 ('media.upload',
  'Upload media',
  'Upload images; they are validated and optimised automatically.',
  'Media library',
  'media',
  True,
  False),
 ('media.edit',
  'Edit media details',
  'Alt text, title, caption, credit and focal point.',
  'Media library',
  'media',
  True,
  False),
 ('media.replace', 'Replace media files', '', 'Media library', 'media', True, False),
 ('media.delete',
  'Archive and delete media',
  'Media still used by content can be archived but never deleted.',
  'Media library',
  'media',
  True,
  False),
 ('homepage.view',
  'View homepage builder',
  'See the homepage sections, drafts, previews and history.',
  'Pages & homepage',
  'homepage',
  True,
  False),
 ('homepage.edit',
  'Edit homepage drafts',
  'Change, add, reorder and restore homepage sections as a draft.',
  'Pages & homepage',
  'homepage',
  True,
  False),
 ('homepage.publish',
  'Publish the homepage',
  'Make homepage drafts live (queues a site rebuild).',
  'Pages & homepage',
  'homepage',
  True,
  False),
 ('pages.view', 'View pages', '', 'Pages & homepage', 'pages', True, False),
 ('pages.edit',
  'Edit page drafts',
  'Edit page content, sections and SEO as a draft; restore revisions.',
  'Pages & homepage',
  'pages',
  True,
  False),
 ('pages.create', 'Create and duplicate pages', '', 'Pages & homepage', 'pages', True, False),
 ('pages.publish',
  'Publish pages',
  'Publish, schedule, unpublish, archive and restore pages.',
  'Pages & homepage',
  'pages',
  True,
  False),
 ('reusable_sections.manage',
  'Manage shared sections and calls to action',
  'Edit shared sections (changes can update every page using them).',
  'Pages & homepage',
  'pages',
  True,
  False),
 ('branding.manage',
  'Manage branding',
  'Site name, logos, favicon, social image and approved style presets.',
  'Site settings',
  'branding',
  True,
  False),
 ('announcements.manage',
  'Manage announcement banners',
  '',
  'Site settings',
  'announcements',
  True,
  False),
 ('navigation.manage', 'Manage navigation menus', '', 'Navigation', 'navigation', True, False),
 ('settings.manage',
  'Manage site settings',
  'Contact details, social links, footer and the newsletter flag.',
  'Site settings',
  'settings',
  True,
  False),
 ('settings.technical',
  'Manage indexing and canonical URL',
  'Search engine indexing and the canonical website address (Super Admin).',
  'Site settings',
  'settings',
  True,
  True),
 ('settings.security', 'Manage security settings', '', 'Site settings', 'settings', False, True),
 ('seo.manage',
  'Manage SEO settings',
  'Default titles, descriptions and sharing image; article canonical URLs, indexing and '
  'post-publication slug changes.',
  'SEO',
  'seo',
  True,
  False),
 ('seo.view',
  'View SEO audit',
  'The SEO dashboard and per-article checks.',
  'SEO',
  'seo',
  True,
  False),
 ('redirects.manage', 'Manage redirects', '', 'SEO', 'redirects', True, False),
 ('publishing.view',
  'View publishing jobs',
  'Static site build status and history.',
  'Publishing',
  'publishing',
  True,
  False),
 ('publishing.manage',
  'Run and retry publishing jobs',
  '',
  'Publishing',
  'publishing',
  True,
  False),
 ('products.view', 'View digital products', '', 'Digital products', 'products', False, False),
 ('products.manage',
  'Manage products and pricing',
  '',
  'Digital products',
  'products',
  False,
  False),
 ('orders.view', 'View orders', '', 'Orders & refunds', 'orders', False, False),
 ('orders.manage', 'Manage orders', '', 'Orders & refunds', 'orders', False, False),
 ('refunds.issue', 'Issue refunds', '', 'Orders & refunds', 'orders', False, False),
 ('payments.configure', 'Configure payments', '', 'Orders & refunds', 'payments', False, True),
 ('customers.view', 'View customers', '', 'Customers', 'customers', False, False),
 ('customers.manage', 'Manage customers', '', 'Customers', 'customers', False, False),
 ('partnerships.view', 'View partnerships', '', 'Partnerships', 'partnerships', False, False),
 ('partnerships.manage', 'Manage partnerships', '', 'Partnerships', 'partnerships', False, False),
 ('advertising.view', 'View advertising', '', 'Advertising', 'advertising', False, False),
 ('advertising.manage', 'Manage advertising', '', 'Advertising', 'advertising', False, False),
 ('affiliates.view',
  'View affiliate campaigns',
  '',
  'Affiliate campaigns',
  'affiliates',
  False,
  False),
 ('affiliates.manage',
  'Manage affiliate campaigns',
  '',
  'Affiliate campaigns',
  'affiliates',
  False,
  False),
 ('newsletters.manage',
  'Manage newsletters',
  '',
  'Newsletters & subscribers',
  'newsletters',
  False,
  False),
 ('subscribers.view',
  'View subscribers',
  '',
  'Newsletters & subscribers',
  'newsletters',
  False,
  False),
 ('subscribers.export',
  'Export subscribers',
  '',
  'Newsletters & subscribers',
  'newsletters',
  False,
  False),
 ('courses.manage', 'Manage courses', '', 'Courses & memberships', 'courses', False, False),
 ('memberships.manage',
  'Manage memberships',
  '',
  'Courses & memberships',
  'memberships',
  False,
  False),
 ('finance.view', 'View finance reports', '', 'Finance', 'finance', False, False),
 ('finance.manage', 'Manage finance', '', 'Finance', 'finance', False, False),
 ('users.view', 'View administrators', '', 'Users, roles & audit', 'users', True, False),
 ('users.manage',
  'Manage administrator accounts',
  'Disable, reactivate and reset passwords of administrators with equal or fewer permissions.',
  'Users, roles & audit',
  'users',
  True,
  False),
 ('roles.manage', 'Manage roles and permissions', '', 'Users, roles & audit', 'roles', True, True),
 ('roles.assign',
  'Assign roles and invite administrators',
  '',
  'Users, roles & audit',
  'roles',
  True,
  True),
 ('audit.view', 'View audit log', '', 'Users, roles & audit', 'audit', True, False)]

NEW_KEYS = ['homepage.view',
 'homepage.edit',
 'homepage.publish',
 'pages.create',
 'pages.publish',
 'reusable_sections.manage',
 'branding.manage',
 'announcements.manage',
 'settings.technical']

# Built-in roles and templates (if they still exist).
GRANTS = {'administrator': ['announcements.manage',
                   'branding.manage',
                   'homepage.edit',
                   'homepage.publish',
                   'homepage.view',
                   'pages.create',
                   'pages.publish',
                   'reusable_sections.manage'],
 'editor': ['homepage.edit', 'homepage.view'],
 'editor_in_chief': ['homepage.view'],
 'marketing_manager': ['announcements.manage', 'homepage.view'],
 'moderator': ['homepage.view'],
 'seo_manager': ['homepage.view'],
 'website_manager': ['announcements.manage',
                     'branding.manage',
                     'homepage.edit',
                     'homepage.publish',
                     'homepage.view',
                     'pages.create',
                     'pages.publish',
                     'reusable_sections.manage']}

# Any role (custom ones included) keeps what it could already do.
IMPLIED = {'pages.edit': ['homepage.edit', 'homepage.view'],
 'pages.view': ['homepage.view'],
 'settings.manage': ['branding.manage']}

# Batch 02 homepage defaults: sections still equal to these were never edited.
HOME_V1 = {'featured-articles': {'content': {'cta_label': 'View all articles',
                                   'cta_url': '/articles',
                                   'description': 'Thoughtful articles on mindset, confidence, '
                                                  'resilience, and intentional living.',
                                   'eyebrow': 'From the journal',
                                   'heading': 'Fresh Perspectives for Everyday Life'},
                       'section_type': 'featured_articles',
                       'variant': 'lead_and_grid'},
 'final-cta': {'content': {'body': 'Wherever you are on your journey, there is something here to '
                                   'encourage you.',
                           'heading': 'Your next chapter can start today',
                           'primary_cta_label': 'Start reading',
                           'primary_cta_url': '/articles',
                           'secondary_cta_label': 'Explore free resources',
                           'secondary_cta_url': '/free-resources'},
               'section_type': 'call_to_action',
               'variant': 'default'},
 'hero': {'content': {'body': 'Practical encouragement, thoughtful resources, and tools to help '
                              'you grow through every season of life.',
                      'eyebrow': 'Think Positive Always',
                      'heading': 'A Better Mindset.',
                      'highlight': 'A Brighter Life.',
                      'primary_cta_label': 'Explore Our Resources',
                      'primary_cta_url': '/free-resources',
                      'secondary_cta_label': 'Read Our Articles',
                      'secondary_cta_url': '/articles'},
          'section_type': 'hero',
          'variant': 'default'},
 'newsletter': {'content': {'description': 'One thoughtful email each week to help you reset your '
                                           'mindset, find perspective, and keep moving forward.',
                            'heading': 'The Positive Reset'},
                'section_type': 'newsletter_cta',
                'variant': 'default'},
 'partnerships': {'content': {'body': 'We welcome conversations with brands, organisations, and '
                                      'publishers whose values align with ours.',
                              'cta_label': 'Explore partnerships',
                              'cta_url': '/partner-with-us',
                              'eyebrow': 'Partner with us',
                              'heading': "Let's Create Something Meaningful Together",
                              'items': ['Sponsored content',
                                        'Brand storytelling',
                                        'Digital campaigns',
                                        'Newsletter sponsorships',
                                        'Relevant resource partnerships']},
                  'section_type': 'partnership_cta',
                  'variant': 'dark'},
 'products': {'content': {'description': 'Thoughtfully created guides and practical tools to help '
                                         'you take the next step.',
                          'eyebrow': 'Coming soon to the shop',
                          'footnote': 'These titles are in development and not yet available to '
                                      'purchase.',
                          'heading': 'Resources for Your Personal Growth Journey'},
              'section_type': 'product_previews',
              'variant': 'default'},
 'topics': {'content': {'description': 'Find encouragement and practical guidance for the part of '
                                       'life you are working on right now.',
                        'eyebrow': 'Explore by topic',
                        'heading': 'Explore What Matters to You'},
            'section_type': 'topics_grid',
            'variant': 'default'},
 'welcome': {'content': {'body': 'Think Positive Always exists to help people develop a healthier '
                                 "mindset, navigate life's challenges, build confidence, and move "
                                 'forward with intention.',
                         'cta_label': 'More about Think Positive Always',
                         'cta_url': '/about',
                         'eyebrow': 'Our mission',
                         'heading': 'Welcome to Think Positive Always'},
             'section_type': 'brand_intro',
             'variant': 'default'},
 'why-tpa': {'content': {'description': 'Inspiration matters most when it helps you live '
                                        'differently.',
                         'eyebrow': 'Why Think Positive Always?',
                         'heading': 'Inspiration That Goes Beyond Words',
                         'items': ['Grounded in real life',
                                   'Practical, not just positive',
                                   'Made for reflection',
                                   'Designed for action'],
                         'quote': 'Positive thinking is not pretending everything is fine. It is '
                                  'believing you can still move forward.'},
             'section_type': 'feature_list',
             'variant': 'default'}}

# Batch 04 homepage (reproduces the hand-built Batch 01 homepage).
HOME_V2 = {'featured-articles': {'content': {'count': 3,
                                   'cta': {'cta_id': None,
                                           'label': 'View all articles',
                                           'style': 'outline',
                                           'url': '/articles'},
                                   'description': 'Thoughtful articles on mindset, confidence, '
                                                  'resilience, and intentional living.',
                                   'eyebrow': 'From the journal',
                                   'heading': 'Fresh Perspectives for Everyday Life',
                                   'mode': 'featured'},
                       'design': {'align': 'left', 'background': 'cream', 'spacing': 'md'},
                       'key': 'featured-articles',
                       'name': 'Featured articles',
                       'section_type': 'featured_articles',
                       'variant': 'lead_and_grid'},
 'final-cta': {'content': {'body': 'Wherever you are on your journey, there is something here to '
                                   'encourage you. Read an article, explore a topic that matters '
                                   'to you, and take one small step forward.',
                           'heading': 'Your next chapter can start today',
                           'primary_cta': {'cta_id': None,
                                           'label': 'Start reading',
                                           'style': '',
                                           'url': '/articles'},
                           'secondary_cta': {'cta_id': None,
                                             'label': 'Explore free resources',
                                             'style': 'outline',
                                             'url': '/free-resources'}},
               'design': {'background': 'ivory', 'spacing': 'lg', 'width': 'narrow'},
               'key': 'final-cta',
               'name': 'Closing invitation',
               'section_type': 'call_to_action',
               'variant': 'centered'},
 'hero': {'content': {'body': 'Practical encouragement, thoughtful resources, and tools to help '
                              'you grow through every season of life.',
                      'eyebrow': 'Think Positive Always',
                      'heading': 'A Better Mindset.',
                      'highlight': 'A Brighter Life.',
                      'primary_cta': {'cta_id': None,
                                      'label': 'Explore Our Resources',
                                      'style': '',
                                      'url': '/free-resources'},
                      'secondary_cta': {'cta_id': None,
                                        'label': 'Read Our Articles',
                                        'style': 'outline',
                                        'url': '/articles'}},
          'design': {'align': 'left', 'background': 'ivory', 'spacing': 'lg'},
          'key': 'hero',
          'name': 'Hero',
          'section_type': 'hero',
          'variant': 'split'},
 'newsletter': {'content': {'description': 'One thoughtful email each week to help you reset your '
                                           'mindset, find perspective, and keep moving forward.',
                            'eyebrow': 'Weekly newsletter',
                            'heading': '',
                            'show_learn_more': True},
                'design': {'background': 'ivory', 'spacing': 'sm', 'width': 'wide'},
                'key': 'newsletter',
                'name': 'Newsletter',
                'section_type': 'newsletter_cta',
                'variant': 'panel'},
 'partnerships': {'content': {'body': 'We welcome conversations with brands, organisations, and '
                                      'publishers whose values align with ours. Together we can '
                                      'share thoughtful, useful messages with a community that '
                                      'cares about personal growth, well-being, and positive '
                                      'change.',
                              'cta': {'cta_id': None,
                                      'label': 'Explore partnerships',
                                      'style': 'light',
                                      'url': '/partner-with-us'},
                              'eyebrow': 'Partner with us',
                              'heading': "Let's Create Something Meaningful Together",
                              'items': ['Sponsored content',
                                        'Brand storytelling',
                                        'Digital campaigns',
                                        'Newsletter sponsorships',
                                        'Relevant resource partnerships'],
                              'list_heading': 'Collaboration opportunities'},
                  'design': {'spacing': 'lg'},
                  'key': 'partnerships',
                  'name': 'Partnerships',
                  'section_type': 'partnership_cta',
                  'variant': 'dark'},
 'products': {'content': {'count': 3,
                          'cta': {'cta_id': None,
                                  'label': 'Visit the shop',
                                  'style': 'outline',
                                  'url': '/shop'},
                          'description': 'Thoughtfully created guides and practical tools to help '
                                         'you take the next step.',
                          'eyebrow': 'Coming soon to the shop',
                          'footnote': 'These titles are in development and not yet available to '
                                      'purchase.',
                          'heading': 'Resources for Your Personal Growth Journey'},
              'design': {'align': 'left', 'background': 'ivory', 'spacing': 'md'},
              'key': 'products',
              'name': 'Coming soon to the shop',
              'section_type': 'product_previews',
              'variant': 'grid'},
 'topics': {'content': {'description': 'Find encouragement and practical guidance for the part of '
                                       'life you are working on right now.',
                        'eyebrow': 'Explore by topic',
                        'heading': 'Explore What Matters to You',
                        'mode': 'featured'},
            'design': {'align': 'left', 'background': 'ivory', 'spacing': 'md'},
            'key': 'topics',
            'name': 'Topics',
            'section_type': 'topics_grid',
            'variant': 'cards_3'},
 'welcome': {'content': {'body': 'Think Positive Always exists to help people develop a healthier '
                                 "mindset, navigate life's challenges, build confidence, and move "
                                 'forward with intention.\n'
                                 '\n'
                                 'Here you will find honest encouragement, mindset insights, and '
                                 'personal growth content written for real life, along with '
                                 'practical resources designed to help you turn reflection into '
                                 'meaningful action.',
                         'cta': {'cta_id': None,
                                 'label': 'More about Think Positive Always',
                                 'style': 'outline',
                                 'url': '/about'},
                         'eyebrow': 'Our mission',
                         'heading': 'Welcome to Think Positive Always',
                         'stat_caption': 'people follow Think Positive Always on LinkedIn, part of '
                                         'a growing international community that shows up for '
                                         'daily encouragement and perspective.'},
             'design': {'background': 'cream', 'spacing': 'md'},
             'key': 'welcome',
             'name': 'Mission and community',
             'section_type': 'brand_intro',
             'variant': 'with_stat'},
 'why-tpa': {'content': {'description': 'Inspiration matters most when it helps you live '
                                        'differently. Everything we create is designed to '
                                        'encourage you and to help you act on that encouragement.',
                         'eyebrow': 'Why Think Positive Always?',
                         'heading': 'Inspiration That Goes Beyond Words',
                         'items': [{'icon': 'heart-handshake',
                                    'text': 'Encouragement that acknowledges real challenges: '
                                            'setbacks, change, uncertainty, and the ordinary '
                                            'pressures of everyday life.',
                                    'title': 'Grounded in real life'},
                                   {'icon': 'compass',
                                    'text': 'Clear mindset and personal growth advice you can '
                                            'apply today, without empty slogans or unrealistic '
                                            'promises.',
                                    'title': 'Practical, not just positive'},
                                   {'icon': 'notebook-pen',
                                    'text': 'Content that invites you to pause, ask better '
                                            'questions, and understand yourself with more honesty '
                                            'and kindness.',
                                    'title': 'Made for reflection'},
                                   {'icon': 'footprints',
                                    'text': 'Resources built to help you take meaningful next '
                                            'steps, so insight becomes progress you can feel.',
                                    'title': 'Designed for action'}],
                         'quote': 'Positive thinking is not pretending everything is fine. It is '
                                  'believing you can still move forward.'},
             'design': {'background': 'beige', 'card_style': 'soft', 'spacing': 'md'},
             'key': 'why-tpa',
             'name': 'Why Think Positive Always',
             'section_type': 'feature_list',
             'variant': 'sticky_intro'}}

# Batch 02 content fields per section type (used to convert in both directions).
LEGACY_FIELDS = {
    'hero': ['eyebrow', 'heading', 'highlight', 'body', 'primary_cta_label', 'primary_cta_url',
             'secondary_cta_label', 'secondary_cta_url'],
    'brand_intro': ['eyebrow', 'heading', 'body', 'cta_label', 'cta_url'],
    'topics_grid': ['eyebrow', 'heading', 'description'],
    'featured_articles': ['eyebrow', 'heading', 'description', 'cta_label', 'cta_url'],
    'product_previews': ['eyebrow', 'heading', 'description', 'footnote'],
    'newsletter_cta': ['heading', 'description'],
    'feature_list': ['eyebrow', 'heading', 'description', 'quote', 'items'],
    'partnership_cta': ['eyebrow', 'heading', 'body', 'cta_label', 'cta_url', 'items'],
    'call_to_action': ['heading', 'body', 'primary_cta_label', 'primary_cta_url',
                       'secondary_cta_label', 'secondary_cta_url'],
    'rich_text': ['heading', 'body'],
}
# Batch 02 variant -> Batch 04 variant.
VARIANTS = {
    'hero': {'default': 'split', 'centered': 'centered'},
    'brand_intro': {'default': 'with_stat'},
    'topics_grid': {'default': 'cards_3'},
    'featured_articles': {'lead_and_grid': 'lead_and_grid', 'grid': 'grid_3'},
    'product_previews': {'default': 'grid'},
    'newsletter_cta': {'default': 'panel'},
    'feature_list': {'default': 'sticky_intro'},
    'partnership_cta': {'dark': 'dark', 'light': 'light'},
    'call_to_action': {'default': 'centered'},
    'rich_text': {'default': 'default', 'narrow': 'narrow'},
}
TYPE_DESIGN = {
    'hero': {'background': 'ivory', 'spacing': 'lg', 'align': 'left'},
    'brand_intro': {'background': 'cream', 'spacing': 'md'},
    'topics_grid': {'background': 'ivory', 'spacing': 'md', 'align': 'left'},
    'featured_articles': {'background': 'cream', 'spacing': 'md', 'align': 'left'},
    'product_previews': {'background': 'ivory', 'spacing': 'md', 'align': 'left'},
    'newsletter_cta': {'background': 'ivory', 'spacing': 'sm', 'width': 'wide'},
    'feature_list': {'background': 'beige', 'spacing': 'md', 'card_style': 'soft'},
    'partnership_cta': {'spacing': 'lg'},
    'call_to_action': {'background': 'ivory', 'spacing': 'lg', 'width': 'narrow'},
    'rich_text': {'background': 'ivory', 'spacing': 'md'},
}
ICONS = ['heart-handshake', 'compass', 'notebook-pen', 'footprints', 'sun', 'sprout', 'gem', 'leaf']
VISIBILITY = {'devices': 'all', 'starts_at': None, 'ends_at': None}


def _is_sqlite():
    return op.get_bind().dialect.name == 'sqlite'


def _load(value):
    if value is None:
        return None
    return json.loads(value) if isinstance(value, str) else value


def _cta(content, prefix, style=''):
    label = (content.get(f'{prefix}_label') or '').strip()
    url = (content.get(f'{prefix}_url') or '').strip()
    if not (label and url):
        return {'label': '', 'url': '', 'style': '', 'cta_id': None}
    return {'label': label, 'url': url, 'style': style, 'cta_id': None}


def convert_edited(section_type, variant, content):
    """Batch 02 content an editor changed -> Batch 04 fields (text is kept as written)."""
    c = dict(content or {})
    out = {k: v for k, v in c.items() if not k.endswith(('_label', '_url'))}
    if section_type in ('hero', 'call_to_action'):
        out['primary_cta'] = _cta(c, 'primary_cta')
        out['secondary_cta'] = _cta(c, 'secondary_cta', 'outline')
    if section_type in ('brand_intro', 'featured_articles'):
        out['cta'] = _cta(c, 'cta', 'outline')
    if section_type == 'partnership_cta':
        out['cta'] = _cta(c, 'cta', 'light')
        out['list_heading'] = 'Collaboration opportunities'
    if section_type in ('topics_grid', 'featured_articles'):
        out['mode'] = 'featured'
    if section_type in ('featured_articles', 'product_previews'):
        out['count'] = 3
    if section_type == 'feature_list':
        out['items'] = [
            {'title': t, 'text': '', 'icon': ICONS[i % len(ICONS)]}
            for i, t in enumerate(c.get('items') or []) if isinstance(t, str) and t.strip()
        ]
    if section_type == 'rich_text' and isinstance(c.get('body'), str):
        out['body'] = [{'type': 'paragraph', 'text': p.strip()}
                       for p in c['body'].split('\n\n') if p.strip()]
    return VARIANTS.get(section_type, {}).get(variant, variant), out


def convert_back(section_type, content):
    """Batch 04 content -> Batch 02 fields (downgrade, best effort)."""
    allowed = LEGACY_FIELDS.get(section_type)
    if allowed is None:
        return content
    c = dict(content or {})
    out = {}
    for prefix in ('primary_cta', 'secondary_cta', 'cta'):
        value = c.get(prefix)
        if isinstance(value, dict):
            out[f'{prefix}_label'] = value.get('label') or ''
            out[f'{prefix}_url'] = value.get('url') or ''
    for key in allowed:
        if key in out:
            continue
        value = c.get(key)
        if key == 'items' and isinstance(value, list):
            value = [i.get('title', '') if isinstance(i, dict) else i for i in value]
        if key == 'body' and isinstance(value, list):
            value = '\n\n'.join(b.get('text', '') for b in value if isinstance(b, dict))
        if value is not None:
            out[key] = value
    return {k: v for k, v in out.items() if k in allowed}


def _add_columns():
    if _is_sqlite():
        # Columns kept by a previous SQLite downgrade (see downgrade()) are not re-added.
        inspector = sa.inspect(op.get_bind())
        existing = {
            (table, c['name'])
            for table in ('pages', 'page_sections', 'navigation_items')
            for c in inspector.get_columns(table)
        }
        for statement in (
            "ALTER TABLE navigation_items ADD COLUMN visibility VARCHAR(10) DEFAULT 'all' NOT NULL",
            "ALTER TABLE page_sections ADD COLUMN name VARCHAR(120)",
            "ALTER TABLE page_sections ADD COLUMN design JSON DEFAULT '{}' NOT NULL",
            "ALTER TABLE page_sections ADD COLUMN visibility JSON DEFAULT '{}' NOT NULL",
            "ALTER TABLE page_sections ADD COLUMN reusable_section_id INTEGER "
            "CONSTRAINT fk_page_sections_reusable_section_id_reusable_sections "
            "REFERENCES reusable_sections (id) ON DELETE RESTRICT",
            "ALTER TABLE pages ADD COLUMN template VARCHAR(40) DEFAULT 'standard' NOT NULL",
            "ALTER TABLE pages ADD COLUMN is_system BOOLEAN DEFAULT '0' NOT NULL",
            "ALTER TABLE pages ADD COLUMN parent_id INTEGER "
            "CONSTRAINT fk_pages_parent_id_pages REFERENCES pages (id) ON DELETE SET NULL",
            "ALTER TABLE pages ADD COLUMN path VARCHAR(400)",
            "ALTER TABLE pages ADD COLUMN published_path VARCHAR(400)",
            "ALTER TABLE pages ADD COLUMN canonical_url VARCHAR(500)",
            "ALTER TABLE pages ADD COLUMN social_title VARCHAR(200)",
            "ALTER TABLE pages ADD COLUMN social_description VARCHAR(320)",
            "ALTER TABLE pages ADD COLUMN social_image_id INTEGER "
            "CONSTRAINT fk_pages_social_image_id_media_assets "
            "REFERENCES media_assets (id) ON DELETE SET NULL",
            "ALTER TABLE pages ADD COLUMN lock_version INTEGER DEFAULT '1' NOT NULL",
            "ALTER TABLE pages ADD COLUMN published_snapshot JSON",
            "ALTER TABLE pages ADD COLUMN published_at DATETIME",
            "ALTER TABLE pages ADD COLUMN first_published_at DATETIME",
            "ALTER TABLE pages ADD COLUMN published_by_id INTEGER "
            "CONSTRAINT fk_pages_published_by_id_users REFERENCES users (id) ON DELETE SET NULL",
            "ALTER TABLE pages ADD COLUMN scheduled_at DATETIME",
            "ALTER TABLE pages ADD COLUMN scheduled_revision_id INTEGER",
            "ALTER TABLE pages ADD COLUMN archived_at DATETIME",
            "ALTER TABLE pages ADD COLUMN draft_updated_at DATETIME",
            "ALTER TABLE pages ADD COLUMN updated_by_id INTEGER "
            "CONSTRAINT fk_pages_updated_by_id_users REFERENCES users (id) ON DELETE SET NULL",
        ):
            table, column = statement.split()[2], statement.split()[5]
            if (table, column) not in existing:
                op.execute(statement)
    else:
        op.add_column('navigation_items', sa.Column('visibility', sa.String(length=10), server_default='all', nullable=False))
        op.add_column('page_sections', sa.Column('name', sa.String(length=120), nullable=True))
        op.add_column('page_sections', sa.Column('design', JSON, server_default='{}', nullable=False))
        op.add_column('page_sections', sa.Column('visibility', JSON, server_default='{}', nullable=False))
        op.add_column('page_sections', sa.Column('reusable_section_id', sa.Integer(), nullable=True))
        op.create_foreign_key(op.f('fk_page_sections_reusable_section_id_reusable_sections'), 'page_sections', 'reusable_sections', ['reusable_section_id'], ['id'], ondelete='RESTRICT')
        op.add_column('pages', sa.Column('template', sa.String(length=40), server_default='standard', nullable=False))
        op.add_column('pages', sa.Column('is_system', sa.Boolean(), server_default='0', nullable=False))
        op.add_column('pages', sa.Column('parent_id', sa.Integer(), nullable=True))
        op.add_column('pages', sa.Column('path', sa.String(length=400), nullable=True))
        op.add_column('pages', sa.Column('published_path', sa.String(length=400), nullable=True))
        op.add_column('pages', sa.Column('canonical_url', sa.String(length=500), nullable=True))
        op.add_column('pages', sa.Column('social_title', sa.String(length=200), nullable=True))
        op.add_column('pages', sa.Column('social_description', sa.String(length=320), nullable=True))
        op.add_column('pages', sa.Column('social_image_id', sa.Integer(), nullable=True))
        op.add_column('pages', sa.Column('lock_version', sa.Integer(), server_default='1', nullable=False))
        op.add_column('pages', sa.Column('published_snapshot', JSON, nullable=True))
        op.add_column('pages', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('pages', sa.Column('first_published_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('pages', sa.Column('published_by_id', sa.Integer(), nullable=True))
        op.add_column('pages', sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('pages', sa.Column('scheduled_revision_id', sa.Integer(), nullable=True))
        op.add_column('pages', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('pages', sa.Column('draft_updated_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column('pages', sa.Column('updated_by_id', sa.Integer(), nullable=True))
        op.create_foreign_key(op.f('fk_pages_parent_id_pages'), 'pages', 'pages', ['parent_id'], ['id'], ondelete='SET NULL')
        op.create_foreign_key(op.f('fk_pages_social_image_id_media_assets'), 'pages', 'media_assets', ['social_image_id'], ['id'], ondelete='SET NULL')
        op.create_foreign_key(op.f('fk_pages_published_by_id_users'), 'pages', 'users', ['published_by_id'], ['id'], ondelete='SET NULL')
        op.create_foreign_key(op.f('fk_pages_updated_by_id_users'), 'pages', 'users', ['updated_by_id'], ['id'], ondelete='SET NULL')
    op.create_index('uq_pages_path', 'pages', ['path'], unique=True)
    op.create_index('uq_pages_published_path', 'pages', ['published_path'], unique=True)


def _tables():
    pages = sa.table(
        'pages',
        sa.column('id', sa.Integer), sa.column('slug', sa.String), sa.column('title', sa.String),
        sa.column('status', sa.String), sa.column('template', sa.String),
        sa.column('is_system', sa.Boolean), sa.column('path', sa.String),
        sa.column('published_path', sa.String), sa.column('seo_title', sa.String),
        sa.column('meta_description', sa.String), sa.column('noindex', sa.Boolean),
        sa.column('published_snapshot', JSON), sa.column('published_at', sa.DateTime(timezone=True)),
        sa.column('first_published_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    sections = sa.table(
        'page_sections',
        sa.column('id', sa.Integer), sa.column('page_id', sa.Integer), sa.column('key', sa.String),
        sa.column('section_type', sa.String), sa.column('variant', sa.String),
        sa.column('content', JSON), sa.column('design', JSON), sa.column('visibility', JSON),
        sa.column('name', sa.String), sa.column('is_visible', sa.Boolean),
        sa.column('display_order', sa.Integer),
    )
    revisions = sa.table(
        'page_revisions',
        sa.column('page_id', sa.Integer), sa.column('number', sa.Integer),
        sa.column('kind', sa.String), sa.column('summary', sa.String),
        sa.column('snapshot', JSON), sa.column('created_at', sa.DateTime(timezone=True)),
    )
    return pages, sections, revisions


def _migrate_content():
    bind = op.get_bind()
    pages, sections, revisions = _tables()
    now = datetime.now(UTC)
    for page in bind.execute(sa.select(pages)).mappings().all():
        values = {}
        if page['path'] is None:
            values['path'] = '/' if page['slug'] == 'home' else f"/{page['slug']}"
        if page['slug'] == 'home':
            values.update(template='home', is_system=True)
        if values:
            bind.execute(pages.update().where(pages.c.id == page['id']).values(**values))

    home_ids = set(bind.execute(sa.select(pages.c.id).where(pages.c.slug == 'home')).scalars())
    for row in bind.execute(sa.select(sections)).mappings().all():
        design = _load(row['design'])
        if design:  # already converted
            continue
        content = _load(row['content']) or {}
        stype, key = row['section_type'], row['key']
        legacy = HOME_V1.get(key)
        if (
            row['page_id'] in home_ids
            and legacy
            and legacy['section_type'] == stype
            and legacy['variant'] == row['variant']
            and legacy['content'] == content
            and key in HOME_V2
        ):
            target = HOME_V2[key]
            values = {
                'section_type': target['section_type'],
                'variant': target['variant'],
                'content': copy.deepcopy(target['content']),
                'design': copy.deepcopy(target['design']),
                'name': target['name'],
            }
        elif stype in LEGACY_FIELDS:
            variant, new_content = convert_edited(stype, row['variant'], content)
            design = copy.deepcopy(HOME_V2[key]['design']) if key in HOME_V2 and HOME_V2[key]['section_type'] == stype else copy.deepcopy(TYPE_DESIGN[stype])
            values = {'variant': variant, 'content': new_content, 'design': design,
                      'name': HOME_V2.get(key, {}).get('name')}
        else:
            continue
        values['visibility'] = dict(VISIBILITY)
        bind.execute(sections.update().where(sections.c.id == row['id']).values(**values))

    # Published pages without a snapshot go live exactly as their (converted) sections.
    for page in bind.execute(
        sa.select(pages).where(pages.c.status == 'published', pages.c.published_snapshot.is_(None))
    ).mappings().all():
        rows = bind.execute(
            sa.select(sections).where(sections.c.page_id == page['id']).order_by(sections.c.display_order)
        ).mappings().all()
        path = '/' if page['slug'] == 'home' else f"/{page['slug']}"
        doc = {
            'version': 1,
            'page': {
                'title': page['title'], 'slug': page['slug'], 'path': path,
                'template': 'home' if page['slug'] == 'home' else (page['template'] or 'standard'),
                'parent_id': None, 'seo_title': page['seo_title'],
                'meta_description': page['meta_description'], 'noindex': bool(page['noindex']),
                'canonical_url': None, 'social_title': None, 'social_description': None,
                'social_image_id': None,
            },
            'sections': [
                {
                    'key': r['key'], 'name': r['name'] or '', 'section_type': r['section_type'],
                    'variant': r['variant'], 'content': _load(r['content']) or {},
                    'design': _load(r['design']) or {}, 'visibility': _load(r['visibility']) or dict(VISIBILITY),
                    'is_visible': bool(r['is_visible']), 'reusable_section_id': None,
                }
                for r in rows
            ],
        }
        bind.execute(
            pages.update().where(pages.c.id == page['id']).values(
                published_snapshot=doc, published_path=path, published_at=now,
                first_published_at=page['first_published_at'] or now,
            )
        )
        bind.execute(revisions.insert().values(
            page_id=page['id'], number=1, kind='published', snapshot=doc, created_at=now,
            summary='Migrated from the Batch 03 homepage configuration',
        ))


def _permissions_table():
    return sa.table(
        'permissions',
        sa.column('id', sa.Integer), sa.column('key', sa.String), sa.column('label', sa.String),
        sa.column('description', sa.String), sa.column('group', sa.String),
        sa.column('module', sa.String), sa.column('is_available', sa.Boolean),
        sa.column('is_sensitive', sa.Boolean), sa.column('sort_order', sa.Integer),
    )


def _sync_permissions():
    bind = op.get_bind()
    permissions = _permissions_table()
    roles = sa.table('roles', sa.column('id', sa.Integer), sa.column('name', sa.String),
                     sa.column('grants_all', sa.Boolean))
    links = sa.table('role_permissions', sa.column('role_id', sa.Integer), sa.column('permission_id', sa.Integer))
    existing = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    for order, (key, label, desc, group, module, available, sensitive) in enumerate(PERMISSIONS):
        values = {'label': label, 'description': desc, 'group': group, 'module': module,
                  'is_available': available, 'is_sensitive': sensitive, 'sort_order': order}
        if key in existing:
            bind.execute(permissions.update().where(permissions.c.id == existing[key]).values(**values))
        else:
            bind.execute(permissions.insert().values(key=key, **values))
    perm_ids = dict(bind.execute(sa.select(permissions.c.key, permissions.c.id)).all())
    key_by_id = {v: k for k, v in perm_ids.items()}
    role_rows = bind.execute(sa.select(roles.c.name, roles.c.id, roles.c.grants_all)).all()
    role_ids = {name: rid for name, rid, _ in role_rows}
    current = set(bind.execute(sa.select(links.c.role_id, links.c.permission_id)).all())
    held: dict[int, set[str]] = {}
    for role_id, perm_id in current:
        held.setdefault(role_id, set()).add(key_by_id.get(perm_id))
    wanted: set[tuple[int, int]] = set()
    for role, keys in GRANTS.items():
        if role in role_ids:  # templates deleted by an administrator stay deleted
            wanted |= {(role_ids[role], perm_ids[k]) for k in keys}
    for name, role_id, grants_all in role_rows:
        if grants_all:
            continue
        for source, keys in IMPLIED.items():
            if source in held.get(role_id, set()):
                wanted |= {(role_id, perm_ids[k]) for k in keys}
    rows = [{'role_id': r, 'permission_id': p} for r, p in sorted(wanted - current)]
    if rows:
        op.bulk_insert(links, rows)


def upgrade():
    op.create_table('announcements',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('message', sa.String(length=240), nullable=False),
    sa.Column('cta_label', sa.String(length=60), nullable=True),
    sa.Column('cta_url', sa.String(length=500), nullable=True),
    sa.Column('variant', sa.String(length=20), nullable=False),
    sa.Column('target', sa.String(length=20), nullable=False),
    sa.Column('target_paths', JSON, nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('is_dismissible', sa.Boolean(), nullable=False),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("target IN ('all', 'home', 'paths')", name=op.f('ck_announcements_announcement_target_valid')),
    sa.CheckConstraint("variant IN ('sage', 'gold', 'charcoal', 'ivory')", name=op.f('ck_announcements_announcement_variant_valid')),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_announcements_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_announcements'))
    )
    op.create_table('global_ctas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('label', sa.String(length=60), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('style', sa.String(length=20), nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_global_ctas_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_global_ctas')),
    sa.UniqueConstraint('name', name=op.f('uq_global_ctas_name'))
    )
    op.create_table('reusable_sections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('section_type', sa.String(length=40), nullable=False),
    sa.Column('variant', sa.String(length=40), nullable=False),
    sa.Column('content', JSON, nullable=False),
    sa.Column('design', JSON, nullable=False),
    sa.Column('description', sa.String(length=300), nullable=True),
    sa.Column('lock_version', sa.Integer(), nullable=False),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_reusable_sections_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reusable_sections')),
    sa.UniqueConstraint('name', name=op.f('uq_reusable_sections_name'))
    )
    op.create_table('page_revisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('page_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('summary', sa.String(length=200), nullable=True),
    sa.Column('snapshot', JSON, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_page_revisions_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['page_id'], ['pages.id'], name=op.f('fk_page_revisions_page_id_pages'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_page_revisions')),
    sa.UniqueConstraint('page_id', 'number', name='uq_page_revisions_page_number')
    )
    _add_columns()
    _migrate_content()
    _sync_permissions()


def downgrade():
    bind = op.get_bind()
    permissions = _permissions_table()
    new_ids = [
        r[0] for r in bind.execute(sa.select(permissions.c.id).where(permissions.c.key.in_(NEW_KEYS)))
    ]
    if new_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN :ids")
                     .bindparams(sa.bindparam('ids', expanding=True)), {'ids': new_ids})
        bind.execute(permissions.delete().where(permissions.c.id.in_(new_ids)))
    _, sections, _ = _tables()
    for row in bind.execute(sa.select(sections.c.id, sections.c.section_type, sections.c.variant, sections.c.content)).mappings().all():
        back = {v: k for k, v in VARIANTS.get(row['section_type'], {}).items()}
        bind.execute(sections.update().where(sections.c.id == row['id']).values(
            content=convert_back(row['section_type'], _load(row['content'])),
            variant=back.get(row['variant'], row['variant']),
        ))
    op.drop_index('uq_pages_published_path', table_name='pages')
    op.drop_index('uq_pages_path', table_name='pages')
    page_cols = ('updated_by_id', 'draft_updated_at', 'archived_at', 'scheduled_revision_id',
                 'scheduled_at', 'published_by_id', 'first_published_at', 'published_at',
                 'published_snapshot', 'lock_version', 'social_image_id', 'social_description',
                 'social_title', 'canonical_url', 'published_path', 'path', 'parent_id',
                 'is_system', 'template')
    section_cols = ('reusable_section_id', 'visibility', 'design', 'name')
    op.drop_column('navigation_items', 'visibility')  # plain column: dropped in place on SQLite
    if _is_sqlite():
        # Never rebuild pages/page_sections on SQLite: inside the migration transaction
        # PRAGMA foreign_keys cannot be switched off, so recreating "pages" would
        # cascade-delete every section. Plain columns are dropped in place; the four
        # reference columns (which SQLite cannot drop without a rebuild) stay as unused,
        # nullable columns and are reused if the migration is applied again.
        fk_columns = {'reusable_section_id', 'parent_id', 'social_image_id', 'published_by_id',
                      'updated_by_id'}
        for column in section_cols:
            if column not in fk_columns:
                op.drop_column('page_sections', column)
        for column in page_cols:
            if column not in fk_columns:
                op.drop_column('pages', column)
    else:
        op.drop_constraint(op.f('fk_page_sections_reusable_section_id_reusable_sections'), 'page_sections', type_='foreignkey')
        for column in section_cols:
            op.drop_column('page_sections', column)
        for fk in ('fk_pages_parent_id_pages', 'fk_pages_social_image_id_media_assets',
                   'fk_pages_published_by_id_users', 'fk_pages_updated_by_id_users'):
            op.drop_constraint(op.f(fk), 'pages', type_='foreignkey')
        for column in page_cols:
            op.drop_column('pages', column)
    op.drop_table('page_revisions')
    op.drop_table('reusable_sections')
    op.drop_table('global_ctas')
    op.drop_table('announcements')
