# -*- coding: utf-8 -*-

import werkzeug
from odoo import http
from odoo.http import request

class Authorize2(http.Controller):
    @http.route('/web/callback', type='http', auth='none', website=True)
    def get_authorized_url(self, state, code, realmId, **kw):
        res = request.env['qb.backend'].sudo().search([])
        res.write({
            'company_id': realmId,
            'o2_auth_url': res.redirect_uri + '?' + 'state=%s' % state + '&code=%s' % code + '&realmId=%s' % realmId,
        })
        context = {
            'id': str(res.id),
            'client_key': str(res.client_key),
            'client_secret': str(res.client_secret),
            'company_id': str(res.company_id),
            'redirect_uri': str(res.redirect_uri),
            'o2_auth_url': str(res.o2_auth_url),
            'token_url': str(res.token_url),
            'location': str(res.location),
            'scope': str(res.scope)
        }
        base_url=http.request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        res.qb_auth_o2_auto_step2(context)
        return werkzeug.utils.redirect(base_url)