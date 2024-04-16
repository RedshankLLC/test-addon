import logging
import time
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from requests_oauthlib import OAuth2Session
from ..unit.backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)

class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'
    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
class quickbook_acount_tax(models.Model):

    _inherit = 'account.tax'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    rate_quickbook_id = fields.Char(
        string='Rate ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')

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
                                    '/' + arguments + '/' + str(record_id) + '?minorversion=4', 
                                    headers=headers)

        if data:
            if isinstance(arguments, list):
                while arguments and arguments[-1] is None:
                    arguments.pop()
            start = datetime.now()
            try:
                if 'false' or 'true' or 'null'in data.content:
                    # converting str data contents to bytes
                    bytes(data.content)
                    # decoding data contents
                    data_decode = data.content.decode('utf-8')
                    # encoding data contents
                    result = data_decode.replace('false', 'False').encode('utf-8')

                    data_decode_one = result.decode('utf-8')
                    result = data_decode_one.replace('true', 'True').encode('utf-8')

                    data_decode_two = result.decode('utf-8')
                    result = data_decode_two.replace('null', 'False').encode('utf-8')

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

    def tax_code_import_mapper(self, backend_id, data):
        record = data
        description = None
        active = False
        _logger.info("API DATA :%s", data)
        if 'TaxCode' in record:
            rec = record['TaxCode']
            if 'SalesTaxRateList' in rec:
                if 'TaxRateDetail' in rec['SalesTaxRateList']:
                    for rate in rec['SalesTaxRateList']['TaxRateDetail']:
                        if 'Name' in rec:
                            name = 'QB_Sale-' + rec['Name']
                        if 'Description' in rec:
                            description = rec['Description'] or None

                        if 'Active' in rec:
                            active = rec['Active']

                        if 'TaxGroup' in rec:
                            if rec['TaxGroup'] == True:
                                option = 'group'
                                amount = 0
                        rate_ids = []
                        if rate['TaxRateRef']:
                            user_type = self.env['account.tax'].search(
                                [('name', '=', rate['TaxRateRef']['name']),
                                ('rate_quickbook_id', '=', rate['TaxRateRef']['value'])])
                            if user_type:
                                rate_ids.append(user_type.id)
                        if rec['Id']:
                            quickbook_id = rec['Id']

                        tax_code_id = self.env['account.tax'].search([('quickbook_id', '=', quickbook_id),
                                        ('type_tax_use', '=', 'sale'), ('backend_id', '=', backend_id)])
                        vals = {
                            'name': name or 'QBO' + rec['Name'],
                            'description': description,
                            'amount': amount,
                            'amount_type': option,
                            'tax_group_id': 1,
                            'children_tax_ids': [(6, 0, rate_ids)] or None,
                            'type_tax_use': 'sale',
                            'backend_id': backend_id,
                            'quickbook_id': quickbook_id,
                        }

                        if not tax_code_id:
                            try:
                                a = super(quickbook_acount_tax, self).create(vals)
                                a.env.cr.commit()
                                QuickExportAdapter.create_or_update_job(self, 'Import Tax', 200, backend_id, data, vals,
                                                                        data['TaxCode']['Id'], a.id)
                                return a
                            except:
                                QuickExportAdapter.create_or_update_job(self, 'Import Tax', 400, backend_id, data, vals,
                                                                        data['TaxCode']['Id'], tax_code_id.id)
                                _logger.info(_("Issue while importing Account Sale Tax " + vals.get('name') + ". Please check if there are any missing values in Quickbooks."))
                        else:
                            tax_code = tax_code_id.write(vals)
                            QuickExportAdapter.create_or_update_job(self, 'Import Tax', 200, backend_id, data, vals,
                                                                    data['TaxCode']['Id'], tax_code_id.id)
                            return tax_code

            if 'PurchaseTaxRateList' in rec:
                if 'TaxRateDetail' in rec['PurchaseTaxRateList']:
                    for rate in rec['PurchaseTaxRateList']['TaxRateDetail']:
                        if 'Name' in rec:
                            name = 'QB_Purchase-' + rec['Name']
                        if 'Description' in rec:
                            description = rec['Description'] or None

                        if 'Active' in rec:
                            active = rec['Active']

                        if 'TaxGroup' in rec:
                            if rec['TaxGroup'] == True:
                                option = 'group'
                                amount = 0
                        rate_ids = []
                        if rate['TaxRateRef']:
                            user_type = self.env['account.tax'].search(
                                [('name', '=', rate['TaxRateRef']['name']),
                                ('rate_quickbook_id', '=', rate['TaxRateRef']['value'])])
                            if user_type:
                                rate_ids.append(user_type.id)
                        if rec['Id']:
                            quickbook_id = rec['Id']

                        tax_code_id = self.env['account.tax'].search([('quickbook_id', '=', quickbook_id),
                                          ('type_tax_use', '=', 'purchase'), ('backend_id', '=', backend_id)])
                        vals = {
                            'name': name or 'QBO' + rec['Name'],
                            'description': description,
                            'amount': amount,
                            'amount_type': option,
                            'tax_group_id': 1,
                            'children_tax_ids': [(6, 0, rate_ids)] or None,
                            'type_tax_use': 'purchase',
                            'backend_id': backend_id,
                            'quickbook_id': quickbook_id,
                        }
                        if not tax_code_id:
                            try:
                                a = super(quickbook_acount_tax, self).create(vals)
                                a.env.cr.commit()
                                QuickExportAdapter.create_or_update_job(self, 'Import Tax', 200, backend_id, data, vals,
                                                                    data['TaxCode']['Id'], a.id)
                                return a
                            except:
                                QuickExportAdapter.create_or_update_job(self, 'Import Tax', 400, backend_id, data, vals,
                                                                        data['TaxCode']['Id'], tax_code_id.id)
                                _logger.info(_("Issue while importing Account Purchase Tax " + vals.get('name') + ". Please check if there are any missing values in Quickbooks."))
                        else:
                            tax_code = tax_code_id.write(vals)
                            QuickExportAdapter.create_or_update_job(self, 'Import Tax', 200, backend_id, data, vals,
                                                                    data['TaxCode']['Id'], tax_code_id.id)
                            return tax_code

    def tax_import_batch(self, model_name, backend_id, filters=None):
        """ Import Tax Code Details. """
        arguments = 'taxcode'
        count = 1
        record_ids = ['start']
        filters['url'] = 'taxcode'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'TaxCode' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['TaxCode']
                for record_id in record_ids:
                    self.env['account.tax'].importer(arguments=arguments, backend_id=backend_id, filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids['QueryResponse']

    def tax_rate_import_batch(self, model_name, backend_id, filters=None):
        """ Prepare the import of vendor """
        arguments = 'taxrate'
        record_ids = self.get_ids(arguments, backend_id, record_id=False)
        if record_ids:
            if 'Vendor' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Vendor']
                for record_id in record_ids:
                    self.env['res.partner'].importer(arguments=arguments, backend_id=backend_id, record_id=int(record_id['Id']))

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self._import_dependencies(data, filters, backend_id)
            self.tax_code_import_mapper(backend_id, data)

    def _import_dependencies(self, data, filters, backend_id):
        """ Import the dependencies for the record"""
        record = data
        _logger.info("API DATA :%s", data)
        if 'SalesTaxRateList' in record['TaxCode']:
            if record['TaxCode']['SalesTaxRateList']['TaxRateDetail']:
                for rate in record['TaxCode']['SalesTaxRateList']['TaxRateDetail']:
                    arguments = 'taxrate'
                    values = self.get_ids(arguments, backend_id, filters, record_id=int(rate['TaxRateRef']['value']))
                    if values:
                        val = values['TaxRate']
                        if val['SpecialTaxType'] == "ADJUSTMENT_RATE":
                            adjustment  = True
                            amount = 0
                        elif val['SpecialTaxType'] == "NONE":
                            adjustment  = False
                            amount = val['RateValue']
                        elif val['SpecialTaxType'] == "ZERO_RATE":
                            adjustment  = False
                            amount = val['RateValue']
                        else:
                            adjustment  = False
                            amount = val['RateValue']
                        search_id = self.env['account.tax'].search([('backend_id', '=',  backend_id),('rate_quickbook_id', '=', val['Id'])])
                        if search_id:
                            if search_id['amount_type'] == 'percent':
                                search_id.write({
                                        'name': val['Name'],
                                        'description': val['Description'],
                                        'amount': amount,
                                        'tax_group_id': 1,
                                        'type_tax_use': 'sale',
                                        'amount_type': 'percent',
                                        'active':val['Description'],
                                        'rate_quickbook_id': val['Id'],
                                        'backend_id': backend_id,
                                })
                            if search_id['amount_type'] == 'group':
                                search_id.write({
                                        'name': val['Name'],
                                        'description': val['Description'],
                                        'amount': amount,
                                        'tax_group_id': 1,
                                        'type_tax_use': 'sale',
                                        'amount_type': 'group',
                                        'active':val['Description'],
                                        'rate_quickbook_id': val['Id'],
                                        'backend_id': backend_id,
                                })
                        else:
                            try:
                                self.env['account.tax'].create({
                                    'name': val['Name'],
                                    'description': val['Description'],
                                    'amount': amount,
                                    'tax_group_id': 1,
                                    'type_tax_use': 'sale',
                                    'amount_type': 'percent',
                                    'active':val['Description'],
                                    'rate_quickbook_id': val['Id'],
                                    'backend_id': backend_id,
                                })
                            except Exception as e:
                                    _logger.error(_("Account Tax" + str(e)))

        if 'PurchaseTaxRateList' in record['TaxCode']:
            if record['TaxCode']['PurchaseTaxRateList']['TaxRateDetail']:
                for rate in record['TaxCode']['PurchaseTaxRateList']['TaxRateDetail']:
                    arguments = 'taxrate'
                    values = self.get_ids(arguments, backend_id, filters, record_id=int(rate['TaxRateRef']['value']))
                    if values:
                        val = values['TaxRate']
                        if val['SpecialTaxType'] == "ADJUSTMENT_RATE":
                            adjustment  = True
                            amount = 0
                        elif val['SpecialTaxType'] == "NONE":
                            adjustment  = False
                            amount = val['RateValue']
                        elif val['SpecialTaxType'] == "ZERO_RATE":
                            adjustment  = False
                            amount = val['RateValue']
                        else:
                            adjustment  = False
                            amount = val['RateValue']
                        search_id = self.env['account.tax'].search([('backend_id', '=',  backend_id),('rate_quickbook_id', '=', val['Id'])])
                        if search_id:
                            if search_id['amount_type'] == 'percent':
                                search_id.write({
                                        'name': val['Name'],
                                        'description': val['Description'],
                                        'amount': amount,
                                        'tax_group_id': 1,
                                        'type_tax_use': 'purchase',
                                        'amount_type': 'percent',
                                        'active':val['Description'],
                                        'rate_quickbook_id': val['Id'],
                                        'backend_id': backend_id,
                                })
                            if search_id['amount_type'] == 'group':
                                search_id.write({
                                        'name': val['Name'],
                                        'description': val['Description'],
                                        'amount': amount,
                                        'tax_group_id': 1,
                                        'type_tax_use': 'purchase',
                                        'amount_type': 'group',
                                        'active':val['Description'],
                                        'rate_quickbook_id': val['Id'],
                                        'backend_id': backend_id,
                                })
                        else:
                            try:
                                self.env['account.tax'].create({
                                    'name': val['Name'],
                                    'description': val['Description'],
                                    'amount': amount,
                                    'tax_group_id': 1,
                                    'type_tax_use': 'purchase',
                                    'amount_type': 'percent',
                                    'active':val['Description'],
                                    'rate_quickbook_id': val['Id'],
                                    'backend_id': backend_id,
                                })
                            except Exception as e:
                                _logger.error(_("Account Tax"+str(e)))

        return

    def export_vendor_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.supplier:
            return
        mapper = self.env['res.partner'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'vendor'
        arguments = [mapper.quickbook_id or None, self]
        export = QboCustomerExport(backend)
        res = export.export_vendor(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Vendor']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Vendor']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Vendor']['Id']})


    @api.model
    def default_get(self,fields):
        res=super(quickbook_acount_tax,self).default_get(fields)
        ids=self.env['qb.backend'].search([]).id
        res['backend_id']=ids
        return res