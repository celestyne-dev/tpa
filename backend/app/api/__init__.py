"""Versioned public API (``/api/v1``)."""

from flask import Blueprint
from flask_restful import Api

from .articles import ArticleDetailResource, ArticleListResource
from .health import HealthResource
from .products import ProductListResource
from .site import SiteResource
from .topics import TopicDetailResource, TopicListResource


class TPAApi(Api):
    def handle_error(self, e):
        # Defer to the app-level JSON error handlers so every error has one shape.
        raise e


api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api = TPAApi(api_v1)

api.add_resource(HealthResource, "/health")
api.add_resource(SiteResource, "/site")
api.add_resource(TopicListResource, "/topics")
api.add_resource(TopicDetailResource, "/topics/<string:slug>")
api.add_resource(ArticleListResource, "/articles")
api.add_resource(ArticleDetailResource, "/articles/<string:slug>")
api.add_resource(ProductListResource, "/products")
