from flask_restful import Resource

from ..services.commerce.catalogue import list_public as list_products
from ..utils.responses import success


class ProductListResource(Resource):
    """Batch 01 compatibility endpoint: the published catalogue (see /shop/products)."""

    def get(self):
        products = list_products()
        return success(products, {"total": len(products)})
