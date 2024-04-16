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

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime
from requests_oauthlib import OAuth2Session
from ..unit.backend_adapter import QuickExportAdapter
from ..unit.quick_account_exporter import QboAccountExport
import os
import json
_logger = logging.getLogger(__name__)


class quickbook_acount(models.Model):
    _inherit = 'account.account'

    # account_type = fields.Selection(
    #     selection_add=[('asset_receivable', 'Anand')], ondelete={'anand': 'cascade'})
    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    account_type = fields.Selection(
        selection=[
            ("asset_receivable", "Receivable"),
            ("asset_cash", "Bank and Cash"),
            ("asset_current", "Current Assets"),
            ("asset_non_current", "Non-current Assets"),
            ("asset_prepayments", "Prepayments"),
            ("asset_fixed", "Fixed Assets"),
            ("liability_payable", "Payable"),
            ("liability_credit_card", "Credit Card"),
            ("liability_current", "Current Liabilities"),
            ("liability_non_current", "Non-current Liabilities"),
            ("equity", "Equity"),
            ("equity_unaffected", "Current Year Earnings"),
            ("income", "Income"),
            ("income_other", "Other Income"),
            ("expense", "Expenses"),
            ("expense_depreciation", "Depreciation"),
            ("expense_direct_cost", "Cost of Revenue"),
            ("off_balance", "Off-Balance Sheet"),
            ("liability_qb_1", "Accounts Payable"),
            ("asset_qb_1", "Accounts Receivable"),
            ("expense_qb_1", "Expense"),
            ("liability_qb_2", "Other Current Liability"),
            ("asset_qb_2", "Other Current Asset"),
            ("asset_qb_3", "Bank"),
            ("expense_qb_2", "Cost of Goods Sold"),
            ("expense_qb_3", "Other Expense"),
            ("expense_qb_4", "Other Income"),
            ("liability_qb_4", "Credit Card"),
            ("liability_qb_3", "Long Term Liability"),
            ("equity_qb_1", "Equity"),
            ("asset_qb_4", "Fixed Asset"),
            ("asset_qb_5", "Other Assets"),
        ],
        string="Type", tracking=True,
        required=True,
        compute='_compute_account_type', store=True, readonly=False, precompute=True,
        help="Account Type is used for information purpose, to generate country-specific legal reports, and set the rules to close a fiscal year and generate opening entries."
    )

    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            if backend.data == 'custom':
                sd = str(backend.start_date.year) + '-'+str(backend.start_date.month).zfill(
                    2)+'-'+str(backend.start_date.day).zfill(2)
                ed = str(backend.end_date.year) + '-'+str(backend.end_date.month).zfill(2) + \
                    '-'+str(backend.end_date.day).zfill(2)
                data = headeroauth.get(backend.location + backend.company_id + "/query?query=select ID from " + arguments + " Where Metadata.CreateTime>'" + str(
                    sd) + "' and Metadata.CreateTime<'" + str(ed)+"'" + ' MAXRESULTS ' + str(1000) + '&minorversion=54', headers=headers)
            elif backend.data == 'all':
                if backend.company_id:
                    data = headeroauth.get(backend.location + backend.company_id +
                                       method + arguments + '%20STARTPOSITION%20' +  str(backend.record_no) + '%20MAXRESULTS%20' + str(500) + '&minorversion=54', headers=headers)
                else:
                    raise UserError(_('Please add company ID'))
        else:
            data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=54', headers=headers)
            if data.status_code == 429:
                self.env.cr.commit()
                time.sleep(60)
                data = headeroauth.get(
                    backend.location + backend.company_id + '/' +
                    arguments + '/' + str(record_id) + '?minorversion=54',
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
                    result = data_decode.replace(
                        'false', 'False').encode('utf-8')
                    data_decode_one = result.decode('utf-8')
                    result = data_decode_one.replace(
                        'true', 'True').encode('utf-8')
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

    def account_import_mapper_type(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Account' in record:
            rec = record['Account']
            reconcile = False
            if 'Name' in rec:
                name = rec['Name']
                code = rec['AcctNum'] if rec.get(
                    'AcctNum') else self.env['ir.sequence'].next_by_code('account.account')
            else:
                name = False
                code = False
            if 'Active' in rec:
                active = rec['Active']
            if 'CurrentBalance' in rec:
                balance = rec['CurrentBalance']




            if 'AccountType' in rec:


                b = dict(self._fields['account_type'].selection)
              

                data_ac_type = rec['AccountType']
                
                file_path = os.path.dirname(os.path.realpath(__file__))[:-6] + '/static/test.json'
                
                f = open(file_path, 'r')
                
                f.seek(0)
                json_file = json.load(f)
               
                json_file_data = json_file['data']
                
                f.close()

                if data_ac_type in b.values():


                    
                    value = [i for i in b if b[i] == data_ac_type][0]

                else:
                    ex = self._fields['account_type'].selection
                    
                    if rec['Classification'] == 'Revenue':
                        classification = 'income_qb_1'
                    elif rec['Classification'] == 'Expense':
                        classification = 'expense_qb_1'
                    elif rec['Classification'] == 'Asset':
                        classification = 'asset_qb_1'
                    elif rec['Classification'] == 'Liability':
                        classification = 'liability_qb_1'
                    elif rec['Classification'] == 'Equity':
                        classification = 'equity_qb_1'
                    
                    for value in json_file_data:
                        if classification in value:
                            class_last_num = classification.split('_')[-1]
                            new_number = int(class_last_num) + 1
                            list_without_num = classification.split('_')[:-1]
                            list_without_num.append(str(new_number))
                            classification = '_'.join(list_without_num)

                    add_data = (classification, rec['AccountType'])
                    if list(add_data) not in json_file_data:
                        json_file_data.append(list(add_data))
                    
                    vals_new = {
                        "data": json_file_data
                    }
                    
                    with open(file_path, 'w') as file:
                        json.dump(vals_new, file, indent = 4)

   
    def account_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        user_type = False
        if 'Account' in record:
            rec = record['Account']
            reconcile = False
            if 'Name' in rec:
                name = rec['Name']
                code = rec['AcctNum'] if rec.get('AcctNum') else self.env['ir.sequence'].next_by_code('account.account')
            else:
                name = False
                code = False
            if 'Active' in rec:
                active = rec['Active']
            if 'CurrentBalance' in rec:
                balance = rec['CurrentBalance']
            if 'AccountType' in rec:
                
                
                account_type_dict = dict(self._fields['account_type'].selection)
               
                if rec['AccountType'] in account_type_dict.values():
                    user_type = [i for i in account_type_dict if account_type_dict[i]==rec['AccountType']][0]
                
                if rec['AccountType'] == 'Accounts Receivable' or rec['AccountType'] == 'Accounts Payable':
                    reconcile = True
            else:
                user_type = False
            if rec['Id']:
                quickbook_id = rec['Id']


        if code != False:
            if 'Name' in rec:
                name = rec['Name']
                account_id = self.env['account.account'].search([('code', '=', code),('name', '=', name)])

                
        account_id = self.env['account.account'].search(
            [('quickbook_id', '=', quickbook_id), ('backend_id', '=', backend_id)])
        vals = {
            'name': name,
            'code': code,
            'account_type': user_type or False,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
            'reconcile': reconcile
        }
        if vals['account_type'] == False or record['Account']['Id'] in ('119','91'):
            return
        if not account_id:
            try:
                a=super(quickbook_acount, self).create(vals)
                a.env.cr.commit()
                QuickExportAdapter.create_or_update_job(self, 'Import Account', 200, backend_id, data, vals, data['Account']['Id'], a.id)
                return a
            except:
                QuickExportAdapter.create_or_update_job(self, 'Import Account', 400, backend_id, data, vals, data['Account']['Id'], account_id.id)
                raise UserError(_("Issue while importing Chart of Account " + vals.get('name') + ". Please check if there are any missing values in Quickbooks."))
        else:
            for ac_id in account_id:
                account = ac_id.write(vals)
                QuickExportAdapter.create_or_update_job(self, 'Import Account', 200, backend_id, data, vals, data['Account']['Id'], ac_id.id)
                return account

    def account_import_batch_new(self, model_name, backend_id, filters=None):
        """ Import Account Details. """
        arguments = 'account'
        count = 1
        record_ids = ['start']
        filters['url'] = 'account'
        filters['count'] = count
        record_ids = self.get_ids(
            arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Account' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Account']
                for record_id in record_ids:
                    self.env['account.account'].importer(arguments=arguments, backend_id=backend_id,
                                                         filters=filters,
                                                         record_id=int(record_id['Id']))
            else:
                record_ids['QueryResponse']
    def account_import_batch_type(self, model_name, backend_id, filters=None):
        """ Import Account Details. """
        arguments = 'account'
        count = 1
        record_ids = ['start']
        filters['url'] = 'account'
        filters['count'] = count
        record_ids = self.get_ids(
            arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Account' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Account']
                for record_id in record_ids:
                    self.env['account.account'].importer_type(arguments=arguments, backend_id=backend_id,
                                                         filters=filters,
                                                         record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']
    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.account_import_mapper(backend_id, data)
    def importer_type(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.account_import_mapper_type(backend_id, data)

    def sync_account(self):
        for backend in self.backend_id:
            self.export_account_data(backend)
        return

    def sync_account_multiple(self):
        for rec in self:
            for backend in rec.backend_id:
                rec.export_account_data(backend)
        return

    def export_account_data(self, backend):
        """ export account and create or update backend """
        if not self.backend_id:
            return
        mapper = self.env['account.account'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'account'
        arguments = [mapper.quickbook_id or None, self]
        export = QboAccountExport(backend)
        res = export.export_account(method, arguments)
        # code for logger
        if res:
            if 'Account' in res['data']:
                qb_id = res['data']['Account']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Account', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Account']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Account']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Account']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                          code + '\n' + 'Name: ' + \
                    str(name.name) + '\n' + 'Detail: ' + errors['Detail'] +'\n' +'Applied Data: ' + str(res['applied_data'])
                
                
                if msg == "Duplicate Name Exists Error":
                    dup_id = details.split("=")[1]

                    self.quickbook_id = dup_id
                    
                else:
                    
                    if errors['code'] == '2090':
                        _logger.info(_("Account export" + details))
                        # raise UserError(
                        #     _("Please Check Whether Income Account Field and Expense Account Field Empty Or Not Synced "))
                    else:
                         _logger.info(_("Account export" + details))

    @api.model
    def default_get(self, fields):
        res = super(quickbook_acount, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res


