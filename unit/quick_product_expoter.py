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
import logging
from .backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)

class QboProductExport(QuickExportAdapter):
    """ Models for QBO customer export """

    def get_api_method(self, method, args):
        """ get api for Product/item"""
        api_method = None
        if method == 'item':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/item?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/item?operation=update&minorversion=4'
        return api_method

    def export_product(self, method, arguments):
        """ Export Product data"""

        _logger.debug("Start calling QBO api %s", method)


        if self.quick.asset_account_ref.quickbook_id:
            asset_value = self.quick.asset_account_ref.quickbook_id
        else:
            asset_value = None
        product_type = str(arguments[1].type)
        if product_type == 'product':
            type_product = "Inventory"
            track_all = True
        elif product_type == 'consu':
            type_product = "NonInventory"
            track_all = False
        elif product_type == 'service':
            type_product = 'Service'
            track_all = False

        income_id=arguments[1].env['account.account'].search(
            [('id', '=', arguments[1].property_account_income_id.id)]).quickbook_id
        exp_id = arguments[1].env['account.account'].search(
                    [('id', '=', arguments[1].property_account_expense_id.id)]).quickbook_id
        result_dict = {
            "Name": arguments[1].name or None,
            "Description": arguments[1].description_sale or None,
            "Active": arguments[1].active,
            "UnitPrice": arguments[1].list_price or None,
            "Type": type_product,
            "IncomeAccountRef": {
                "value":  income_id if income_id else '',
            },
            "PurchaseDesc": arguments[1].description_purchase or None,
            "PurchaseCost": arguments[1].standard_price,
            "ExpenseAccountRef": {
                "value": exp_id or None,
            },
            "AssetAccountRef": {
                "value": asset_value or None,
            },
            "TrackQtyOnHand": track_all,
            "QtyOnHand": arguments[1].qty_available or 0,
            "InvStartDate": arguments[1].create_date.strftime("%Y-%m-%d %H:%M:%S"),
            'SalesTaxCodeRef': {
                "value": arguments[1].taxes_id.quickbook_id or None,
            },
        }

        if arguments[1].categ_id:
            if arguments[1].categ_id.quickbook_id==False:
                arguments[1].categ_id.backend_id=arguments[1].backend_id.id
                arguments[1].categ_id.export_product_category_data(arguments[1].backend_id)

            for i in arguments[1].categ_id:
                if i.quickbook_id:
                    result_dict.update({
                        "SubItem": True,
                        "ParentRef": {"value": str(arguments[1].categ_id.quickbook_id), "name":arguments[1].categ_id.quickbook_name if arguments[1].categ_id.quickbook_name else arguments[1].categ_id.name},
                    })
        if arguments[1].default_code:
            result_dict.update({
                "Sku": arguments[1].default_code,
            })

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Item']['sparse'],
                "Id": result['Item']['Id'],
                "SyncToken": result['Item']['SyncToken']
             })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}