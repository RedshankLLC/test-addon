import logging
import time

from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from requests_oauthlib import OAuth2Session

_logger = logging.getLogger(__name__)

class quickbook_accounts_custom(models.Model):
    _name = 'quickbook.accounts'
    _description = 'Quickbook Accounts'

    name = fields.Char(required=False)
    account_type_id = fields.Char()
    classification = fields.Char()
    quickbook_id = fields.Char(string='ID on Quickbook', readonly=True)
    account_odoo = fields.Many2one('account.account', readonly=False, domain="[('quickbook_id','=',False)]")
    code = fields.Char()
    active = fields.Boolean(default=False)
    balance = fields.Float(default=0.0)
    reconcile = fields.Boolean(default=False)
    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    def get_ids(self, arguments, backend_id, filters, record_id):
        # arguments = 'customer
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            if backend.company_id:
                data = headeroauth.get(backend.location + backend.company_id +
                                   method + arguments + '%20STARTPOSITION%20'+ str(filters['count']) + '%20MAXRESULTS%20' + str(1000) + '&minorversion=4', headers=headers)
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

    def account_import_batch(self, model_name, backend_id, filters=None):
        """ Import Account Details. """
        arguments = 'account'
        count = 1
        record_ids = ['start']
        filters['url'] = 'account'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Account' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Account']
                for record_id in record_ids:
                    self.env['quickbook.accounts'].importer(arguments=arguments, backend_id=backend_id,
                                                                         filters=filters,
                                                                         record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.account_import_mapper(backend_id, data)
    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.account_import_mapper_type(backend_id, data)

    def account_import_mapper_type(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Account' in record:

            rec = record['Account']
            reconcile = False
            if 'Name' in rec:
                name = rec['Name']
                code = self.env['ir.sequence'].next_by_code('quickbook.accounts')
            else:
                name = False
                code = False
            if 'Active' in rec:
                active = rec['Active']
            if 'CurrentBalance' in rec:
                balance = rec['CurrentBalance']
            if 'AccountType' in rec:
                account_type = rec['AccountType']
                if rec['AccountType'] == 'Accounts Receivable' or rec['AccountType'] == 'Accounts Payable':
                    reconcile = True
            else:
                account_type = False
            if rec['Id']:
                quickbook_id = rec['Id']

        account_id = self.env['quickbook.accounts'].search(
            [('quickbook_id', '=', quickbook_id)])
        vals = {
            'name': name,
            'code': code,
            'active': active,
            'balance': balance,
            'account_type_id': account_type,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
            'reconcile': reconcile
        }
        if not account_id:
            return super(quickbook_accounts_custom, self).create(vals)
        else:
            for ac_id in account_id:
                account = ac_id.write(vals)
                return account
    def account_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Account' in record:

            rec = record['Account']
            reconcile = False
            if 'Name' in rec:
                name = rec['Name']
                code = self.env['ir.sequence'].next_by_code('quickbook.accounts')
            else:
                name = False
                code = False
            if 'Active' in rec:
                active = rec['Active']
            if 'CurrentBalance' in rec:
                balance = rec['CurrentBalance']
            if 'AccountType' in rec:
                account_type = rec['AccountType']
                if rec['AccountType'] == 'Accounts Receivable' or rec['AccountType'] == 'Accounts Payable':
                    reconcile = True
            else:
                account_type = False
            if rec['Id']:
                quickbook_id = rec['Id']

        account_id = self.env['quickbook.accounts'].search(
            [('quickbook_id', '=', quickbook_id)])
        vals = {
            'name': name,
            'code': code,
            'active': active,
            'balance': balance,
            'account_type_id': account_type,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
            'reconcile': reconcile
        }
        if not account_id:
            return super(quickbook_accounts_custom, self).create(vals)
        else:
            for ac_id in account_id:
                account = ac_id.write(vals)
                return account

    def write(self, fields):
        res = super(quickbook_accounts_custom, self).write(fields)
        if self.account_odoo:
            old_qb_acc = self.env['account.account'].search([('quickbook_id', '=', self.quickbook_id)])
            for acc in old_qb_acc:
                if self.account_odoo == acc:
                    self.account_odoo.quickbook_id = self.quickbook_id
                else:
                    acc.update({'quickbook_id': False})
            self.account_odoo.quickbook_id = self.quickbook_id
        return res