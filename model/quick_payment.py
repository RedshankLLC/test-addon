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
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from requests_oauthlib import OAuth2Session
from ..unit.quick_payment_exporter import QboPaymentExport
from ..unit.backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)

class quickbook_acount_payment(models.Model):
    _inherit = 'account.payment'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    linked_doc_number = fields.Char(
        string='Linked txnReferenceNumber', readonly=False, required=False)

    @api.model
    def create(self, vals):
        return super(quickbook_acount_payment, self).create(vals)

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
                data = headeroauth.get(
                    backend.location + backend.company_id + '/' + arguments + '/' + str(record_id) + '?minorversion=4',
                    headers=headers)

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


    def payment_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        ID = []
        if 'Payment' in record:
            rec = record['Payment']
            linked_doc_number = ''
            if 'CustomerRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['CustomerRef']['value'])])
                if partner_id and partner_id.customer_rank > 0:
                    partner_type = 'customer'
                else:
                    partner_type = 'supplier'
                partner_ids = partner_id.id or False
            else:
                partner_ids = False
                partner_type = None

            if 'TxnDate' in rec:
                payment_date = rec['TxnDate']
            else:
                payment_date = None

            if rec['Id']:
                quickbook_id = rec['Id']

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

            if 'Line' in rec:
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Invoice':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            communication = inv_id.ref or ''
                            amount = lines['Amount'] or None
                            ID = []
                            if inv_id:
                                ID = inv_id.id
                                state = inv_id.state

            if 'Payment' in record:
                journal_id = self.env['account.journal'].search([('type', 'in', ('bank','cash'))], limit=1)
                payment_type = 'inbound'
                payment_method_id = 1

            if 'Line' in rec:
                diffrence = 0.0
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Invoice' or trnx['TxnType'] == 'Bill':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            amount = lines['Amount'] or None
                            if inv_id.move_type in ['in_invoice', 'out_refund']:
                                diffrence = amount - inv_id.amount_total
                            else:
                                diffrence = inv_id.amount_total - amount

                            if diffrence > 0.0:
                                payment_difference_handling = 'open'
                                writeoff_account_id = None
                            else:
                                payment_difference_handling = 'reconcile'
                                writeoff_account_id = partner_id.property_account_receivable_id.id
                    for data in lines['LineEx']:
                        for dict_data in lines['LineEx']['any']:
                            if dict_data['value']['Name'] == 'txnReferenceNumber':
                                if 'Value' in dict_data['value']:
                                    linked_doc_number = dict_data['value']['Value']
                    if lines['Amount']:
                        total_amt = lines['Amount']
                    else:
                        total_amt = 0
                    payment_id = self.env['account.payment'].search(
                        [('quickbook_id', '=', quickbook_id),
                         ('backend_id', '=', backend_id)])
                    if ID and state == 'posted':
                        vals = {
                            'partner_id': partner_ids,
                            'partner_type': partner_type,
                            'ref': communication,
                            'date': payment_date or rec['TxnDate'],
                            'amount': total_amt,
                            'journal_id': journal_id.id,
                            'payment_type': payment_type,
                            # 'payment_method_id': payment_method_id,
                            'payment_method_line_id': payment_method_id,
                            'backend_id': backend_id,
                            'quickbook_id': quickbook_id,
                            'currency_id': currency,
                        }
                        if 'Payment' in record:
                            vals.update({'linked_doc_number':linked_doc_number})

                        if not payment_id:
                            payment = super(quickbook_acount_payment, self).create(vals)
                            QuickExportAdapter.create_or_update_job(self, 'Import Payment', 200, backend_id, record,
                                                                    vals, record['Payment']['Id'], payment.id)
                            payment.action_post()

                            if 'Payment' in record:
                                if linked_doc_number:
                                    a = self.env['account.move'].search([('name', '=', payment.name)])
                                    b = self.env['account.move'].search([('doc_number','=', payment.linked_doc_number)])
                                    for l in b.line_ids:
                                        if b.partner_id.property_account_receivable_id == l.account_id:
                                            lines = l
                                    if type(lines) != dict:
                                        payment_lines = a.line_ids
                                        for account in payment_lines.account_id:
                                            (payment_lines + lines).filtered_domain([('account_id', '=', account.id), ('reconciled', '=', False)]).reconcile()

                            if 'BillPayment' in record:
                                if linked_doc_number:
                                    a = self.env['account.move'].search([('name', '=', payment.name)])
                                    b = self.env['account.move'].search([('quickbook_id','=', payment.linked_doc_number)])
                                    for line in b.line_ids:
                                        if b.partner_id.property_account_payable_id == line.account_id:
                                            lines = line
                                    if type(lines) != dict:
                                        payment_lines = a.line_ids
                                        for account in payment_lines.account_id:
                                            (payment_lines + lines).filtered_domain([('account_id', '=', account.id), ('reconciled', '=', False)]).reconcile()
                        else:
                            try:
                                payment_id.write(vals)
                                QuickExportAdapter.create_or_update_job(self, 'Import Payment', 200,
                                                                        backend_id, record,
                                                                        vals, record['Payment']['Id'],
                                                                        payment_id.id)
                            except Exception as e:
                                QuickExportAdapter.create_or_update_job(self, 'Import Payment', 400,
                                                                        backend_id, record,
                                                                        vals, record['Payment']['Id'],
                                                                        payment_id.id)
                                _logger.info(_("Error in Import Payment: " + str(e)))
            return

        elif 'BillPayment' in record:
            rec = record['BillPayment']
            linked_doc_number = ''
            if 'VendorRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['VendorRef']['value'])])
                if partner_id and partner_id.customer_rank > 0:
                    partner_type = 'customer'
                else:
                    partner_type = 'supplier'
                partner_ids = partner_id.id or False

            else:
                partner_ids = False
                partner_type = None

            if 'Line' in rec:
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Bill':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            communication = inv_id.ref or ''
                            amount = lines['Amount'] or None
                            ID = []
                            if inv_id:
                                ID = inv_id.id
                                state = inv_id.state

                            linked_doc_number = trnx['TxnId']

            if rec['PayType'] == 'Check':
                payment_method_id = 2
                payment_type = 'outbound'
                journal_id = self.env['account.journal'].search([('type', 'in', ('bank','cash'))], limit=1)
            else:
                payment_method_id = 1
                payment_type = 'outbound'
                journal_id = self.env['account.journal'].search([('type', 'in', ('bank','cash'))], limit=1)

            if 'Line' in rec:
                diffrence = 0.0
                for lines in rec['Line']:
                    for trnx in lines['LinkedTxn']:
                        if trnx['TxnType'] == 'Invoice' or trnx['TxnType'] == 'Bill':
                            inv_id = self.env['account.move'].search(
                                [('quickbook_id', '=', trnx['TxnId'])])
                            amount = lines['Amount'] or None
                            if inv_id.move_type in ['in_invoice', 'out_refund']:
                                diffrence = amount - inv_id.amount_total
                            else:
                                diffrence = inv_id.amount_total - amount
                if diffrence > 0.0:
                    payment_difference_handling = 'open'
                    writeoff_account_id = None
                else:
                    payment_difference_handling = 'reconcile'
                    writeoff_account_id = partner_id.property_account_receivable_id.id
            if 'TxnDate' in rec:
                payment_date = rec['TxnDate']
            else:
                payment_date = None

            if rec['Id']:
                quickbook_id = rec['Id']

            if rec['TotalAmt']:
                total_amt = rec['TotalAmt']
            else:
                total_amt = 0

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        payment_id = self.env['account.payment'].search(
            [('quickbook_id', '=', quickbook_id),
             ('backend_id', '=', backend_id)])

        if ID and state == 'posted':
            vals = {
                'partner_id': partner_ids,
                'partner_type': partner_type,
                'ref': communication,
                'date': payment_date or rec['TxnDate'],
                'amount': total_amt,
                'journal_id': journal_id.id,
                'payment_type': payment_type,
                'payment_method_line_id': payment_method_id,
                'backend_id': backend_id,
                'quickbook_id': quickbook_id,
                'currency_id': currency,
            }
            if 'Payment' in record:
                vals.update({'linked_doc_number':linked_doc_number})

            if 'BillPayment' in record:
                vals.update({'linked_doc_number':linked_doc_number})
            if not payment_id:
                payment = super(quickbook_acount_payment, self).create(vals)
                QuickExportAdapter.create_or_update_job(self, 'Import BillPayment', 200, backend_id, data, vals,
                                                        data['BillPayment']['Id'], payment.id)
                payment.action_post()

                if 'Payment' in record:
                    if linked_doc_number:
                        a = self.env['account.move'].search([('name', '=', payment.name)])
                        b = self.env['account.move'].search([('doc_number','=', payment.linked_doc_number)])
                        for l in b.line_ids:
                            if b.partner_id.property_account_receivable_id == l.account_id:
                                lines = l
                        if type(lines) != dict:
                            payment_lines = a.line_ids
                            for account in payment_lines.account_id:
                                (payment_lines + lines).filtered_domain([('account_id', '=', account.id), ('reconciled', '=', False)]).reconcile()

                if 'BillPayment' in record:
                    if linked_doc_number:
                        a = self.env['account.move'].search([('name', '=', payment.name)])
                        b = self.env['account.move'].search([('quickbook_id','=', payment.linked_doc_number)])
                        for line in b.line_ids:
                            if b.partner_id.property_account_payable_id == line.account_id:
                                lines = line
                        if type(lines) != dict:
                            payment_lines = a.line_ids
                            for account in payment_lines.account_id:
                                (payment_lines + lines).filtered_domain([('account_id', '=', account.id), ('reconciled', '=', False)]).reconcile()
            else:
                try:
                    payment = payment_id.write(vals)
                    QuickExportAdapter.create_or_update_job(self, 'Import BillPayment', 200, backend_id, data, vals,
                                                            data['BillPayment']['Id'], payment_id.id)
                except Exception as e:
                    QuickExportAdapter.create_or_update_job(self, 'Import BillPayment', 400, backend_id, data, vals,
                                                            data['BillPayment']['Id'], payment_id.id)
                    _logger.info(_("Error in Import BillPayment: " + str(e)))
            return payment

    def payment_import_batch(self, model_name, backend_id, filters=None):
        """ Import Payment Details. """
        arguments = 'payment'
        count = 1
        filters['url'] = 'payment'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Payment' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Payment']
                for record_id in record_ids:
                    self.env['account.payment'].importer(arguments=arguments, backend_id=backend_id,filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids['QueryResponse']

    def BillPayment_import_batch(self, model_name, backend_id, filters=None):
        """ Import BillPayment Details. """
        arguments = 'billpayment'
        count = 1
        record_ids = ['start']
        filters['url'] = 'billpayment'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'BillPayment' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['BillPayment']
                for record_id in record_ids:
                    self.importer(arguments=arguments, backend_id=backend_id,
                                  filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.payment_import_mapper(backend_id, data)

    def sync_payment(self):
        for backend in self.backend_id:
            if self.partner_type == 'customer':
                self.export_payment_data(backend)
            elif self.partner_type == 'supplier':
                self.export_billpayment_data(backend)
        return

    def export_payment_data(self, backend):
        """ export payments and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.payment'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'payment'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPaymentExport(backend)
        res = export.export_payment(method, arguments)
        # code for logger
        if res:
            if 'Payment' in res['data']:
                qb_id = res['data']['Payment']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Payment', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)
        if mapper.id == self.id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Payment']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Payment']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Payment']['Id']})
        if res['status'] == 500 or res['status'] == 400:
            if res['data']:
                for errors in res['data']['Fault']['Error']:
                    msg = errors['Message']
                    code = errors['code']
                    name = res['name']
                    details = 'Message: ' + msg + '\n' + 'Code: ' + \
                              code + '\n' + 'Name:' + str(name.name) + '\n' +'Detail: ' + errors['Detail']  +'\n' +'Applied Data: ' + str(res['applied_data'])
                    if errors['code']:
                        _logger.info(_(details))

    def export_billpayment_data(self, backend):
        """ export bill payments and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.payment'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'billpayment'
        arguments = [mapper.quickbook_id or None, self]
        export = QboPaymentExport(backend)
        res = export.export_billpayment(method, arguments)
        # code for logger
        if res:
            if 'BillPayment' in res['data']:
                qb_id = res['data']['BillPayment']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export BillPayment', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)
        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['BillPayment']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['BillPayment']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['BillPayment']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                            code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + errors['Detail'] + \
                            '\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Export billpayment Data: " +str(details)))

    @api.model
    def default_get(self, fields):
        res = super(quickbook_acount_payment, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res