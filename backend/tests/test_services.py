from datetime import UTC, datetime, timedelta

from app.cms.blocks import validate_blocks
from app.extensions import db
from app.models import Article
from app.services import publication_service
from app.services.content_repository import LocalContentRepository
from app.services.seed_service import seed_sample_content
from app.services.serializers import reading_time


def test_reading_time_minimum_and_scaling():
    assert reading_time([{"type": "paragraph", "text": "Hello"}]) == 1
    assert reading_time([{"type": "paragraph", "text": " ".join(["word"] * 900)}]) == 4
    assert reading_time([{"type": "list", "items": ["a b", "c"]}]) == 1


def test_sample_fixture_integrity():
    repo = LocalContentRepository()
    topics = {t["slug"] for t in repo.list_topics()}
    articles = repo.list_articles()
    assert len(topics) == 8 and len(articles) == 6
    for article in articles:
        assert article["topic_slug"] in topics
        assert article["source"] == "sample"
        validate_blocks(article["body"])  # fixtures satisfy the block rules


def test_seed_is_idempotent_and_preserves_edits(app):
    with app.app_context():
        first = seed_sample_content()
        db.session.commit()
        assert first["articles"] == 6 and first["topics"] == 8
        article = db.session.scalar(
            db.select(Article).where(Article.slug == "building-quiet-confidence")
        )
        article.title = "Edited by the editorial team"
        db.session.commit()
        second = seed_sample_content()
        db.session.commit()
        assert second["articles"] == 0 and second["topics"] == 0
        assert db.session.scalar(db.select(db.func.count(Article.id))) == 6
        db.session.refresh(article)
        assert article.title == "Edited by the editorial team"
        assert article.source == "sample" and article.status == "published"
        assert article.body[0]["type"] == "paragraph"


def test_timestamps_are_timezone_aware(seeded):
    with seeded.app_context():
        article = db.session.scalar(db.select(Article).limit(1))
        assert article.published_at.tzinfo is not None
        assert article.created_at.tzinfo is not None


def test_scheduled_articles_publish_only_via_explicit_task(seeded):
    client = seeded.test_client()
    with seeded.app_context():
        article = db.session.scalar(
            db.select(Article).where(Article.slug == "building-quiet-confidence")
        )
        article.status = "scheduled"
        article.published_at = datetime.now(UTC) - timedelta(minutes=5)  # time already passed
        db.session.commit()
    # Not visible until the publish-due task promotes it.
    assert client.get("/api/v1/articles/building-quiet-confidence").status_code == 404
    with seeded.app_context():
        assert publication_service.publish_due_scheduled() == {
            "published": ["building-quiet-confidence"],
            "failed": [],
            "boundary_rebuild": False,
            "expired_orders": 0,
        }
        db.session.commit()
    assert client.get("/api/v1/articles/building-quiet-confidence").status_code == 200


def test_cli_publish_due_and_seed_commands(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=["seed", "sample-content"])
    assert "articles=6" in result.output
    result = runner.invoke(args=["seed", "sample-content"])
    assert "articles=0" in result.output and "skipped=14" in result.output
    assert "menus=2" in runner.invoke(args=["cms", "seed-defaults"]).output
    assert "menus=0" in runner.invoke(args=["cms", "seed-defaults"]).output
    assert "No scheduled articles" in runner.invoke(args=["content", "publish-due"]).output


def test_sample_seed_refused_in_production_config(app):
    app.config["ALLOW_SAMPLE_SEED"] = False
    result = app.test_cli_runner().invoke(args=["seed", "sample-content"])
    assert result.exit_code != 0 and "not seeded in production" in result.output
