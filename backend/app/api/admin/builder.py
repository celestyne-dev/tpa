"""Admin API for the homepage and page builder, shared sections, CTAs and announcements.

Decorators check the broad permission; the services then check the permission
for the specific page (homepage.* for the homepage, pages.* for other pages).
"""

from flask_jwt_extended import current_user
from flask_restful import Resource
from sqlalchemy import func, or_, select

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...auth.rbac import effective_permissions
from ...cms.routing import OVERRIDABLE_PATHS
from ...extensions import db
from ...models import Article, Page, Topic
from ...schemas.admin import (
    AnnouncementSchema,
    CtaSchema,
    LinkOptionsQuerySchema,
    LockSchema,
    PageCreateSchema,
    PageDraftSchema,
    PagePreviewSchema,
    PageQuerySchema,
    PageScheduleSchema,
    PageSlugCheckSchema,
    PageWriteSchema,
    ReorderSchema,
    SectionCreateSchema,
    SectionWriteSchema,
    SharedSectionSchema,
    ShareSectionSchema,
)
from ...services import page_render, seo_service
from ...services.admin import announcement_admin, page_admin, shared_admin
from ...utils.errors import ForbiddenError
from ...utils.responses import success
from .._validation import load_body, load_query

ANY_PAGE_VIEW = (P.PAGES_VIEW, P.HOMEPAGE_VIEW)
ANY_PAGE_EDIT = (P.PAGES_EDIT, P.HOMEPAGE_EDIT)


def _page_for(page_id: int, action: str = "view"):
    page = page_admin.get_page(page_id)
    page_admin.require(page, current_user, action)
    return page


def _detail(page):
    return success(page_admin.page_detail(page, current_user))


# ---- pages ----------------------------------------------------------------------------------


class PageListResource(Resource):
    @require_permission(P.PAGES_VIEW)
    def get(self):
        args = load_query(PageQuerySchema())
        perms = effective_permissions(current_user)
        args["exclude_home"] = P.HOMEPAGE_VIEW.value not in perms
        pages = page_admin.list_pages(args)
        return success(pages, {"total": len(pages)})

    @require_permission(P.PAGES_CREATE)
    def post(self):
        page = page_admin.create_page(load_body(PageCreateSchema()), current_user)
        db.session.commit()
        return success(page_admin.page_detail(page, current_user), status=201)


class HomepageResource(Resource):
    @require_permission(P.HOMEPAGE_VIEW)
    def get(self):
        page = page_admin.ensure_home(current_user)
        db.session.commit()
        return _detail(page)


class PageResource(Resource):
    @require_any_permission(*ANY_PAGE_VIEW)
    def get(self, page_id: int):
        return _detail(_page_for(page_id))

    @require_any_permission(*ANY_PAGE_EDIT)
    def patch(self, page_id: int):
        """Batch 02 page settings endpoint (title, SEO fields, status)."""
        page = _page_for(page_id, "edit")
        page_admin.update_page(page, load_body(PageWriteSchema(), partial=True), current_user)
        db.session.commit()
        return success(page_admin.page_dict(page, with_sections=True))


class PageDraftResource(Resource):
    @require_any_permission(*ANY_PAGE_EDIT)
    def put(self, page_id: int):
        page = _page_for(page_id, "edit")
        page_admin.save_draft(page, load_body(PageDraftSchema()), current_user)
        db.session.commit()
        return _detail(page)


class PagePublishResource(Resource):
    @require_any_permission(P.PAGES_PUBLISH, P.HOMEPAGE_PUBLISH)
    def post(self, page_id: int):
        page = _page_for(page_id, "publish")
        page_admin.publish(page, current_user, load_body(LockSchema())["lock_version"])
        db.session.commit()
        return _detail(page)


class PageScheduleResource(Resource):
    @require_any_permission(P.PAGES_PUBLISH, P.HOMEPAGE_PUBLISH)
    def post(self, page_id: int):
        page = _page_for(page_id, "publish")
        data = load_body(PageScheduleSchema())
        page_admin.schedule(page, data["scheduled_at"], current_user, data["lock_version"])
        db.session.commit()
        return _detail(page)

    @require_any_permission(P.PAGES_PUBLISH, P.HOMEPAGE_PUBLISH)
    def delete(self, page_id: int):
        page = _page_for(page_id, "publish")
        page_admin.unschedule(page, current_user)
        db.session.commit()
        return _detail(page)


class _PageAction(Resource):
    action = ""
    handler = None

    def _run(self, page_id: int):
        page = page_admin.get_page(page_id)
        type(self).handler(page, current_user)
        db.session.commit()
        return _detail(page)


class PageUnpublishResource(_PageAction):
    handler = staticmethod(page_admin.unpublish)

    @require_permission(P.PAGES_PUBLISH)
    def post(self, page_id: int):
        return self._run(page_id)


class PageArchiveResource(_PageAction):
    handler = staticmethod(page_admin.archive)

    @require_permission(P.PAGES_PUBLISH)
    def post(self, page_id: int):
        return self._run(page_id)


class PageRestoreResource(_PageAction):
    handler = staticmethod(page_admin.restore)

    @require_permission(P.PAGES_PUBLISH)
    def post(self, page_id: int):
        return self._run(page_id)


class PageDiscardResource(_PageAction):
    handler = staticmethod(page_admin.discard_draft)

    @require_any_permission(*ANY_PAGE_EDIT)
    def post(self, page_id: int):
        return self._run(page_id)


class PageDuplicateResource(Resource):
    @require_permission(P.PAGES_CREATE)
    def post(self, page_id: int):
        page = _page_for(page_id)
        copy = page_admin.duplicate(page, current_user)
        db.session.commit()
        return success(page_admin.page_detail(copy, current_user), status=201)


class PagePreviewResource(Resource):
    """Private draft preview (admin responses are never cached or indexed)."""

    @require_any_permission(*ANY_PAGE_VIEW)
    def get(self, page_id: int):
        return success(page_admin.preview(_page_for(page_id), None))

    @require_any_permission(*ANY_PAGE_VIEW)
    def post(self, page_id: int):
        data = load_body(PagePreviewSchema())
        result = page_admin.preview(_page_for(page_id), data)
        db.session.rollback()  # previews never write
        return success(result)


class PageSeoChecksResource(Resource):
    @require_any_permission(*ANY_PAGE_VIEW)
    def get(self, page_id: int):
        page = _page_for(page_id)
        doc = page_render.draft_document(page)
        return success(
            {"checks": seo_service.check_page_document(doc, is_home=page.slug == "home")}
        )


class PageRevisionListResource(Resource):
    @require_any_permission(*ANY_PAGE_VIEW)
    def get(self, page_id: int):
        page = _page_for(page_id)
        items = page_admin.list_revisions(page)
        return success(items, {"total": len(items)})


class PageRevisionResource(Resource):
    @require_any_permission(*ANY_PAGE_VIEW)
    def get(self, page_id: int, revision_id: int):
        page = _page_for(page_id)
        revision = page_admin.get_revision(page, revision_id)
        return success(page_admin.revision_dict(revision, with_snapshot=True))


class PageRevisionRestoreResource(Resource):
    @require_any_permission(*ANY_PAGE_EDIT)
    def post(self, page_id: int, revision_id: int):
        page = _page_for(page_id, "edit")
        revision = page_admin.get_revision(page, revision_id)
        page_admin.restore_revision(
            page, revision, current_user, load_body(LockSchema())["lock_version"]
        )
        db.session.commit()
        return _detail(page)


class PageSlugCheckResource(Resource):
    @require_any_permission(P.PAGES_EDIT, P.PAGES_CREATE)
    def get(self):
        args = load_query(PageSlugCheckSchema())
        return success(page_admin.slug_check(args["slug"], args["parent_id"], args["exclude"]))


class PageTemplatesResource(Resource):
    @require_any_permission(*ANY_PAGE_VIEW)
    def get(self):
        return success(page_admin.templates())


class SectionTypesResource(Resource):
    @require_any_permission(*ANY_PAGE_VIEW, P.REUSABLE_SECTIONS_MANAGE)
    def get(self):
        return success(page_admin.section_types())


# Batch 02 section endpoints (they edit the draft and respect the same permissions).


class PageSectionListResource(Resource):
    @require_any_permission(*ANY_PAGE_EDIT)
    def post(self, page_id: int):
        page = _page_for(page_id, "edit")
        section = page_admin.create_section(page, load_body(SectionCreateSchema()), current_user)
        db.session.commit()
        return success(page_admin.section_dict(section), status=201)


class PageSectionResource(Resource):
    @require_any_permission(*ANY_PAGE_EDIT)
    def patch(self, page_id: int, section_id: int):
        page = _page_for(page_id, "edit")
        section = page_admin.get_section(page, section_id)
        page_admin.update_section(
            section, load_body(SectionWriteSchema(), partial=True), current_user
        )
        db.session.commit()
        return success(page_admin.section_dict(section))


class PageSectionOrderResource(Resource):
    @require_any_permission(*ANY_PAGE_EDIT)
    def put(self, page_id: int):
        page = _page_for(page_id, "edit")
        page_admin.reorder_sections(page, load_body(ReorderSchema())["order"], current_user)
        db.session.commit()
        return success(page_admin.page_dict(page, with_sections=True))


class PageSectionShareResource(Resource):
    @require_permission(P.REUSABLE_SECTIONS_MANAGE)
    def post(self, page_id: int, section_id: int):
        page = _page_for(page_id, "edit")
        section = page_admin.get_section(page, section_id)
        if section.reusable_section_id:
            raise ForbiddenError("This section is already shared.")
        shared = shared_admin.create_from_section(
            section, load_body(ShareSectionSchema())["name"], current_user
        )
        db.session.commit()
        return success(shared_admin.reusable_dict(shared), status=201)


# ---- pickers -------------------------------------------------------------------------------------


class BuilderOptionsResource(Resource):
    """Published articles, active topics and authors for section pickers (ids and titles only)."""

    @require_any_permission(*ANY_PAGE_EDIT, P.REUSABLE_SECTIONS_MANAGE)
    def get(self):
        from ...models import Author
        from ...services.article_service import published_filter

        articles = db.session.scalars(
            select(Article).where(published_filter()).order_by(Article.published_at.desc())
        )
        topics = db.session.scalars(
            select(Topic).where(Topic.status == "active").order_by(Topic.display_order, Topic.name)
        )
        authors = db.session.scalars(
            select(Author).where(Author.status == "active").order_by(Author.display_name)
        )
        from ...models import AdPlacement, AffiliateLink, Product, ProductCollection
        from ...services.newsletter.lead_magnets import options as lead_magnet_options

        products = db.session.scalars(
            select(Product).where(Product.status != "archived").order_by(Product.title)
        )
        collections = db.session.scalars(select(ProductCollection).order_by(ProductCollection.name))
        return success(
            {
                "products": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "status": p.status,
                        "type": p.product_type,
                        "note": None if p.status == "published" else "Not published (hidden)",
                    }
                    for p in products
                ],
                "product_collections": [
                    {"id": c.id, "name": c.name, "slug": c.slug, "active": c.is_active}
                    for c in collections
                ],
                "articles": [{"id": a.id, "title": a.title, "slug": a.slug} for a in articles],
                "topics": [
                    {"id": t.id, "name": t.name, "slug": t.slug, "featured": t.featured}
                    for t in topics
                ],
                "authors": [{"id": a.id, "name": a.display_name} for a in authors],
                "lead_magnets": lead_magnet_options(),
                "ad_placements": [
                    {"key": p.key, "name": p.name, "active": p.is_active}
                    for p in db.session.scalars(select(AdPlacement).order_by(AdPlacement.name))
                ],
                "affiliate_links": [
                    {
                        "id": link.id,
                        "name": link.name,
                        "merchant": link.merchant,
                        "active": link.is_active,
                    }
                    for link in db.session.scalars(
                        select(AffiliateLink).order_by(AffiliateLink.name)
                    )
                ],
            }
        )


# ---- link picker -------------------------------------------------------------------------------


class LinkOptionsResource(Resource):
    @require_any_permission(
        *ANY_PAGE_EDIT,
        P.NAVIGATION_MANAGE,
        P.REUSABLE_SECTIONS_MANAGE,
        P.ANNOUNCEMENTS_MANAGE,
        P.SETTINGS_MANAGE,
    )
    def get(self):
        q = load_query(LinkOptionsQuerySchema())["q"].strip().lower()
        overridden = set(
            db.session.scalars(select(Page.published_path).where(Page.status == "published"))
        )

        def match(*values):
            return not q or any(q in (v or "").lower() for v in values)

        builtin = [
            {"label": label, "url": path, "group": "Website pages"}
            for path, label in seo_service_static_labels().items()
            if match(label, path) and not (path in OVERRIDABLE_PATHS and path in overridden)
        ]
        pages = [
            {
                "label": p.title,
                "url": p.published_path or p.path,
                "group": "CMS pages",
                "note": None if p.status == "published" else "Not published yet",
            }
            for p in db.session.scalars(
                select(Page)
                .where(Page.status != "archived", Page.slug != "home")
                .order_by(Page.title)
            )
            if match(p.title, p.path)
        ]
        topics = [
            {"label": t.name, "url": f"/topics/{t.slug}", "group": "Topics"}
            for t in db.session.scalars(
                select(Topic).where(Topic.status == "active").order_by(Topic.name)
            )
            if match(t.name, t.slug)
        ]
        stmt = select(Article).where(Article.status == "published")
        if q:
            stmt = stmt.where(
                or_(func.lower(Article.title).like(f"%{q}%"), Article.slug.like(f"%{q}%"))
            )
        articles = [
            {"label": a.title, "url": f"/articles/{a.slug}", "group": "Articles"}
            for a in db.session.scalars(stmt.order_by(Article.published_at.desc()).limit(20))
        ]
        from ...models import Product, ProductCollection

        products = [
            {"label": p.title, "url": f"/shop/{p.published_slug}", "group": "Shop products"}
            for p in db.session.scalars(
                select(Product).where(Product.status == "published").order_by(Product.title)
            )
            if p.published_slug and match(p.title, p.published_slug)
        ]
        collections = [
            {"label": c.name, "url": f"/shop/collections/{c.slug}", "group": "Shop collections"}
            for c in db.session.scalars(
                select(ProductCollection)
                .where(ProductCollection.is_active.is_(True))
                .order_by(ProductCollection.name)
            )
            if match(c.name, c.slug)
        ]
        return success(builtin + pages + topics + articles + products + collections)


def seo_service_static_labels() -> dict[str, str]:
    labels = {
        "/": "Home",
        "/articles": "Articles",
        "/shop": "Shop",
        "/free-resources": "Free Resources",
        "/resources": "Resource Library",
        "/courses": "Courses",
        "/membership": "Membership",
        "/newsletter": "Newsletter",
        "/partner-with-us": "Partner With Us",
        "/advertise": "Advertise (media kit)",
        "/about": "About",
        "/contact": "Contact",
        "/privacy-policy": "Privacy Policy",
        "/terms": "Terms of Use",
        "/affiliate-disclosure": "Affiliate Disclosure",
    }
    return {path: labels.get(path, path) for path, _, _ in seo_service.STATIC_PATHS}


# ---- shared sections and CTAs ----------------------------------------------------------------


SHARED_READ = (*ANY_PAGE_EDIT, P.REUSABLE_SECTIONS_MANAGE)


class SharedSectionListResource(Resource):
    @require_any_permission(*SHARED_READ)
    def get(self):
        items = shared_admin.list_reusable()
        return success(items, {"total": len(items)})

    @require_permission(P.REUSABLE_SECTIONS_MANAGE)
    def post(self):
        shared = shared_admin.create_reusable(load_body(SharedSectionSchema()), current_user)
        db.session.commit()
        return success(shared_admin.reusable_dict(shared), status=201)


class SharedSectionResource(Resource):
    @require_any_permission(*SHARED_READ)
    def get(self, shared_id: int):
        return success(shared_admin.reusable_dict(shared_admin.get_reusable(shared_id)))

    @require_permission(P.REUSABLE_SECTIONS_MANAGE)
    def put(self, shared_id: int):
        shared = shared_admin.get_reusable(shared_id)
        result = shared_admin.update_reusable(
            shared, load_body(SharedSectionSchema(), partial=True), current_user
        )
        db.session.commit()
        return success({**shared_admin.reusable_dict(shared), **result})

    @require_permission(P.REUSABLE_SECTIONS_MANAGE)
    def delete(self, shared_id: int):
        shared_admin.delete_reusable(shared_admin.get_reusable(shared_id), current_user)
        db.session.commit()
        return success({"deleted": True})


class CtaListResource(Resource):
    @require_any_permission(*SHARED_READ)
    def get(self):
        items = shared_admin.list_ctas()
        return success(items, {"total": len(items)})

    @require_permission(P.REUSABLE_SECTIONS_MANAGE)
    def post(self):
        cta = shared_admin.create_cta(load_body(CtaSchema()), current_user)
        db.session.commit()
        return success(shared_admin.cta_dict(cta), status=201)


class CtaResource(Resource):
    @require_permission(P.REUSABLE_SECTIONS_MANAGE)
    def patch(self, cta_id: int):
        cta = shared_admin.get_cta(cta_id)
        shared_admin.update_cta(cta, load_body(CtaSchema(), partial=True), current_user)
        db.session.commit()
        return success(shared_admin.cta_dict(cta))

    @require_permission(P.REUSABLE_SECTIONS_MANAGE)
    def delete(self, cta_id: int):
        shared_admin.delete_cta(shared_admin.get_cta(cta_id), current_user)
        db.session.commit()
        return success({"deleted": True})


# ---- announcements -----------------------------------------------------------------------------


class AnnouncementListResource(Resource):
    @require_permission(P.ANNOUNCEMENTS_MANAGE)
    def get(self):
        items = announcement_admin.list_announcements()
        return success(items, {"total": len(items)})

    @require_permission(P.ANNOUNCEMENTS_MANAGE)
    def post(self):
        a = announcement_admin.create_announcement(load_body(AnnouncementSchema()), current_user)
        db.session.commit()
        return success(announcement_admin.announcement_dict(a), status=201)


class AnnouncementResource(Resource):
    @require_permission(P.ANNOUNCEMENTS_MANAGE)
    def patch(self, announcement_id: int):
        a = announcement_admin.get_announcement(announcement_id)
        announcement_admin.update_announcement(
            a, load_body(AnnouncementSchema(), partial=True), current_user
        )
        db.session.commit()
        return success(announcement_admin.announcement_dict(a))

    @require_permission(P.ANNOUNCEMENTS_MANAGE)
    def delete(self, announcement_id: int):
        announcement_admin.delete_announcement(
            announcement_admin.get_announcement(announcement_id), current_user
        )
        db.session.commit()
        return success({"deleted": True})


class AnnouncementOrderResource(Resource):
    @require_permission(P.ANNOUNCEMENTS_MANAGE)
    def put(self):
        announcement_admin.reorder(load_body(ReorderSchema())["order"], current_user)
        db.session.commit()
        return success(announcement_admin.list_announcements())
