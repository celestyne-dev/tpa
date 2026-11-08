from flask_restful import Resource

from ..extensions import limiter
from ..schemas.content import (
    article_detail_schema,
    article_summaries_schema,
    article_summary_schema,
)
from ..schemas.queries import ArticleListQuerySchema, PageQuerySchema, SearchQuerySchema
from ..services import article_service, page_render, topic_service
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
        related = article_service.related_articles(slug)
        adjacent = article_service.adjacent_articles(slug)
        # The article sidebar (Admin › Article sidebar), never repeating the article or
        # the related articles shown under it.
        sidebar = page_render.public_sidebar(slug, [a["slug"] for a in related])
        return success(
            {
                "article": article_detail_schema.dump(article),
                "related": article_summaries_schema.dump(related),
                "adjacent": {
                    key: article_summary_schema.dump(value) if value else None
                    for key, value in adjacent.items()
                },
                "sidebar": sidebar,
            }
        )


class AuthorDetailResource(Resource):
    """Public author page: only real people with a bio and published articles."""

    def get(self, slug: str):
        args = load_query(PageQuerySchema())
        data = article_service.get_author_page(require_slug(slug, "Author"), page=args["page"])
        return success(
            {"author": data["author"], "articles": article_summaries_schema.dump(data["articles"])},
            {"pagination": data["pagination"]},
        )


class AuthorListResource(Resource):
    def get(self):
        items = [
            {
                "slug": a.slug,
                "name": a.display_name,
                "article_count": count,
                # For the authors index (/authors): the same bio and portrait as the
                # author's own page.
                "bio": a.bio,
                "image": a.profile_image.as_image("avatar") if a.profile_image else None,
            }
            for a, count in article_service.authors_with_pages()
        ]
        return success(items, {"total": len(items)})


class SearchResource(Resource):
    """Published articles only. Rate-limited; queries are capped at 100 characters and
    8 terms, and never logged with the visitor."""

    decorators = [limiter.limit("60 per minute")]

    def get(self):
        args = load_query(SearchQuerySchema())
        data = article_service.search_articles(args["q"], page=args["page"])
        return success(
            {"query": data["query"], "terms": data["terms"],
             "results": article_summaries_schema.dump(data["results"])},
            {"pagination": data["pagination"]},
        )  # fmt: skip
