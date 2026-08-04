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

    def normalizeListProducts(self, product):
            result = []
            for val in product:
                # Convert non-serializable fields (like dates or custom objects) into safe types
                if isinstance(val, tuple):
                    result.append(list(val)) # Convert tuple to JSON-friendly list
                if isinstance(val, dict):
                    result.append(self.normalizeProducts(val)) # Convert tuple to JSON-friendly list
                else:
                    try:
                        json.dumps(val) # Test if it can be serialized
                        result.append(val)
                    except TypeError:
                        result.append(str(val)) # Fallback to string representation
    
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

        products_data = product_model.search(
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
            attribute_lines = request.env["product.template.attribute.line"].sudo().search(
                domain=[('product_tmpl_id', '=', prod.id)]
            )
    
            serialized_attributes = []
            for line in attribute_lines:
                
                tmpl_attribute_values = request.env["product.template.attribute.value"].sudo().search([
                    ('product_tmpl_id', '=', prod.id),
                    ('attribute_id', '=', line.attribute_id.id)
                ])
    
                values_list = []
                for tmpl_val in tmpl_attribute_values:
                    values_list.append({
                        "value_id": tmpl_val.product_attribute_value_id.id, # The core global value ID
                        "value_name": tmpl_val.name,                         # The name (e.g., "XL")
                        "price_extra": tmpl_val.price_extra                 # The variant surcharge price (e.g., 5.0)
                    })
    
                serialized_attributes.append({
                    "attribute_line_id": line.id,
                    "attribute_id": line.attribute_id.id,
                    "attribute_name": line.attribute_id.name,
                    "values": values_list
                })

            prod_obj = self.normalizeProducts(prod.read()[0])
            prod_obj['attribute'] = serialized_attributes
            clean_products.append(prod_obj)

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
        attribute_lines = request.env["product.template.attribute.line"].sudo().search(
            domain=[('product_tmpl_id', '=', product_id)]
        )

        serialized_attributes = []
        for line in attribute_lines:
            
            tmpl_attribute_values = request.env["product.template.attribute.value"].sudo().search([
                ('product_tmpl_id', '=', product_id),
                ('attribute_id', '=', line.attribute_id.id)
            ])

            values_list = []
            for tmpl_val in tmpl_attribute_values:
                values_list.append({
                    "value_id": tmpl_val.product_attribute_value_id.id, # The core global value ID
                    "value_name": tmpl_val.name,                         # The name (e.g., "XL")
                    "price_extra": tmpl_val.price_extra                 # The variant surcharge price (e.g., 5.0)
                })

            serialized_attributes.append({
                "attribute_line_id": line.id,
                "attribute_id": line.attribute_id.id,
                "attribute_name": line.attribute_id.name,
                "values": values_list
            })

        products_data["attribute"] = serialized_attributes

        context = {
            "product": products_data
        }

        return Response(
            json.dumps(context),
            status=200,
            headers=[('Content-Type', 'application/json')]
        )

    @http.route(
        '/garm/product/categories',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def product_categories(self, **kwargs):
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
    
            category_model = request.env["product.category"].sudo()
            
            domain = []
    
    
            total_count = category_model.search_count(
                domain=domain
            )
    
            categories_data = category_model.search_read(
                domain=domain,
                fields=["id", "name", "parent_id", "complete_name"],
                order="complete_name asc"
            )
    
            
            clean_categories = []
            for category in categories_data:
                category_obj = self.normalizeProducts(category)

                product_count = request.env["product.template"].sudo().search_count([
                    ('categ_id', 'child_of', category_obj['id'])
                ])

                category_obj['product_count'] = product_count

                clean_categories.append(category_obj)
    
            context = {
                "categories": clean_categories,
                "metadata": {
                    "total_count": total_count
                }
            }
    
            return Response(
                json.dumps(context),
                status=200,
                headers=[('Content-Type', 'application/json')]
            )

    @http.route(
        '/garm/product/<int:product_id>/variants',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def product_variants(self, product_id, **kwargs):
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
                        "error": "product_not_found",
                        "error_description": "Product not found"
                    }), 
                    status=400,
                    headers=[('Content-Type', 'application/json')]
                )
    
            variants = request.env["product.product"].sudo().search_read(
                domain=[('product_tmpl_id', '=', product_id), ('active', '=', True)]
            )
    
            
            clean_variants = []

            for variant in variants:
                variant_obj = self.normalizeProducts(variant)

                clean_variants.append(variant_obj)
    
            context = {
                "variants": clean_variants
            }
    
            return Response(
                json.dumps(context),
                status=200,
                headers=[('Content-Type', 'application/json')]
            )

    @http.route(
        '/garm/product/<int:product_id>/attributes',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def product_attributes(self, product_id, **kwargs):
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
                        "error": "product_not_found",
                        "error_description": "Product not found"
                    }), 
                    status=400,
                    headers=[('Content-Type', 'application/json')]
                )

            structured_attributes = []

            for line in product.attribute_line_ids:
                # Gather all individual value options defined for this product line
                values_list = []
                
                for val in line.value_ids:
                    values_list.append({
                        "value_id": val.id,
                        "value_name": val.name
                    })

                # Append the parent attribute along with its choices
                structured_attributes.append({
                    "attribute_line_id": line.id,
                    "attribute_id": line.attribute_id.id,
                    "attribute_name": line.attribute_id.name, # e.g., "Color" or "Size"
                    "values": values_list                      # e.g., [{"value_id": 1, "value_name": "Red"}]
                })
    
            context = {
                "attributes": structured_attributes
            }
    
            return Response(
                json.dumps(context),
                status=200,
                headers=[('Content-Type', 'application/json')]
            )