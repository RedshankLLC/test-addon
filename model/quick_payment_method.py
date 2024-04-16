# -*- coding: utf-8 -*-
#
#
#    TechSpawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY TechSpawn(<http://www.techspawn.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the PaymentMethods of the GNU Affero General Public License as
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
import logging
import time

from datetime import datetime
from odoo import models, fields, api,_
from odoo.exceptions import UserError
from requests_oauthlib import OAuth2Session
from ..unit.quick_pay_method_exporter import QboPaymentMethodExport
from ..unit.backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)

class quickbook_acount_method(models.Model):
    _inherit = 'payment.provider'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    payment_type = fields.Selection([('CREDIT_CARD', 'Credit Card'),
                                     ('NON_CREDIT_CARD', 'Non Credit Card')], 'Payment Type')

    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            if backend.data == 'custom':
                sd = str(backend.start_date.year) +'-'+str(backend.start_date.month).zfill(2)+'-'+str(backend.start_date.day).zfill(2)
                ed = str(backend.end_date.year) +'-'+str(backend.end_date.month).zfill(2)+'-'+str(backend.end_date.day).zfill(2)
                data = headeroauth.get(backend.location + backend.company_id +"/query?query=select ID from "+ arguments +" Where Metadata.CreateTime>'" + str(sd) +"' and Metadata.CreateTime<'"+ str(ed)+"'" + ' MAXRESULTS ' + str(1000) +'&minorversion=54', headers=headers)
            elif backend.data == 'all':
                if backend.company_id:
                    data = headeroauth.get(backend.location + backend.company_id +
                                   method + arguments + '%20STARTPOSITION%20'+ str(backend.record_no) + '%20MAXRESULTS%20' + str(500) + '&minorversion=54', headers=headers)
                else:
                    raise UserError(_('Please add company ID'))
        else:
            data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=4', headers=headers)
            if data.status_code == 429:
                self.env.cr.commit()
                time.sleep(60)
                data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=4', headers=headers)

        if data:
            if isinstance(arguments, list):
                while arguments and arguments[-1] is None:
                    arguments.pop()
            start = datetime.now()
            try:
                if 'false' or 'true' or 'null' in data.content:
                    # converting str data contents to bytes
                    data1 = bytes(data.content)
                    # decoding data contents
                    data_decode = data.content.decode('utf-8')
                    # encoding data contents
                    result = data_decode.replace('false', 'False').encode('utf-8')

                    data_decode_one = result.decode('utf-8')
                    result = data_decode_one.replace('true', 'True').encode('utf-8')

                    data_decode_two = result.decode('utf-8')
                    result = data_decode_two.replace('null', 'False')

                    result = eval(result)
                else:
                    result = eval(data.content)
            except:
                _logger.error("api.call(%s, %s) failed", method, arguments)
            else:
                _logger.debug("api.call(%s, %s) returned %s in %s seconds",
                              method, arguments, result,
                              (datetime.now() - start).seconds)
            return result

    def payment_method_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'PaymentMethod' in record:
            rec = record['PaymentMethod']
            if 'Name' in rec:
                name = rec['Name']
            if 'Active' in rec:
                active = rec['Active']
            if 'Type' in rec:
                payment_type = rec['Type']
            if rec['Id']:
                quickbook_id = rec['Id']

        partner_id = self.env['payment.provider'].search(
            [('quickbook_id', '=', quickbook_id),
             ('backend_id', '=', backend_id)])
        vals = {
            'name': name,
            'payment_type': payment_type,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
        }

        if not partner_id:
            try:
                a = super(quickbook_acount_method, self).create(vals)
                a.env.cr.commit()
                QuickExportAdapter.create_or_update_job(self, 'Import PaymentMethod', 200, backend_id, data, vals, data['PaymentMethod']['Id'], a.id)
                return a
            except:
                QuickExportAdapter.create_or_update_job(self, 'Import PaymentMethod', 400, backend_id, data, vals, data['PaymentMethod']['Id'], partner_id.id)
                raise UserError(_("Issue while importing " + vals.get(
                    'name') + ". Please check if there are any missing values in Quickbooks."))
        else:
            partner = partner_id.write(vals)
            QuickExportAdapter.create_or_update_job(self, 'Import PaymentMethod', 200, backend_id, data, vals, data['PaymentMethod']['Id'], partner_id.id)
            return partner

    def payment_method_import_batch(self, model_name, backend_id, filters=None):
        """ Import Customer Details."""
        arguments = 'paymentmethod'
        count = 1
        record_ids = ['start']
        filters['url'] = 'paymentmethod'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'PaymentMethod' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['PaymentMethod']
                for record_id in record_ids:
                    self.env['payment.provider'].importer(arguments=arguments, backend_id=backend_id,
                                                                       filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.payment_method_import_mapper(backend_id, data)

    def sync_PaymentMethod(self):
        for backend in self.backend_id:
            self.export_payment_method_data(backend)
        return

    def export_payment_method_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['payment.provider'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'paymentmethod'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPaymentMethodExport(backend)
        res = export.export_payment_Method(method, arguments)
        # code for logger
        if res:
            if 'PaymentMethod' in res['data']:
                qb_id = res['data']['PaymentMethod']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export PaymentMethod', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['PaymentMethod']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['PaymentMethod']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['PaymentMethod']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                          code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + errors['Detail'] \
                          +'\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Payment Method Export: " + details))