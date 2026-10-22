"""Public SEO endpoints used by the prerender step and the static server."""

from flask import request
from flask_restful import Resource

from ..services import redirect_service, seo_service
from ..utils.errors import NotFoundError
from ..utils.responses import success


class SitemapResource(Resource):
    def get(self):
        entries = seo_service.sitemap_entries()
        return success(entries, {"total": len(entries)})


class RedirectListPublicResource(Resource):
    def get(self):
        items = redirect_service.active_redirects()
        return success(items, {"total": len(items)})


class RedirectResolveResource(Resource):
    def get(self):
        found = redirect_service.resolve(request.args.get("path", ""))
        if found is None:
            raise NotFoundError("No redirect for this path.")
        return success(found)
