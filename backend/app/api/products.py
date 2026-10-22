from flask_restful import Resource

from ..schemas.content import products_schema
from ..services.product_service import list_products
from ..utils.responses import success


class ProductListResource(Resource):
    def get(self):
        products = list_products()
        return success(products_schema.dump(products), {"total": len(products)})
