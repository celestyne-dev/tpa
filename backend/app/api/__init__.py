"""Versioned public API (``/api/v1``)."""

from flask import Blueprint
from flask_restful import Api

from .articles import ArticleDetailResource, ArticleListResource
from .health import HealthResource, ReadinessResource
from .pages import PageListPublicResource, PageResolveResource
from .products import ProductListResource
from .seo import RedirectListPublicResource, RedirectResolveResource, SitemapResource
from .site import SiteResource
from .topics import TopicDetailResource, TopicListResource


class TPAApi(Api):
    def handle_error(self, e):
        # Defer to the app-level JSON error handlers so every error has one shape.
        raise e


api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api = TPAApi(api_v1)

api.add_resource(HealthResource, "/health")
api.add_resource(ReadinessResource, "/health/ready")
api.add_resource(SiteResource, "/site")
api.add_resource(TopicListResource, "/topics")
api.add_resource(TopicDetailResource, "/topics/<string:slug>")
api.add_resource(ArticleListResource, "/articles")
api.add_resource(ArticleDetailResource, "/articles/<string:slug>")
api.add_resource(ProductListResource, "/products")
api.add_resource(SitemapResource, "/sitemap")
api.add_resource(PageListPublicResource, "/pages")
api.add_resource(PageResolveResource, "/pages/resolve")
api.add_resource(RedirectListPublicResource, "/redirects")
api.add_resource(RedirectResolveResource, "/redirects/resolve")

# ---- Storefront, customer accounts, checkout, downloads, payment webhooks -------
from .commerce import PRIVATE_PREFIXES, PUBLIC_COMMERCE_ROUTES  # noqa: E402

for resource, path in PUBLIC_COMMERCE_ROUTES:
    api.add_resource(resource, path, endpoint=f"shop_{resource.__name__.lower()}")

# ---- Newsletter, lead magnets and email provider feedback ------------------------
from .newsletter import NEWSLETTER_PRIVATE_PREFIXES, PUBLIC_NEWSLETTER_ROUTES  # noqa: E402

for resource, path in PUBLIC_NEWSLETTER_ROUTES:
    api.add_resource(resource, path, endpoint=f"newsletter_{resource.__name__.lower()}")

# ---- Partnership inquiries, media kit, affiliate redirects ------------------------
from .partnerships import PARTNERSHIP_PRIVATE_PREFIXES, PUBLIC_PARTNERSHIP_ROUTES  # noqa: E402

for resource, path in PUBLIC_PARTNERSHIP_ROUTES:
    api.add_resource(resource, path, endpoint=f"partnership_{resource.__name__.lower()}")

# ---- Text-based courses: catalogue, certificates and learners ---------------------
from .courses import COURSE_PRIVATE_PREFIXES, PUBLIC_COURSE_ROUTES  # noqa: E402

for resource, path in PUBLIC_COURSE_ROUTES:
    api.add_resource(resource, path, endpoint=f"course_{resource.__name__.lower()}")

# ---- Membership plans (Batch 10.1: published plans; no billing yet) ------------------
from .memberships import PUBLIC_MEMBERSHIP_ROUTES  # noqa: E402

for resource, path in PUBLIC_MEMBERSHIP_ROUTES:
    api.add_resource(resource, path, endpoint=f"membership_{resource.__name__.lower()}")

# ---- First-party page-view beacon (Batch 11.1) -------------------------------------
from .analytics import PUBLIC_ANALYTICS_ROUTES  # noqa: E402

for resource, path in PUBLIC_ANALYTICS_ROUTES:
    api.add_resource(resource, path, endpoint=f"analytics_{resource.__name__.lower()}")

# ---- Admin API ------------------------------------------------------------------
from flask import request  # noqa: E402

from ..auth.decorators import check_origin  # noqa: E402
from .admin import ADMIN_ROUTES  # noqa: E402

for resource, path in ADMIN_ROUTES:
    api.add_resource(resource, path, endpoint=f"admin_{resource.__name__.lower()}")


WEBHOOK_PATHS = ("/api/v1/payments/",)


@api_v1.before_request
def _admin_origin_guard():
    # Cookie-authenticated mutations (admin and customer) only from trusted origins.
    # Provider webhooks authenticate with signatures instead.
    if request.path.startswith(WEBHOOK_PATHS):
        return
    if request.path.startswith("/api/v1/admin") or request.path.startswith(PRIVATE_PREFIXES):
        check_origin()


@api_v1.after_request
def _admin_no_store(response):
    if request.path.startswith("/api/v1/admin"):
        # Admin data (including draft previews) is never cached or indexed.
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    elif request.path.startswith(
        PRIVATE_PREFIXES
        + NEWSLETTER_PRIVATE_PREFIXES
        + PARTNERSHIP_PRIVATE_PREFIXES
        + COURSE_PRIVATE_PREFIXES
    ):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        response.headers["Vary"] = "Cookie"
    return response
