"""Public article queries. Only published articles whose publish time has passed are visible."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select

from ..extensions import db
from ..models import Article, Author, Topic, article_topics
from ..utils.errors import NotFoundError
from .serializers import author_has_page, public_article


def _now() -> datetime:
    return datetime.now(UTC)


def published_filter():
    return (Article.status == "published") & (Article.published_at <= _now())


def _topic_filter(slug: str):
    return or_(
        Article.primary_topic.has(Topic.slug == slug),
        Article.secondary_topics.any(Topic.slug == slug),
    )


def published_topic_counts() -> dict[int, int]:
    """Published article count per topic (primary or secondary, counted once)."""
    pairs: set[tuple[int, int]] = set()
    rows = db.session.execute(
        select(Article.id, Article.primary_topic_id).where(published_filter())
    )
    for article_id, topic_id in rows:
        if topic_id:
            pairs.add((article_id, topic_id))
    secondary = db.session.execute(
        select(article_topics.c.article_id, article_topics.c.topic_id)
        .join(Article, Article.id == article_topics.c.article_id)
        .where(published_filter())
    )
    pairs.update((a, t) for a, t in secondary)
    counts: dict[int, int] = {}
    for _, topic_id in pairs:
        counts[topic_id] = counts.get(topic_id, 0) + 1
    return counts


def list_articles(
    *, topic: str | None = None, featured: bool | None = None, page: int = 1, page_size: int = 12
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    conditions = [published_filter()]
    if topic:
        conditions.append(_topic_filter(topic))
    if featured is not None:
        conditions.append(Article.featured.is_(featured))

    total = db.session.scalar(select(func.count(Article.id)).where(*conditions)) or 0
    stmt = (
        select(Article)
        .where(*conditions)
        .order_by(Article.published_at.desc(), Article.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [public_article(a, include_body=False) for a in db.session.scalars(stmt)]
    total_pages = max(1, math.ceil(total / page_size))
    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
    return items, pagination


def get_article_model(slug: str) -> Article:
    article = db.session.scalar(select(Article).where(Article.slug == slug, published_filter()))
    if article is None:
        raise NotFoundError(f"Article '{slug}' was not found.")
    return article


def get_article(slug: str) -> dict[str, Any]:
    return public_article(get_article_model(slug))


def related_articles(slug: str, limit: int = 3) -> list[dict[str, Any]]:
    """Same primary topic first, then shared secondary topics, then most recent."""
    article = get_article_model(slug)
    own = {t.id for t in article.secondary_topics} | {article.primary_topic_id}
    candidates = db.session.scalars(
        select(Article)
        .where(published_filter(), Article.id != article.id)
        .order_by(Article.published_at.desc(), Article.id.desc())
        .limit(60)
    ).all()

    def score(other: Article) -> int:
        if other.primary_topic_id and other.primary_topic_id == article.primary_topic_id:
            return 2
        theirs = {t.id for t in other.secondary_topics} | {other.primary_topic_id}
        return 1 if own & theirs else 0

    ranked = sorted(candidates, key=score, reverse=True)[:limit]
    return [public_article(a, include_body=False) for a in ranked]


# ---- author pages ---------------------------------------------------------------------------


def authors_with_pages() -> list[tuple[Author, int]]:
    """Authors that get a public page: active, marked as real people, with a bio and at
    least one published article. Returns (author, published article count)."""
    rows = db.session.execute(
        select(Author, func.count(Article.id))
        .join(Article, Article.author_id == Author.id)
        .where(published_filter(), Author.status == "active", Author.is_person.is_(True))
        .group_by(Author.id)
        .order_by(Author.display_name)
    ).all()
    return [(author, count) for author, count in rows if author_has_page(author)]


def get_author_page(slug: str, *, page: int = 1, page_size: int = 12) -> dict[str, Any]:
    author = db.session.scalar(select(Author).where(Author.slug == slug))
    if author is None or not author_has_page(author):
        raise NotFoundError(f"Author '{slug}' was not found.")
    conditions = [published_filter(), Article.author_id == author.id]
    total = db.session.scalar(select(func.count(Article.id)).where(*conditions)) or 0
    if total == 0:
        raise NotFoundError(f"Author '{slug}' was not found.")
    total_pages = max(1, math.ceil(total / page_size))
    stmt = (
        select(Article)
        .where(*conditions)
        .order_by(Article.published_at.desc(), Article.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    portrait = author.profile_image.as_image("avatar") if author.profile_image else None
    return {
        "author": {
            "slug": author.slug,
            "name": author.display_name,
            "bio": author.bio,
            "image": portrait,
            "article_count": total,
        },
        "articles": [public_article(a, include_body=False) for a in db.session.scalars(stmt)],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


# ---- search ---------------------------------------------------------------------------------

SEARCH_MAX_TERMS = 8
SEARCH_MAX_LENGTH = 100


def search_terms(query: str) -> list[str]:
    """Lower-case words and numbers only (no operators reach the database)."""
    import re

    words = re.findall(r"[^\W_]+", (query or "")[:SEARCH_MAX_LENGTH].lower())
    return list(dict.fromkeys(w for w in words if len(w) > 1 or w.isdigit()))[:SEARCH_MAX_TERMS]


def _search_postgres(terms: list[str]):
    """Full-text search, ranked: title (A) over subtitle/excerpt (B) over body text (C).
    Every term may be a prefix ("kind" finds "kindness"), so results appear while typing."""
    from sqlalchemy import literal_column, text

    body_text = func.concat_ws(
        " ",
        func.jsonb_path_query_array(Article.body, text("'lax $[*].text'")).cast(db.Text),
        func.jsonb_path_query_array(
            Article.body, text("'lax $[*].items[*] ? (@.type() == \"string\")'")
        ).cast(db.Text),
        func.jsonb_path_query_array(Article.body, text("'lax $[*].items[*].title'")).cast(db.Text),
    )
    english = literal_column("'english'::regconfig")
    document = (
        func.setweight(func.to_tsvector(english, Article.title), literal_column("'A'"))
        .op("||")(
            func.setweight(
                func.to_tsvector(english, func.concat_ws(" ", Article.subtitle, Article.excerpt)),
                literal_column("'B'"),
            )
        )
        .op("||")(func.setweight(func.to_tsvector(english, body_text), literal_column("'C'")))
    )
    query = func.to_tsquery(english, " & ".join(f"{t}:*" for t in terms))
    rank = func.ts_rank(document, query)
    return document.op("@@")(query), rank


def search_articles(query: str, *, page: int = 1, page_size: int = 10) -> dict[str, Any]:
    """Published articles matching every term. PostgreSQL uses ranked full-text search;
    other databases (local development, tests) fall back to substring matching."""
    terms = search_terms(query)
    empty = {
        "query": query or "",
        "terms": terms,
        "results": [],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 1,
            "has_next": False,
            "has_prev": page > 1,
        },
    }
    if not terms:
        return empty
    if db.engine.dialect.name == "postgresql":
        matches, rank = _search_postgres(terms)
        conditions = [published_filter(), matches]
        total = db.session.scalar(select(func.count(Article.id)).where(*conditions)) or 0
        stmt = (
            select(Article)
            .where(*conditions)
            .order_by(rank.desc(), Article.published_at.desc(), Article.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        found = list(db.session.scalars(stmt))
    else:
        from ..cms.blocks import plain_text

        scored = []
        for article in db.session.scalars(
            select(Article).where(published_filter()).order_by(Article.published_at.desc())
        ):
            title = article.title.lower()
            rest = " ".join(
                [article.subtitle or "", article.excerpt or "", plain_text(article.body or [])]
            ).lower()
            if all(t in title or t in rest for t in terms):
                scored.append((sum(t in title for t in terms), article))
        scored.sort(key=lambda pair: -pair[0])  # stable: newest first within a score
        total = len(scored)
        found = [a for _s, a in scored[(page - 1) * page_size : page * page_size]]
    total_pages = max(1, math.ceil(total / page_size))
    return {
        **empty,
        "results": [public_article(a, include_body=False) for a in found],
        "pagination": {
            **empty["pagination"],
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
        },
    }
