from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import Author, Tag, Topic
from ...schemas.admin import (
    ArticleQuerySchema,
    ArticleSaveSchema,
    ArticleWriteSchema,
    AuthorWriteSchema,
    LockSchema,
    PublishSchema,
    ReassignSchema,
    RevisionCompareSchema,
    SlugCheckSchema,
    TagWriteSchema,
    TopicWriteSchema,
)
from ...services import seo_service
from ...services.admin import article_admin, revisions, taxonomy
from ...services.admin.common import get_or_404
from ...utils.responses import success
from .._validation import load_body, load_query

_article_query = ArticleQuerySchema()
_article_write = ArticleWriteSchema()
_publish = PublishSchema()
_reassign = ReassignSchema()


# Anyone who can work with articles may open the list; it is scoped to their own
# articles unless they also hold articles.view.
ARTICLE_ACCESS = (P.ARTICLES_VIEW, P.ARTICLES_CREATE, P.ARTICLES_EDIT_OWN, P.ARTICLES_EDIT_ANY)


class ArticleListResource(Resource):
    @require_any_permission(*ARTICLE_ACCESS)
    def get(self):
        items, pagination = article_admin.list_articles(load_query(_article_query), current_user)
        return success(
            items,
            {"pagination": pagination, "counts": article_admin.status_counts(current_user)},
        )

    @require_permission(P.ARTICLES_CREATE)
    def post(self):
        article = article_admin.create_article(load_body(_article_write), current_user)
        db.session.commit()
        return success(article_admin.admin_detail(article, current_user), status=201)


class ArticleResource(Resource):
    @require_any_permission(*ARTICLE_ACCESS)
    def get(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        return success(article_admin.admin_detail(article, current_user))

    @require_any_permission(P.ARTICLES_EDIT_OWN, P.ARTICLES_EDIT_ANY)
    def patch(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        data = load_body(ArticleSaveSchema(), partial=True)
        mode = data.pop("mode", "save")
        lock_version = data.pop("lock_version", None)
        summary = data.pop("change_summary", None)
        result = article_admin.update_article(
            article,
            data,
            current_user,
            mode=mode,
            lock_version=lock_version,
            summary=summary,
        )
        db.session.commit()
        return success(article_admin.admin_detail(article, current_user), {"save_result": result})

    @require_permission(P.ARTICLES_DELETE)
    def delete(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        article_admin.delete_article(article, current_user)
        db.session.commit()
        return success({"deleted": True})


def _action(name: str, permission: P):
    class ArticleAction(Resource):
        @require_permission(permission)
        def post(self, article_id: int):
            article = article_admin.get_article_for(article_id, current_user)
            if name == "publish":
                article_admin.publish(article, load_body(_publish)["published_at"], current_user)
            else:
                getattr(article_admin, name)(article, current_user)
            db.session.commit()
            return success(article_admin.admin_detail(article, current_user))

    ArticleAction.__name__ = f"Article{name.title().replace('_', '')}Resource"
    return ArticleAction


ArticlePublishResource = _action("publish", P.ARTICLES_PUBLISH)
ArticleUnpublishResource = _action("unpublish", P.ARTICLES_UNPUBLISH)
ArticleArchiveResource = _action("archive", P.ARTICLES_ARCHIVE)
ArticleRestoreResource = _action("restore", P.ARTICLES_ARCHIVE)
ArticleSubmitResource = _action("submit_for_review", P.ARTICLES_SUBMIT_REVIEW)
ArticleApproveResource = _action("approve", P.ARTICLES_APPROVE)


class ArticlePreviewResource(Resource):
    """Private preview of the working copy (admin responses are no-store and noindex)."""

    @require_permission(P.ARTICLES_PREVIEW)
    def get(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        return success(article_admin.preview_article(article))


class ArticlePublishChangesResource(Resource):
    @require_permission(P.ARTICLES_PUBLISH)
    def post(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        article_admin.publish_changes(
            article, current_user, load_body(LockSchema())["lock_version"]
        )
        db.session.commit()
        return success(article_admin.admin_detail(article, current_user))


class ArticleDiscardChangesResource(Resource):
    @require_any_permission(P.ARTICLES_EDIT_OWN, P.ARTICLES_EDIT_ANY)
    def post(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        article_admin.discard_changes(article, current_user)
        db.session.commit()
        return success(article_admin.admin_detail(article, current_user))


class ArticleRevisionListResource(Resource):
    @require_permission(P.ARTICLES_VIEW_REVISIONS)
    def get(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        items = revisions.list_for(article)
        return success(items, {"total": len(items)})


class ArticleRevisionResource(Resource):
    @require_permission(P.ARTICLES_VIEW_REVISIONS)
    def get(self, article_id: int, revision_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        revision = revisions.get(article, revision_id)
        return success({**revisions.revision_summary(revision), "snapshot": revision.snapshot})


class ArticleRevisionCompareResource(Resource):
    @require_permission(P.ARTICLES_VIEW_REVISIONS)
    def get(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        args = load_query(RevisionCompareSchema())
        a = revisions.get(article, args["from_id"])
        b = revisions.get(article, args["to_id"])
        if a.number > b.number:
            a, b = b, a
        return success(revisions.compare(a, b))


class ArticleRevisionRestoreResource(Resource):
    @require_permission(P.ARTICLES_RESTORE_REVISIONS)
    def post(self, article_id: int, revision_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        result = article_admin.restore_revision(
            article, revision_id, current_user, load_body(LockSchema())["lock_version"]
        )
        db.session.commit()
        return success(article_admin.admin_detail(article, current_user), {"save_result": result})


class ArticleSeoChecksResource(Resource):
    @require_any_permission(*ARTICLE_ACCESS, P.SEO_VIEW)
    def get(self, article_id: int):
        article = article_admin.get_article_for(article_id, current_user)
        return success(seo_service.check_article(article))


class ArticleSlugCheckResource(Resource):
    @require_any_permission(*ARTICLE_ACCESS)
    def get(self):
        args = load_query(SlugCheckSchema())
        return success(seo_service.slug_status(args["slug"], args["exclude"]))


# ---- taxonomy -----------------------------------------------------------------


# Taxonomy is readable by anyone working on articles (editor pickers need it).
TAXONOMY_READ = (*ARTICLE_ACCESS, P.TOPICS_MANAGE, P.TAGS_MANAGE, P.AUTHORS_MANAGE)


def _taxonomy(model, label, schema, manage, list_fn, save_fn, delete_fn, dict_fn, reassign_fn=None):
    write = schema()

    class ListResource(Resource):
        @require_any_permission(*TAXONOMY_READ)
        def get(self):
            items = list_fn()
            return success(items, {"total": len(items)})

        @require_permission(manage)
        def post(self):
            obj = save_fn(None, load_body(write), current_user)
            db.session.commit()
            return success(dict_fn(obj), status=201)

    class ItemResource(Resource):
        @require_any_permission(*TAXONOMY_READ)
        def get(self, item_id: int):
            return success(dict_fn(get_or_404(model, item_id, label)))

        @require_permission(manage)
        def patch(self, item_id: int):
            obj = get_or_404(model, item_id, label)
            save_fn(obj, load_body(write, partial=True), current_user)
            db.session.commit()
            return success(dict_fn(obj))

        @require_permission(manage)
        def delete(self, item_id: int):
            delete_fn(get_or_404(model, item_id, label), current_user)
            db.session.commit()
            return success({"deleted": True})

    class ReassignResource(Resource):
        @require_permission(manage)
        def post(self, item_id: int):
            obj = get_or_404(model, item_id, label)
            moved = reassign_fn(obj, load_body(_reassign)["target_id"], current_user)
            db.session.commit()
            return success({"moved": moved, "item": dict_fn(obj)})

    for cls, suffix in ((ListResource, "List"), (ItemResource, ""), (ReassignResource, "Reassign")):
        cls.__name__ = f"{model.__name__}{suffix}Resource"
    return ListResource, ItemResource, ReassignResource


TopicListResource, TopicResource, TopicReassignResource = _taxonomy(
    Topic,
    "Topic",
    TopicWriteSchema,
    P.TOPICS_MANAGE,
    taxonomy.list_topics,
    taxonomy.save_topic,
    taxonomy.delete_topic,
    taxonomy.topic_dict,
    taxonomy.reassign_topic,
)
AuthorListResource, AuthorResource, AuthorReassignResource = _taxonomy(
    Author,
    "Author",
    AuthorWriteSchema,
    P.AUTHORS_MANAGE,
    taxonomy.list_authors,
    taxonomy.save_author,
    taxonomy.delete_author,
    taxonomy.author_dict,
    taxonomy.reassign_author,
)
TagListResource, TagResource, _ = _taxonomy(
    Tag,
    "Tag",
    TagWriteSchema,
    P.TAGS_MANAGE,
    taxonomy.list_tags,
    taxonomy.save_tag,
    taxonomy.delete_tag,
    taxonomy.tag_dict,
)
