from flask_restful import Resource

from ..services.site_service import get_site_settings
from ..utils.responses import success


class SiteResource(Resource):
    def get(self):
        return success(get_site_settings())
