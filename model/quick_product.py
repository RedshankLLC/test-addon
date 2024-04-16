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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
import logging
import time

from odoo import models, fields, api, _
from datetime import datetime
from requests_oauthlib import OAuth2Session
from odoo.exceptions import UserError
from ..unit.backend_adapter import QuickExportAdapter
from ..unit.quick_product_expoter import QboProductExport

_logger = logging.getLogger(__name__)


class quickbook_product_template(models.Model):
    _inherit = 'product.template'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    image_name = fields.Char('Image Name', help='QBO Image Name')
    image_id = fields.Char('Image ID', help='QBO Image ID')
    purchase_tax_included = fields.Boolean(
        string='Purchase Tax Included', default=False)
    sales_tax_included = fields.Boolean(
        string='Sales Tax Included', default=False)
    abatement_rate = fields.Char()
    reverse_charge_rate = fields.Char()
    taxable = fields.Boolean(string='Taxable', default=False)

    def get_ids(self, arguments, backend_id, filters, record_id):
        # arguments = 'customer'
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

    def product_import_mapper(self, backend_id, data):
        record = data
        product_category = ""
        _logger.info("API DATA :%s", data)

        if 'Item' in record:
            rec = record['Item']
            if 'Name' in rec:
                name = rec['Name']
            else:
                name = False
            if 'Sku' in rec:
                sku = rec['Sku']
            else:
                sku = False
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
                    property_item_income = self.env['account.account'].search(
                        [('quickbook_id', '=', rec['IncomeAccountRef']['value'])])
                    property_item_income = property_item_income.id or False
            else:
                property_item_income = False

            if 'ExpenseAccountRef' in rec:
                if rec['ExpenseAccountRef']:
                    property_item_expense = self.env['account.account'].search(
                        [('quickbook_id', '=', rec['ExpenseAccountRef']['value'])])
                    property_item_expense = property_item_expense.id or False
            else:
                property_item_expense = False

            if 'ParentRef' in rec:
                if rec['ParentRef']['name']:
                    categ_name = rec['ParentRef']['name']
                    category = categ_name.split(':')
                    if len(category) > 1:
                        category_name = category[-1]
                        search_categ = self.env['product.category'].search([('name', '=', category_name)])
                        for cat_id in search_categ:
                            if cat_id.quickbook_id:
                                product_category = cat_id.id
                    else:
                        search_categ = self.env['product.category'].search(
                            [('name', '=', rec['ParentRef']['name'])])
                        for cat_id in search_categ:
                            if cat_id.quickbook_id:
                                product_category = cat_id.id


            taxes_ids = []
            if 'SalesTaxCodeRef' in rec:
                if rec['SalesTaxCodeRef']:
                    taxes_id = self.env['account.tax'].search(
                        [('type_tax_use', '=', 'sale'), ('quickbook_id', '=', rec['SalesTaxCodeRef']['value'])])
                    if taxes_id:
                        taxes_ids.append(taxes_id.id)

            supplier_taxes_ids = []
            if 'PurchaseTaxCodeRef' in rec:
                if rec['PurchaseTaxCodeRef']:
                    supplier_taxes_id = self.env['account.tax'].search(
                        [('type_tax_use', '=', 'purchase'), ('quickbook_id', '=', rec['PurchaseTaxCodeRef']['value'])])
                    if supplier_taxes_id:
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
        warehouse = self.env['stock.warehouse'].search([('code', '=', 'WH')])

        vals = {
            'name': name,
            'default_code': sku,
            'active': active,
            'list_price': lst_price,
            'purchase_tax_included': purchase_tax_included,
            'sales_tax_included': sales_tax_included,
            'taxable': taxable,
            'abatement_rate': abatement_rate,
            'reverse_charge_rate': reverse_charge_rate,
            'type': product_type,
            'description': description,
            'property_account_income_id': property_item_income,
            'taxes_id': [(6, 0, taxes_ids)] or None,
            'supplier_taxes_id': [(6, 0, supplier_taxes_ids)] or None,
            'description_sale': description_sale,
            'standard_price': standard_price,
            'description_purchase': description_purchase,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,

        }

        # if import_from_other_module = True:
        item_id = self.env['product.template'].search(
            [('quickbook_id', '=', quickbook_id), ('backend_id', '=', backend_id),('active', '=', active)], limit=1)

        if product_category:
            vals.update({'categ_id': product_category})
        if product_type =='product':
            vals.update({
                'qty_available': qty_available,
                'property_account_expense_id': property_item_expense,
            })
        if not vals['active']:
            archived_name=str(name).split("(")

            vals.update({
                'name': archived_name[0],
            })
        if not item_id:
            try:
                if __name__=='main':
                    if rec['Type'] == 'Inventory':
                        p_id = super(quickbook_product_template, self).create(vals)
                        p_id.env.cr.commit()
                        QuickExportAdapter.create_or_update_job(self, 'Import Item', 200, backend_id, data, vals, data['Item']['Id'], p_id.id)
                        varient_id = self.env['product.product'].search([('product_tmpl_id','=',p_id.id),('active', '=', active)],limit=1)
                        stock_quant_obj=self.env['stock.quant']
                        if 'QtyOnHand' in rec:
                            stock_quant_obj.with_context(inventory_mode=True).create({
                                'product_id': varient_id.id,
                                'inventory_quantity': rec['QtyOnHand'],
                                'location_id': warehouse.lot_stock_id.id,
                            })
                            stock_quant_id = stock_quant_obj.search([('product_id','=', varient_id.id)])
                            stock_quant_id.action_apply_inventory()
                        return p_id
                    if rec['Type'] == 'Service':
                        super(quickbook_product_template, self.env['product.template']).create(vals)
                        p_id = super(quickbook_product_template, self.env['product.template']).create(vals)
                        p_id.env.cr.commit()
                        QuickExportAdapter.create_or_update_job(self, 'Import Item', 200, backend_id, data, vals, data['Item']['Id'], p_id.id)
                        return p_id
                else:
                    if rec['Type'] == 'Inventory':
                        p_id = super(quickbook_product_template, self.env['product.template']).create(vals)
                        p_id.env.cr.commit()
                        QuickExportAdapter.create_or_update_job(self, 'Import Item', 200, backend_id, data, vals, data['Item']['Id'], p_id.id)
                        varient_id = self.env['product.product'].search([('product_tmpl_id', '=', p_id.id),('active', '=', active)], limit=1)
                        if p_id:
                            if p_id.product_variant_ids:
                                for variant_id in p_id.product_variant_ids:
                                    self.env['stock.quant'].with_context(inventory_mode=True).create({
                                        'product_id': variant_id.id,
                                        'location_id': warehouse.lot_stock_id.id,
                                        'inventory_quantity': rec['QtyOnHand'],
                                    })
                            stock_quant_obj = self.env['stock.quant'].search([('product_id','=', varient_id.id)])
                            stock_quant_obj.action_apply_inventory()
                        return p_id
                    if rec['Type'] == 'Service':
                        p_id = super(quickbook_product_template, self.env['product.template']).create(vals)
                        p_id.env.cr.commit()
                        QuickExportAdapter.create_or_update_job(self, 'Import Item', 200, backend_id, data, vals, data['Item']['Id'], p_id.id)
                        return p_id
            except:
                QuickExportAdapter.create_or_update_job(self, 'Import Item', 400, backend_id, data, vals,
                                                        data['Item']['Id'], item_id.id)
                _logger.info(_("Issue while importing Product " + vals.get(
                    'name') + ". Please check if there are any missing values in Quickbooks."))
        else:
            if rec['Type'] == 'Inventory':
                if 'QtyOnHand' in rec:
                    variant_id = self.env['product.product'].search([('product_tmpl_id', '=', item_id.id),('active', '=', active)], limit=1)
                    self.env['stock.quant'].with_context(inventory_mode=True).create({
                        'product_id': variant_id.id,
                        'inventory_quantity': rec['QtyOnHand'],
                        'location_id': warehouse.lot_stock_id.id })
                    stock_quant_obj = self.env['stock.quant'].search([('product_id', '=', variant_id.id)])
                    stock_quant_obj.action_apply_inventory()
            account = item_id.write(vals)
            QuickExportAdapter.create_or_update_job(self, 'Import Item', 200, backend_id, data, vals,
                                                    data['Item']['Id'], item_id.id)
            return account

    def item_import_batch_new(self, model_name, backend_id, filters=None):
        """ Import Product Details. """
        arguments = 'item'
        count = 1
        filters['url'] = 'item'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Item' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Item']
                for record_id in record_ids:
                    self.env['product.template'].importer(arguments=arguments, backend_id=backend_id,
                                                          filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.product_import_mapper(backend_id, data)

    def sync_product(self):
        """ Export the inventory configuration and quantity of a product. """
        for backend in self.backend_id:
            self.export_product_data(backend)
        return

    def sync_product_multiple(self):
        for rec in self:
            for backend in rec.backend_id:
                rec.export_product_data(backend)
        return

    def export_product_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['product.template'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'item'
        arguments = [mapper.quickbook_id or None, self]
        export = QboProductExport(backend)
        res = export.export_product(method, arguments)
        # code for logger
        if res:
            if 'Item' in res['data']:
                qb_id = res['data']['Item']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Item', res['status'], backend.id,
                              res['data'] if res['data'] else res['errors'], res['applied_data'], qb_id,
                              self.id)
        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                          code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + errors['Detail'] \
                          +'\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Export product: "+details))

    @api.model
    def default_get(self, fields):
        res = super(quickbook_product_template, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res
