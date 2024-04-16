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
from odoo import models, fields, api,_
from odoo.exceptions import UserError
from requests_oauthlib import OAuth2Session
from ..unit.quick_payment_term_exporter import QboPaymentTermExport
from ..unit.backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)

class quickbook_journal_entry(models.Model):
    _inherit = 'account.journal'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.journal_mapper(backend_id, data)

    def sync_term(self):
        for backend in self.backend_id:
            self.journal_data(backend)
        return

    def journal_data(self, backend):
        """ export term details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.journal'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'term'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPaymentTermExport(backend)
        res = export.export_journal(method, arguments)
        if res:
            if 'JournalEntry' in res['data']:
                qb_id = res['data']['JournalEntry']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Journal', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)
        if mapper.id == self.id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Term']['Id']})
            elif res['status'] == 200 or res['status'] == 201:
                self.env['account.journal'].create(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Term']['Id']})
        elif res['status'] == 200 or res['status'] == 201:
            self.env['account.journal'].create(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Term']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: ' + name.name + '\n' + 'Detail: ' + \
                          errors['Detail']
                if errors['code']:
                    raise UserError(details)

    def journal_batch_new(self, model_name, backend_id, filters=None):
        """ Import journal Details. """
        arguments = 'journalentry'
        count = 1
        record_ids = ['start']
        filters['url'] = 'journalentry'
        filters['count'] = count
        record_ids = self.get_ids_new(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'JournalEntry' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['JournalEntry']
                for record_id in record_ids:
                    self.env['account.journal'].importer_new(arguments=arguments, backend_id=backend_id,
                                                                           filters=filters,
                                                                           record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def get_ids_new(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token, 'content-type': 'application/json',
                   'accept': 'application/json'}
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

    def importer_new(self, arguments, backend_id, filters, record_id):
        data = self.get_ids_new(arguments, backend_id, filters, record_id)
        if data:
            self.journal_mapper_new(backend_id, data)

    def journal_mapper_new(self, backend_id, data):

        record = data
        _logger.info("API DATA %s", data)

        line_ids = []

        if 'JournalEntry' in record:
            rec = record['JournalEntry']

            for lines in rec['Line'] :
                detail = lines['DetailType']
                if lines[detail]['PostingType'] == "Credit" :
                    default_credit = int(lines[detail]['AccountRef']['value'])
                    term = self.env['account.account'].search([('quickbook_id', '=', default_credit)]).id
                    default_credit_account_id = term
                    if lines.get('Description'):
                        description = lines['Description']
                    else:
                        description = ''
                    if lines.get('Amount'):
                        amount = lines['Amount']
                    else:
                        amount = 0
                    result = {'account_id':term, 'name':description, 'credit':float(amount)}
                    line_ids.append([0,0,result])
                if lines[detail]['PostingType'] == "Debit" :
                    default_debit = int(lines[detail]['AccountRef']['value'])
                    term = self.env['account.account'].search([('quickbook_id', '=', default_debit)]).id
                    default_debit_account_id = term
                    if lines.get('Description'):
                        description = lines['Description']
                    else:
                        description = ''
                    if lines.get('Amount'):
                        amount = lines['Amount']
                    else:
                        amount = 0
                    result = {'account_id':term, 'name':description, 'debit':float(amount)}
                    line_ids.append([0,0,result])

            if rec['TxnDate'] :
                create_date = rec['TxnDate']

            if rec['Id'] :
                quickbook_id = rec['Id']

            if rec.get('DocNumber'):
                doc_number = rec['DocNumber']
            else:
                doc_number = ''
            if rec.get('PrivateNote'):
                refname = rec['PrivateNote']
            else:
                refname = ''

        account_journal_id = self.env['account.move'].search(
            [('quickbook_id', '=', quickbook_id),
             ('backend_id', '=', backend_id)])
        vals = {
            'ref': refname,
            'date': create_date,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
            'doc_number' : doc_number,
            'line_ids': line_ids
        }
        if not account_journal_id:
            journal = self.env['account.move'].create(vals)
            QuickExportAdapter.create_or_update_job(self, 'Import Journal', 200, backend_id, record,
                                                    vals, record['JournalEntry']['Id'], journal.id)
        else:
            return account_journal_id