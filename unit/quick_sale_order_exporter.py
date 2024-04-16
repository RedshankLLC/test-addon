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


class QboSalesOrderExport(QuickExportAdapter):
    """ Models for QBO customer export """

    def get_api_method(self, method, args):
        """ get api for Product/item"""
        api_method = None
        if method == 'salesreceipt':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/salesreceipt?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/salesreceipt?operation=update&minorversion=4'
        else:
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/estimate?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/estimate?operation=update&minorversion=4'
        return api_method

    def export_sales_receipt(self, method, arguments):
        """ Export Product data"""
        _logger.debug("Start calling QBO api %s", method)

        temp_array = []
        staxcodeqb_id = None
        lst = []
        sum = 0
        total_amt = 0

        for i in arguments[1].order_line:
            

            discount_value =(i.product_uom_qty *i.price_unit) * i.discount/100
            lst.append(discount_value)
            sum = sum + discount_value
            final = i.product_uom_qty *i.price_unit
            total_amt = total_amt + final
        
        if arguments[1].order_line:
            for order_line in arguments[1].order_line:
                product_template_id = arguments[1].env['product.template'].search(
                    [('name', '=', order_line.product_id.name)],limit=1)
                if order_line.tax_id:
                    taxcoderef = "TAX"
                    staxcodeqb_id = order_line.tax_id.quickbook_id
                else:
                    taxcoderef = "NON"

                amount = order_line.product_uom_qty * order_line.price_unit

                temp = {
                    "Description": order_line.name or None,
                    "Amount": amount,
                    "DetailType": "SalesItemLineDetail",
                    "SalesItemLineDetail": {
                        "ItemRef": {
                            "value": product_template_id.quickbook_id or None,
                        },
                        "UnitPrice": order_line.price_unit or None,
                        "Qty": order_line.product_uom_qty or None,
                        "TaxCodeRef": {
                            "value": taxcoderef,
                        },
                    },
                    "LineNum": order_line.sequence,
                    "Id": order_line.quickbook_id or None,
                }

                true = True
                false = False
                a =  arguments[1].env['account.account'].search([('name','=','Discounts')]).quickbook_id
                dics = {"DetailType": "DiscountLineDetail", "Amount": sum,"DiscountLineDetail": {"DiscountAccountRef": {"name": 'Discounts given',"value": a or None},"PercentBased": false}}

                if not arguments[1].env.company.partner_id.country_id.code is 'US':
                    temp.get("SalesItemLineDetail").get('TaxCodeRef').update({'value': staxcodeqb_id })
                temp_array.append(temp)
                temp_array.append(dics)
        result_dict = {
            "Line": temp_array,
            "TxnTaxDetail": {
                "TxnTaxCodeRef": {
                    "value": staxcodeqb_id or None
                },
            },
            "CustomerRef": {
                "value": arguments[1].partner_id.quickbook_id,
            },

            "TxnDate": arguments[1].date_order.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if arguments[1].state:
            if arguments[1].state == 'draft':
                result_dict.update({"TxnStatus": "Pending"})
            elif arguments[1].state == 'sale':
                result_dict.update({"TxnStatus": "Accepted"})
            elif arguments[1].state == 'cancel':
                result_dict.update({"TxnStatus": "Rejected"})
            else:
                result_dict.update({"TxnStatus": "Pending"})
        if arguments[1].pricelist_id:
            result_dict.update({
                "CurrencyRef": {
                   "value": str(arguments[1].pricelist_id.currency_id.name)
                  }
                })

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            if 'Estimate' in result:
                result_dict.update({
                    "sparse": result['Estimate']['sparse'],
                    "Id": result['Estimate']['Id'],
                    "SyncToken": result['Estimate']['SyncToken'], })
            else:
                result_dict.update({
                    "sparse": result['SalesReceipt']['sparse'],
                    "Id": result['SalesReceipt']['Id'],
                    "SyncToken": result['SalesReceipt']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}