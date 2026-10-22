from flask_restful import Resource

from ..schemas.queries import PagePathQuerySchema
from ..services import page_render
from ..utils.errors import NotFoundError
from ..utils.responses import success
from ._validation import load_query


class PageListPublicResource(Resource):
    """Live CMS pages (used by the prerenderer to render every page)."""

    def get(self):
        pages = page_render.published_pages()
        return success(pages, {"total": len(pages)})


class PageResolveResource(Resource):
    """A published page by its path, resolved for rendering. Drafts are never returned."""

    def get(self):
        path = load_query(PagePathQuerySchema())["path"]
        page = page_render.public_page(path)
        if page is None:
            raise NotFoundError("Page not found.")
        return success(page)
