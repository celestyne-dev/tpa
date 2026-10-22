from flask_restful import Resource

from ..schemas.content import article_detail_schema, article_summaries_schema
from ..schemas.queries import ArticleListQuerySchema
from ..services import article_service, topic_service
from ..utils.responses import success
from ._validation import load_query, require_slug

_query = ArticleListQuerySchema()


class ArticleListResource(Resource):
    def get(self):
        args = load_query(_query)
        if args["topic"]:
            # Unknown topics are a 404 rather than an empty list.
            topic_service.get_topic(args["topic"])
        items, pagination = article_service.list_articles(
            topic=args["topic"],
            featured=args["featured"],
            page=args["page"],
            page_size=args["page_size"],
        )
        meta = {"pagination": pagination}
        if args["topic"]:
            meta["topic"] = args["topic"]
        return success(article_summaries_schema.dump(items), meta)


class ArticleDetailResource(Resource):
    def get(self, slug: str):
        article = article_service.get_article(require_slug(slug, "Article"))
        related = article_service.related_articles(article)
        return success(
            {
                "article": article_detail_schema.dump(article),
                "related": article_summaries_schema.dump(related),
            }
        )
