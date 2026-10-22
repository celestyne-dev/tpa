from app.services import article_service
from app.services.content_repository import LocalContentRepository


def test_reading_time_minimum_and_scaling():
    assert article_service.reading_time([{"type": "paragraph", "text": "Hello"}]) == 1
    words = " ".join(["word"] * 900)
    assert article_service.reading_time([{"type": "paragraph", "text": words}]) == 4
    assert article_service.reading_time([{"type": "list", "items": ["a b", "c"]}]) == 1


def test_sample_content_integrity():
    repo = LocalContentRepository()
    topics = {t["slug"] for t in repo.list_topics()}
    articles = repo.list_articles()
    assert len(topics) == 8 and len(articles) == 6
    assert len({a["slug"] for a in articles}) == len(articles)
    for article in articles:
        assert article["topic_slug"] in topics
        assert set(article.get("secondary_topic_slugs", [])) <= topics
        assert article["source"] == "sample"
    for product in repo.list_products():
        assert set(product["topic_slugs"]) <= topics


def test_repository_returns_copies():
    repo = LocalContentRepository()
    repo.list_articles()[0]["title"] = "mutated"
    assert repo.list_articles()[0]["title"] != "mutated"


def test_repository_can_be_swapped(app):
    class EmptyRepo:
        def list_topics(self):
            return []

        def list_articles(self):
            return []

        def list_products(self):
            return []

    app.extensions["tpa_content_repository"] = EmptyRepo()
    client = app.test_client()
    assert client.get("/api/v1/articles").get_json()["data"] == []
    assert client.get("/api/v1/topics").get_json()["meta"]["total"] == 0
