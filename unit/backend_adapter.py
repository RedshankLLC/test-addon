# -*- coding: utf-8 -*-
#
#
#    Techspawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY Techspawn(<http://www.Techspawn.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
import json
import logging
import time
import datetime
from requests_oauthlib import OAuth1
from requests_oauthlib import OAuth2Session

_logger = logging.getLogger(__name__)


class QboLocation(object):

    def __init__(self, location, client_key, client_secret, resource_owner_key, resource_owner_secret, company_id,
                 asset_account_ref, access_token, type):
        self._location = location
        self.client_key = client_key
        self.client_secret = client_secret
        self.resource_owner_key = resource_owner_key
        self.resource_owner_secret = resource_owner_secret
        self.company_id = company_id
        self.asset_account_ref = asset_account_ref
        self.access_token = access_token
        self.type = type

    @property
    def location(self):
        location = self._location
        return location


class QuickExportAdapter(object):
    """ External Records Adapter for QBO """

    def __init__(self, backend):

        backend = backend
        quick = QboLocation(
            backend.location,
            backend.client_key,
            backend.client_secret,
            backend.resource_owner_key,
            backend.resource_owner_secret,
            backend.company_id,
            backend.asset_account_ref,
            backend.access_token,
            backend.type)
        self.quick = quick


    def export(self, method, result_dict, arguments):

        def myconverter(o):
            if isinstance(o, datetime.date):
                return str(o)
        """ Export all data to quickbook"""
        if self.quick.type == 'oauth1':

            headeroauth = OAuth1(self.quick.client_key, self.quick.client_secret,
                                 self.quick.resource_owner_key, self.quick.resource_owner_secret,
                                 signature_type='auth_header')
        elif self.quick.type == 'oauth2':

            headeroauth = OAuth2Session(self.quick.client_key)

        headers = {'Authorization': 'Bearer %s' % self.quick.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        response_export = headeroauth.post(self.get_api_method(method, arguments), data=json.dumps(result_dict, default=myconverter), headers=headers)
        if response_export.status_code == 429:
            arguments[1].env.cr.commit()
            time.sleep(60)
            response_export = headeroauth.post(self.get_api_method(method, arguments), data=json.dumps(result_dict, default=myconverter), headers=headers)

        _logger.info("Export to api %s, status: %s, res : %s", self.get_api_method(method, arguments), response_export.status_code,
                     response_export.json())
        return response_export

    def importer_updater(self, method, arguments):
        """ Export all data to quickbook"""
        if self.quick.type == 'oauth1':

            headeroauth = OAuth1(self.quick.client_key, self.quick.client_secret,
                                 self.quick.resource_owner_key, self.quick.resource_owner_secret,
                                 signature_type='auth_header')
        elif self.quick.type == 'oauth2':

            headeroauth = OAuth2Session(self.quick.client_key)

        headers = {'Authorization': 'Bearer %s' % self.quick.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        ris = self.quick.location + self.quick.company_id + \
              '/' + method + '/' + str(arguments[0]) + '?minorversion=4'
        response = headeroauth.get(ris, headers=headers)
        if response.status_code == 429:
            arguments[1].env.cr.commit()
            time.sleep(60)
            response = headeroauth.get(ris, headers=headers)
        return response.json()

    def create_or_update_job(self, name, code, backend_id, response, request, quickbook_id, odoo_id):
        record = self.env['quickbook.jobs'].search(
            [('name', '=', name), ('odoo_id', '=', odoo_id)])
        values = {
            'name': name,
            'code': code,
            'backend_id': backend_id,
            'response': response,
            'request': request,
            'quickbook_id': quickbook_id,
            'odoo_id': odoo_id,
        }
        if record:
            record.write(values)
        else:
            self.env['quickbook.jobs'].create(values)
