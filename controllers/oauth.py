from odoo import http
from odoo.http import request, Response
import secrets
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

logger.info(">>>>>>>> OAUTH CONTROLLER FILE IS LOADED BY ODOO <<<<<<<<")

class GarmOAuthController(http.Controller):

    @http.route(
        '/garm/oauth/authorize',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False
    )

    def authorize(self, **kwargs):

        client_id = kwargs.get("client_id", None)

        redirect_uri = kwargs.get("redirect_uri", None)

        state = kwargs.get("state", None)

        if not client_id or not redirect_uri or not state:
            return Response(
                "Missing required parameters: client_id, redirect_uri, and state are required.", 
                status=400
            )

        client = request.env[
            'garm.oauth.client'
        ].sudo().search([
            ('client_id', '=', client_id),
            ('active', '=', True)
        ], limit=1)

        if not client:
            return request.not_found()

        return request.render(
            'garm.authorize_page',
            {
                'client': client,
                'redirect_uri': redirect_uri,
                'state': state
            }
        )


    @http.route(
        '/garm/oauth/approve',
        type='http',
        auth='user',
        methods=['POST'],
        csrf=True
    )
    def approve(self, **post):

        client_id = post.get("client_id")

        redirect_uri = post.get("redirect_uri")

        state = post.get("state")

        client = request.env[
            'garm.oauth.client'
        ].sudo().search([
            ('client_id', '=', client_id)
        ], limit=1)

        if not client:
            return request.not_found()

        code = secrets.token_urlsafe(32)

        request.env[
            'garm.oauth.code'
        ].sudo().create({

            'code': code,

            'client_id': client.id,

            'user_id': request.env.user.id,

            'expires_at': datetime.now() + timedelta(seconds=(60 * 24 * 30))

        })

        url = (
            redirect_uri
            + "?code="
            + code
            + "&state="
            + state
        )

        return request.redirect(url)