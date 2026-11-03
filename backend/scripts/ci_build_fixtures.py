"""CI build fixtures: enough sample articles for the build to prerender real pagination
(/articles/page/2, /topics/<slug>/page/2) and an author page, so the build validation
can check them.

For throwaway CI and local databases only. It refuses to run unless sample seeding is
allowed (FLASK_CONFIG=development or testing; production always refuses), and it only
adds articles marked as sample content after `flask seed sample-content` ran.

    FLASK_CONFIG=development DATABASE_URL=sqlite:////tmp/ci.db python scripts/ci_build_fixtures.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import create_app  # noqa: E402
from app.cms.blocks import validate_blocks  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Article, Author, Topic  # noqa: E402

FIXTURE_ARTICLES = 20  # with the six samples: 26 articles, three archive pages of 12


def main() -> int:
    app = create_app()
    with app.app_context():
        if not app.config.get("ALLOW_SAMPLE_SEED") or app.config.get("ENV_NAME") == "production":
            print("Refusing: CI fixtures are only for throwaway development/test databases.")
            return 2
        sample = db.session.scalar(select(Article).where(Article.source == "sample"))
        if sample is None:
            print("Run `flask seed sample-content` first.")
            return 2
        topic = sample.primary_topic or db.session.scalar(select(Topic))
        author = sample.author or db.session.scalar(select(Author))
        # A fixture author page: a real-person profile with a bio.
        author.is_person = True
        author.bio = author.bio or "Fixture biography used by the CI build validation."
        start = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        for i in range(FIXTURE_ARTICLES):
            slug = f"ci-fixture-article-{i + 1:02d}"
            if db.session.scalar(select(Article.id).where(Article.slug == slug)):
                continue
            when = start + timedelta(days=i)
            db.session.add(
                Article(
                    title=f"CI fixture article {i + 1:02d}",
                    slug=slug,
                    excerpt=f"Fixture summary {i + 1:02d} for the build validation.",
                    body=validate_blocks(
                        [
                            {"type": "paragraph", "text": "Fixture text with a [link](/articles)."},
                            {
                                "type": "sources",
                                "items": [{"title": "Fixture source", "url": "https://example.org/"}],
                            },
                        ]
                    ),
                    author=author,
                    primary_topic=topic,
                    status="published",
                    published_at=when,
                    first_published_at=when,
                    source="sample",
                    original_slug=slug,
                )
            )
        db.session.commit()
        total = db.session.query(Article).filter(Article.status == "published").count()
        print(f"CI fixtures ready: {total} published articles; author page for {author.slug}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
