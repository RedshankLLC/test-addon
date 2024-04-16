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


class QboPurchaseExport(QuickExportAdapter):
    """ Models for QBO customer export """

    def get_api_method(self, method, args):
        """ get api for Product/item"""
        api_method = None
        if method == 'purchaseorder':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/purchaseorder?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/purchaseorder?operation=update&minorversion=4'
        return api_method

    def export_purchase_order(self, method, arguments):
        """ Export purchase order data"""
        _logger.debug("Start calling QBO api %s", method)

        temp_array = []
        ptaxcodeqb_id = None
        if arguments[1].order_line:
            for order_line in arguments[1].order_line:
                product_template_id = arguments[1].env['product.template'].search(
                    [('name', '=', order_line.product_id.name)],limit=1)
                if order_line.taxes_id:
                    taxcoderef = "TAX"
                    ptaxcodeqb_id = order_line.taxes_id.quickbook_id
                else:
                    taxcoderef = "NON"

                temp = {
                    "Description": order_line.name or None,
                    "Amount": order_line.price_subtotal,
                    "DetailType": "ItemBasedExpenseLineDetail",
                    "ItemBasedExpenseLineDetail": {
                        "ItemRef": {
                            "value": product_template_id.quickbook_id or None,
                        },
                        "UnitPrice": order_line.price_unit,
                        "Qty": order_line.product_qty,
                        "TaxCodeRef": {
                            "value": taxcoderef,
                        },
                    },
                    "Id": order_line.quickbook_id or None,
                }
                if not arguments[1].env.company.partner_id.country_id.code is 'US':
                    temp.get("ItemBasedExpenseLineDetail").get('TaxCodeRef').update({'value': ptaxcodeqb_id })
                temp_array.append(temp)
        result_dict = {
            "DocNumber": arguments[1].name,
            "POEmail": {
                "Address": str(arguments[1].partner_id.email)
            },
            "Line": temp_array,
            "TxnTaxDetail": {
                "TxnTaxCodeRef": {
                    "value": ptaxcodeqb_id or None
                },
            },
            "VendorRef": {
                "value": arguments[1].partner_id.quickbook_id,
                "name": arguments[1].partner_id.name
            },
        }

        if arguments[1].currency_id:
            result_dict.update({
                "CurrencyRef": {
                   "value": str(arguments[1].currency_id.name)
                  }
                })

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['PurchaseOrder']['sparse'],
                "Id": result['PurchaseOrder']['Id'],
                "SyncToken": result['PurchaseOrder']['SyncToken'], })

        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict,'errors': errors_dict or {}, 'name': arguments[1]}