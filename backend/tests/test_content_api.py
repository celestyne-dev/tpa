def _data(res):
    return res.get_json()["data"]


# ---- site -------------------------------------------------------------


def test_site_settings(client):
    res = client.get("/api/v1/site")
    assert res.status_code == 200
    site = _data(res)
    assert site["name"] == "Think Positive Always"
    assert site["community"]["linkedin_followers_label"] == "280,000+"
    assert site["newsletter"] == {
        "name": "The Positive Reset",
        "cadence": "weekly",
        "is_open": False,
    }
    # Nothing configured in testing: no invented contact details or social URLs.
    assert site["contact"] == {"email": None, "partnerships_email": None}
    assert site["social_links"] == []


def test_site_settings_only_exposes_https_social_links(app):
    app.config["SOCIAL_LINKS"] = {"linkedin": "https://www.linkedin.com/x", "x": "http://insecure"}
    app.config["CONTACT_EMAIL"] = "hello@example.org"
    site = _data(app.test_client().get("/api/v1/site"))
    assert [s["platform"] for s in site["social_links"]] == ["linkedin"]
    assert site["contact"]["partnerships_email"] == "hello@example.org"


# ---- topics -----------------------------------------------------------


def test_topic_list(client):
    res = client.get("/api/v1/topics")
    body = res.get_json()
    assert res.status_code == 200
    assert body["meta"]["total"] == 8 == len(body["data"])
    first = body["data"][0]
    assert {"slug", "name", "description", "intro", "icon", "featured", "article_count"} <= set(
        first
    )


def test_topic_list_featured_filter(client):
    topics = _data(client.get("/api/v1/topics?featured=true"))
    assert len(topics) == 6 and all(t["featured"] for t in topics)


def test_topic_list_invalid_filter(client):
    res = client.get("/api/v1/topics?featured=maybe")
    assert res.status_code == 400
    assert "featured" in res.get_json()["error"]["details"]


def test_topic_detail(client):
    topic = _data(client.get("/api/v1/topics/positive-mindset"))
    assert topic["name"] == "Positive Mindset"
    assert topic["article_count"] >= 1


def test_topic_detail_not_found(client):
    for slug in ["unknown-topic", "Bad_Slug"]:
        res = client.get(f"/api/v1/topics/{slug}")
        assert res.status_code == 404
        assert res.get_json()["error"]["code"] == "not_found"


# ---- articles ---------------------------------------------------------


def test_article_list_defaults(client):
    body = client.get("/api/v1/articles").get_json()
    assert len(body["data"]) == 6
    assert body["meta"]["pagination"] == {
        "page": 1,
        "page_size": 12,
        "total": 6,
        "total_pages": 1,
        "has_next": False,
        "has_prev": False,
    }
    dates = [a["published_at"] for a in body["data"]]
    assert dates == sorted(dates, reverse=True)
    summary = body["data"][0]
    assert "body" not in summary
    assert summary["topic"]["name"]
    assert summary["reading_time_minutes"] >= 1
    assert summary["image"]["alt"]


def test_article_pagination(client):
    page1 = client.get("/api/v1/articles?page_size=4").get_json()
    page2 = client.get("/api/v1/articles?page_size=4&page=2").get_json()
    assert len(page1["data"]) == 4 and len(page2["data"]) == 2
    assert page1["meta"]["pagination"]["has_next"] is True
    assert page2["meta"]["pagination"]["has_prev"] is True
    assert not {a["slug"] for a in page1["data"]} & {a["slug"] for a in page2["data"]}


def test_article_page_beyond_range_is_empty(client):
    body = client.get("/api/v1/articles?page=9").get_json()
    assert body["data"] == [] and body["meta"]["pagination"]["total_pages"] == 1


def test_article_topic_filter_includes_secondary_topics(client):
    body = client.get("/api/v1/articles?topic=emotional-well-being").get_json()
    assert body["meta"]["topic"] == "emotional-well-being"
    assert body["data"]
    for article in body["data"]:
        assert "emotional-well-being" in [article["topic_slug"], *article["secondary_topic_slugs"]]


def test_article_featured_filter(client):
    articles = _data(client.get("/api/v1/articles?featured=true"))
    assert len(articles) == 5 and all(a["featured"] for a in articles)


def test_article_list_unknown_topic(client):
    assert client.get("/api/v1/articles?topic=not-a-topic").status_code == 404


def test_article_list_validation(client):
    for query in ["page=0", "page=abc", "page_size=500", "topic=Bad Slug"]:
        res = client.get(f"/api/v1/articles?{query}")
        assert res.status_code == 400, query
        assert res.get_json()["error"]["code"] == "validation_error"


def test_article_detail(client):
    res = client.get("/api/v1/articles/building-quiet-confidence")
    assert res.status_code == 200
    data = _data(res)
    article = data["article"]
    assert article["title"] == "Building Quiet Confidence That Does Not Need Applause"
    assert article["source"] == "sample"
    assert article["body"][0]["type"] == "paragraph"
    assert article["topic"] == {"slug": "confidence-self-worth", "name": "Confidence & Self-Worth"}
    assert article["canonical_url"] is None
    assert len(data["related"]) == 3
    assert article["slug"] not in [r["slug"] for r in data["related"]]


def test_article_detail_not_found(client):
    res = client.get("/api/v1/articles/no-such-article")
    assert res.status_code == 404
    assert res.get_json() == {
        "error": {"code": "not_found", "message": "Article 'no-such-article' was not found."}
    }


# ---- products ---------------------------------------------------------


def test_product_list(client):
    body = client.get("/api/v1/products").get_json()
    assert body["meta"]["total"] == 4
    titles = [p["title"] for p in body["data"]]
    assert "The Power of Starting Again" in titles
    for product in body["data"]:
        assert product["availability"] == "coming-soon"
        assert "price" not in product
