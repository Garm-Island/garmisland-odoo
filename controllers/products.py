from odoo import http
from odoo.http import request, Response
from datetime import datetime, timedelta
import logging
import json
import math
import base64
from .oauth import authenticate

logger = logging.getLogger(__name__)

logger.info(">>>>>>>> PRODUCT CONTROLLER FILE IS LOADED BY ODOO <<<<<<<<")

class GarmProductController(http.Controller):

    def normalizeProducts(self, product):
        result = {}
        for key, val in product.items():
            # Convert non-serializable fields (like dates or custom objects) into safe types
            if isinstance(val, tuple):
                result[key] = list(val) # Convert tuple to JSON-friendly list
            else:
                try:
                    json.dumps(val) # Test if it can be serialized
                    result[key] = val
                except TypeError:
                    result[key] = str(val) # Fallback to string representation

        return result

    @http.route(
        '/garm/products',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def products(self, **kwargs):
        oauth = authenticate()

        if not oauth:
            return Response(
                json.dumps({
                    "error": "unauthorized",
                    "error_description": "Unauthorized access"
                }),
                status=400,
                headers=[('Content-Type', 'application/json')]
            )

        try:
            limit = max(1, int(kwargs.get('limit', 150)))   # Default to 150 items per page
            cursor = kwargs.get('cursor', None)
            status = kwargs.get('status', None)
        except ValueError:
            limit = 150
            status = None
            cursor = None

        product_model = request.env["product.template"].sudo()
        
        domain = []

        if status:
            status_type = str(status).lower().strip()
            if status_type == "draft":

                domain.append(('active', '=', True))
                domain.append(('is_published', '=', False))

            elif status_type == "active":

                domain.append(('active', '=', True))
                domain.append(('sale_ok', '=', True))
                domain.append(('is_published', '=', True))

            elif status_type == "archived":

                domain.append(('active', '=', False))


        total_count = product_model.search_count(
            domain=domain
        )

        if cursor:
            try:
                # Decode base64 cursor to get the last seen ID
                last_id = int(base64.b64decode(cursor).decode('utf-8'))
                domain.append(('id', '>', last_id))

            except Exception:
                return Response(
                    json.dumps({
                        "error": "invalid_cursor", 
                        "error_description": "The provided cursor is invalid."
                    }),
                    status=400,
                    headers=[('Content-Type', 'application/json')]
                )

        products_data = product_model.search_read(
            domain=domain,
            limit=limit + 1,
            order="id asc"
        )

        has_next = len(products_data) > limit

        if has_next:
            products_data = products_data[:limit]

            # Create next cursor using the ID of the very last item in our page slice
            next_last_id = str(products_data[-1]['id']).encode('utf-8')
            next_cursor = base64.b64encode(next_last_id).decode('utf-8')

        else:
            next_cursor = None

        clean_products = []
        for prod in products_data:
            clean_products.append(self.normalizeProducts(prod))

        context = {
            "products": clean_products,
            "metadata": {
                "limit": limit,
                "next_cursor": next_cursor,
                "has_next": has_next,
                "total_count": total_count
            }
        }

        return Response(
            json.dumps(context),
            status=200,
            headers=[('Content-Type', 'application/json')]
        )

    @http.route(
        '/garm/product/<int:product_id>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def get_product_by_id(self, product_id, **kwargs):
        oauth = authenticate()

        if not oauth:
            return Response(
                json.dumps({
                    "error": "unauthorized",
                    "error_description": "Unauthorized access"
                }),
                status=400,
                headers=[('Content-Type', 'application/json')]
            )

        product = request.env["product.template"].sudo().browse(product_id)

        if not product.exists():
            return Response(
                json.dumps({
                    "error": "not_found",
                    "error_description": f"Product with ID {product_id} does not exist."
                }),
                status=404,
                headers=[('Content-Type', 'application/json')]
            )
        
        products_data = self.normalizeProducts(product.read()[0])

        context = {
            "product": products_data
        }

        return Response(
            json.dumps(context),
            status=200,
            headers=[('Content-Type', 'application/json')]
        )