import logging
import random
import requests
import time

from odoo import models, fields, api
from datetime import datetime
from requests_oauthlib import OAuth2Session
from odoo.exceptions import UserError

from ..unit.quick_product_expoter import QboProductExport

_logger = logging.getLogger(__name__)

class quickbook_products_custom(models.Model):

    _name = 'quickbook.products'
    _description ='Quickbook Products'

    name = fields.Char(required=False)
    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    lst_price = fields.Float()
    property_account_income_id = fields.Many2one('quickbook.accounts',string='IncomeAccountRef')
    property_account_expense_id = fields.Many2one('quickbook.accounts',string='ExpenseAccountRef')

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=True)
    sync_date = fields.Datetime(string='Last synchronization date')
    image_name = fields.Char()
    product_odoo = fields.Many2one('product.template')
    active = fields.Boolean()
    description = fields.Text()
    purchase_tax_included = fields.Boolean()
    sales_tax_included = fields.Boolean()
    abatement_rate = fields.Char()
    reverse_charge_rate = fields.Char()
    taxable = fields.Boolean()
    description_purchase = fields.Text()
    description_sale = fields.Text()
    qty_available = fields.Float()
    standard_price = fields.Float()
    supplier_taxes_id = fields.Char()
    taxes_id = fields.Char()


    def get_ids(self, arguments, backend_id, filters, record_id):
        # arguments = 'customer'
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            data = headeroauth.get(backend.location + backend.company_id +
                                   method + arguments + '%20STARTPOSITION%20'+ str(filters['count']) + '%20MAXRESULTS%20' + str(1000) + '&minorversion=4', headers=headers)
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
                if 'false' or 'true' or 'null'in data.content:
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
    
    def product_import_mapper(self, backend_id, data):
        
        record = data
        _logger.info("API DATA :%s", data)
        if 'Item' in record:
            rec = record['Item']
            if 'Name' in rec:
                name = rec['Name']
            else:
                name = False
            if 'Active' in rec:
                active = rec['Active']
            else:
                active = True
            if 'UnitPrice' in rec:
                lst_price = float(rec['UnitPrice']) or 0.0
            else:
                lst_price = False
            if 'PurchaseTaxIncluded' in rec:
                purchase_tax_included = rec['PurchaseTaxIncluded']
            else:
                purchase_tax_included = False
            if 'SalesTaxIncluded' in rec:
                sales_tax_included = rec['SalesTaxIncluded']
            else:
                sales_tax_included = False
            if 'Taxable' in rec:
                taxable = rec['Taxable']
            else:
                taxable = False
            if 'AbatementRate' in rec:
                abatement_rate = rec['AbatementRate']
            else:
                abatement_rate = None
            if 'ReverseChargeRate' in rec:
                reverse_charge_rate = rec['ReverseChargeRate']
            else:
                reverse_charge_rate = None
            if rec['Type']:
                if rec['Type'] == 'Service':
                    product_type = 'service'
                elif rec['Type'] == 'NonInventory':
                    product_type = 'consu'
                elif rec['Type'] == 'Inventory':
                    product_type = 'product'
                else:
                    product_type = 'product'
            else:
                product_type = 'product'
            if 'Description' in rec:
                description = rec['Description']
            else:
                description = False
            if 'Description' in rec:
                description_sale = rec['Description']
            else:
                description_sale = False
            if 'PurchaseCost' in rec:
                standard_price = rec['PurchaseCost']
            else:
                standard_price = False
            if 'IncomeAccountRef' in rec:
                if rec['IncomeAccountRef']:
                    property_item_income = self.env['quickbook.accounts'].search(
                        [('quickbook_id', '=', rec['IncomeAccountRef']['value'])])
                    property_item_income = property_item_income.id or False
            else:
                property_item_income = False

            if 'ExpenseAccountRef' in rec:
                if rec['ExpenseAccountRef']:
                    property_item_expense = self.env['quickbook.accounts'].search(
                        [('quickbook_id', '=', rec['ExpenseAccountRef']['value'])])
                    property_item_expense = property_item_expense.id or False
            else:
                property_item_expense = False

            taxes_ids = []
            if 'SalesTaxCodeRef' in rec:
                if rec['SalesTaxCodeRef']:
                    taxes_id = self.env['account.tax'].search(
                        [('quickbook_id', '=', rec['SalesTaxCodeRef']['value'])])
                    taxes_ids.append(taxes_id.id)

            supplier_taxes_ids = []
            if 'PurchaseTaxCodeRef' in rec:
                if rec['PurchaseTaxCodeRef']:
                    supplier_taxes_id = self.env['account.tax'].search(
                        [('quickbook_id', '=', rec['PurchaseTaxCodeRef']['value'])])
                    supplier_taxes_ids.append(supplier_taxes_id.id)

            if 'PurchaseDesc' in rec:
                description_purchase = rec['PurchaseDesc'] or None
            else:
                description_purchase = None
            if 'QtyOnHand' in rec:
                qty_available = rec['QtyOnHand']
            else:
                qty_available = 0.0
            if rec['Id']:
                quickbook_id = rec['Id']

        item_id = self.env['quickbook.products'].search(
            [('quickbook_id', '=', quickbook_id), ('backend_id', '=', backend_id)])
        vals_quick_product = {
            'name': name,
            'active': active,
            'lst_price': lst_price,
            'purchase_tax_included': purchase_tax_included,
            'sales_tax_included': sales_tax_included,
            'taxable': taxable,
            'abatement_rate': abatement_rate,
            'reverse_charge_rate': reverse_charge_rate,
            'description': description,
            'property_account_income_id': property_item_income,
            'property_account_expense_id': property_item_expense,
            'taxes_id': [(6, 0, taxes_ids)] or None,
            'supplier_taxes_id': [(6, 0, supplier_taxes_ids)] or None,
            'description_sale': description_sale,
            'standard_price': standard_price,
            'description_purchase': description_purchase,
            'qty_available': qty_available,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
        }
        vals_product_template = {
            'name': name,
            'active': active,
            'lst_price': lst_price,
            'purchase_tax_included': purchase_tax_included,
            'sales_tax_included': sales_tax_included,
            'taxable': taxable,
            'abatement_rate': abatement_rate,
            'reverse_charge_rate': reverse_charge_rate,
            'type': product_type,
            'description': description,
            'property_account_income_id': property_item_income,
            'property_account_expense_id': property_item_expense,
            'taxes_id': [(6, 0, taxes_ids)] or None,
            'supplier_taxes_id': [(6, 0, supplier_taxes_ids)] or None,
            'description_sale': description_sale,
            'standard_price': standard_price,
            'description_purchase': description_purchase,
            'qty_available': qty_available,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
        }


        if not item_id:
            return super(quickbook_products_custom, self).create(vals_quick_product)
        else:
            account = item_id.write(vals_quick_product)
            return account

    def item_import_batch(self, model_name, backend_id, filters=None):
        """ Import Product Details. """
        arguments = 'item'
        count = 1
        record_ids = ['start']
        filters['url'] = 'item'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Item' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Item']
                for record_id in record_ids:
                    self.env['quickbook.products'].importer(arguments=arguments, backend_id=backend_id,
                                  filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.product_import_mapper(backend_id, data)

    def write(self, fields):
        res = super(quickbook_products_custom, self).write(fields)
        if self.product_odoo:
            old_qb_prod = self.env['product.template'].search([('quickbook_id', '=', self.quickbook_id)])
            for prod in old_qb_prod:
                if self.product_odoo == prod:
                    self.product_odoo.quickbook_id = self.quickbook_id
                else:
                    prod.update({'quickbook_id': False})
            self.product_odoo.quickbook_id = self.quickbook_id
        return res