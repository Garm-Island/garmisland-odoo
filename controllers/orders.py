from odoo import http
from odoo.http import request, Response
from datetime import datetime, timedelta
import logging
import json
import math
import base64
from urllib.parse import parse_qsl
from .oauth import authenticate

logger = logging.getLogger(__name__)

logger.info(">>>>>>>> ORDER CONTROLLER FILE IS LOADED BY ODOO <<<<<<<<")

class GarmOrderController(http.Controller):

    def normalizeOrder(self, order):
        result = {}
        for key, val in order.items():
            if isinstance(val, tuple):
                result[key] = list(val)
            elif isinstance(val, list):
                result[key] = val
            else:
                try:
                    json.dumps(val)
                    result[key] = val
                except TypeError:
                    result[key] = str(val)

        return result

    def normalizeOrderLine(self, order_line):
        result = {}
        for key, val in order_line.items():
            if isinstance(val, tuple):
                result[key] = list(val)
            elif isinstance(val, list):
                result[key] = val
            elif isinstance(val, dict):
                result[key] = self.normalizeOrder(val)
            else:
                try:
                    json.dumps(val)
                    result[key] = val
                except TypeError:
                    result[key] = str(val)

        return result

    @http.route(
        '/garm/orders',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False
    )
    def list_orders(self, **kwargs):
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
            count_only = kwargs.get('count_only', None)
            limit = max(1, int(kwargs.get('limit', 100)))
            cursor = kwargs.get('cursor', None)
            status = kwargs.get('status', None)
        except ValueError:
            limit = 100
            cursor = None
            status = None
            count_only = None

        order_model = request.env['sale.order'].sudo()
        domain = []

        if status:
            status_type = str(status).lower().strip()
            if status_type in ['draft', 'sent', 'sale', 'done', 'cancel']:
                domain.append(('state', '=', status_type))

        if 'website_id' in order_model._fields:
            domain.append(('website_id', '!=', False))

        total_count = order_model.search_count(domain)

        if count_only and count_only == '1':
            return Response(
                json.dumps({
                    "metadata": {
                        "total_count": total_count
                    }
                }),
                status=200,
                headers=[('Content-Type', 'application/json')]
            )

        if cursor:
            try:
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

        orders = order_model.search_read(
            domain=domain,
            limit=limit + 1,
            order='id asc'
        )

        has_next = len(orders) > limit
        if has_next:
            orders = orders[:limit]
            next_cursor = base64.b64encode(str(orders[-1]['id']).encode('utf-8')).decode('utf-8')
        else:
            next_cursor = None

        order_ids = [order['id'] for order in orders]
        order_lines = request.env['sale.order.line'].sudo().search_read(
            domain=[('order_id', 'in', order_ids)],
            fields=[
                'id',
                'order_id',
                'product_id',
                'name',
                'product_uom_qty',
                'qty_delivered',
                'price_unit',
                'discount',
                'price_subtotal',
                'price_total',
                'state'
            ]
        )

        lines_by_order = {}
        for line in order_lines:
            order_id = line.get('order_id', [None])[0]
            if order_id not in lines_by_order:
                lines_by_order[order_id] = []
            lines_by_order[order_id].append(self.normalizeOrderLine(line))

        clean_orders = []
        for order in orders:
            order_obj = self.normalizeOrder(order)
            order_obj['lines'] = lines_by_order.get(order['id'], [])
            clean_orders.append(order_obj)

        context = {
            "orders": clean_orders,
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