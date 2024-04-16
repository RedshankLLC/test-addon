# -*- coding: utf-8 -*-
#
#
#    TechSpawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY TechSpawn(<http://www.techspawn.com>).
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
import logging
import time
from datetime import datetime
from odoo import models, fields, _
from odoo.exceptions import UserError
from requests_oauthlib import OAuth2Session
from ..unit.quick_payment_term_exporter import QboPaymentTermExport
from ..unit.backend_adapter import QuickExportAdapter
_logger = logging.getLogger(__name__)


class quickbook_acount_term(models.Model):
    _inherit = 'account.payment.term'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')

    def get_ids(self, arguments, backend_id, filters, record_id):
        # arguments = 'term'
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token, 'content-type': 'application/json',
                   'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            if backend.company_id:
                data = headeroauth.get(backend.location+backend.company_id +
                                        method+arguments+'%20STARTPOSITION%20'+ str(filters['count']) + '%20MAXRESULTS%20' + str(1000) +'&minorversion=4', headers=headers)
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

    def term_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Term' in record:
            rec = record['Term']
            if 'Name' in rec:
                name = rec['Name']
                note = rec['Name']

            if 'Active' in rec:
                active = rec['Active']
           
            lines_pay_ids = []
            if 'Type' in rec:
                term = self.env['account.payment.term'].search(
                    [('quickbook_id', '=', rec['Id']), ('name', '=', rec['Name'])])
                line = term.line_ids
                if rec['Type'] == 'STANDARD':
                    value = 'percent'
                    option = 'day_after_invoice_date'
                    duedate = rec['DueDays']

                if rec['Type'] == 'DATE_DRIVEN':
                    value = 'percent'
                    # option = 'day_current_month'
                    duedate =  int(rec['DayOfMonthDue']) if rec.get('DayOfMonthDue') else 1

                result = {
                    'nb_days': duedate,
                    'value': value,
                    # 'option': option,
                }
                if not line:
                    lines_pay_ids.append([0, 0, result]) or False
                else:
                    lines_pay_ids.append([1, line.id, result])

            if rec['Id']:
                quickbook_id = rec['Id']

                pay_term_id = self.env['account.payment.term'].search(
                    [('quickbook_id', '=', quickbook_id),
                     ('backend_id', '=', backend_id)])
                vals = {
                    'name': name,
                    'note': note,
                    'active': active,
                    'line_ids': lines_pay_ids,
                    'backend_id': backend_id,
                    'quickbook_id': quickbook_id,
                }

                if not pay_term_id:
                    try:
                        pay_term = super(quickbook_acount_term, self).create(vals)
                        pay_term.env.cr.commit()
                        QuickExportAdapter.create_or_update_job(self, 'Import Payment Term', 200, backend_id, data,
                                                                vals, data['Term']['Id'],
                                                                pay_term.id)
                    except Exception as e:
                        QuickExportAdapter.create_or_update_job(self, 'Import Payment Term', 400, backend_id, data,
                                                                vals, data['Term']['Id'],
                                                                pay_term_id.id)
                        _logger.error("Payment Term not created " + str(e))
                else:
                    QuickExportAdapter.create_or_update_job(self, 'Import Payment Term', 200, backend_id, data, vals,
                                                            data['Term']['Id'],
                                                            pay_term_id.id)
                    term = pay_term_id.write(vals)
                    return term

    def term_import_batch(self, model_name, backend_id, filters=None):
        """ Import term Details. """
        arguments = 'term'
        count = 1
        record_ids = ['start']
        filters['url'] = 'term'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Term' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Term']
                for record_id in record_ids:
                    self.env['account.payment.term'].importer(arguments=arguments, backend_id=backend_id,
                                                                           filters=filters,
                                                                           record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.term_import_mapper(backend_id, data)

    def sync_term(self):
        for backend in self.backend_id:
            self.export_term_data(backend)
        return

    def export_term_data(self, backend):
        """ export term details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.payment.term'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'term'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPaymentTermExport(backend)
        res = export.export_payment_term(method, arguments)

        if mapper.id == self.id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Term']['Id']})
            elif res['status'] == 200 or res['status'] == 201:
                self.env['account,.payment.term'].create(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Term']['Id']})
        elif res['status'] == 200 or res['status'] == 201:
            self.env['account,.payment.term'].create(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Term']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: ' + name.name + '\n' + 'Detail: ' + \
                          errors['Detail']  +'\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Payment Terms :"+details))
