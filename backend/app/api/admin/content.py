from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import Author, Tag, Topic
from ...schemas.admin import (
    ArticleQuerySchema,
    ArticleWriteSchema,
    AuthorWriteSchema,
    PublishSchema,
    ReassignSchema,
    TagWriteSchema,
    TopicWriteSchema,
)
from ...services import publication_service
from ...services.admin import article_admin, media_admin, taxonomy
from ...services.admin.common import get_or_404
from ...utils.responses import success
from .._validation import load_body, load_query

_article_query = ArticleQuerySchema()
_article_write = ArticleWriteSchema()
_publish = PublishSchema()
_reassign = ReassignSchema()


class ArticleListResource(Resource):
    @require_permission(P.CONTENT_READ)
    def get(self):
        items, pagination = article_admin.list_articles(load_query(_article_query))
        return success(items, {"pagination": pagination, "counts": article_admin.status_counts()})

    @require_permission(P.CONTENT_WRITE)
    def post(self):
        article = article_admin.create_article(load_body(_article_write), current_user)
        db.session.commit()
        return success(article_admin.admin_detail(article), status=201)


class ArticleResource(Resource):
    @require_permission(P.CONTENT_READ)
    def get(self, article_id: int):
        return success(article_admin.admin_detail(article_admin.get_article(article_id)))

    @require_permission(P.CONTENT_WRITE)
    def patch(self, article_id: int):
        article = article_admin.get_article(article_id)
        data = load_body(_article_write, partial=True)
        article_admin.update_article(article, data, current_user)
        db.session.commit()
        return success(article_admin.admin_detail(article))


def _action(name: str, permission: P):
    class ArticleAction(Resource):
        @require_permission(permission)
        def post(self, article_id: int):
            article = article_admin.get_article(article_id)
            if name == "publish":
                article_admin.publish(article, load_body(_publish)["published_at"], current_user)
            else:
                getattr(article_admin, name)(article, current_user)
            db.session.commit()
            return success(article_admin.admin_detail(article))

    ArticleAction.__name__ = f"Article{name.capitalize()}Resource"
    return ArticleAction


ArticlePublishResource = _action("publish", P.CONTENT_PUBLISH)
ArticleUnpublishResource = _action("unpublish", P.CONTENT_MODERATE)
ArticleArchiveResource = _action("archive", P.CONTENT_MODERATE)
ArticleRestoreResource = _action("restore", P.CONTENT_WRITE)


class ArticlePreviewResource(Resource):
    @require_permission(P.CONTENT_READ)
    def get(self, article_id: int):
        return success(article_admin.preview(article_admin.get_article(article_id)))


# ---- taxonomy -----------------------------------------------------------------


def _taxonomy(model, label, schema, list_fn, save_fn, delete_fn, dict_fn, reassign_fn=None):
    write = schema()

    class ListResource(Resource):
        @require_permission(P.CONTENT_READ)
        def get(self):
            items = list_fn()
            return success(items, {"total": len(items)})

        @require_permission(P.TAXONOMY_MANAGE)
        def post(self):
            obj = save_fn(None, load_body(write), current_user)
            db.session.commit()
            return success(dict_fn(obj), status=201)

    class ItemResource(Resource):
        @require_permission(P.CONTENT_READ)
        def get(self, item_id: int):
            return success(dict_fn(get_or_404(model, item_id, label)))

        @require_permission(P.TAXONOMY_MANAGE)
        def patch(self, item_id: int):
            obj = get_or_404(model, item_id, label)
            save_fn(obj, load_body(write, partial=True), current_user)
            db.session.commit()
            return success(dict_fn(obj))

        @require_permission(P.TAXONOMY_MANAGE)
        def delete(self, item_id: int):
            delete_fn(get_or_404(model, item_id, label), current_user)
            db.session.commit()
            return success({"deleted": True})

    class ReassignResource(Resource):
        @require_permission(P.TAXONOMY_MANAGE)
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
    taxonomy.list_tags,
    taxonomy.save_tag,
    taxonomy.delete_tag,
    taxonomy.tag_dict,
)


class MediaListResource(Resource):
    @require_permission(P.CONTENT_READ)
    def get(self):
        items = media_admin.list_media()
        return success(items, {"total": len(items)})


class PublishingStatusResource(Resource):
    @require_permission(P.CONTENT_READ)
    def get(self):
        return success(publication_service.status())
