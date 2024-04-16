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
from . backend_adapter import QuickExportAdapter
from ..unit.quick_invoice_exporter import QboInvoiceExport
from ..unit.backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)


class QboPaymentExport(QuickExportAdapter):
    """ Models for QBO payment export """

    def get_api_method(self, method, args):
        """ get api for payment"""
        api_method = None
        if method == 'payment':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/payment?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/payment?operation=update&minorversion=4'
        elif method == 'billpayment':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/billpayment?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/billpayment?operation=update&minorversion=4'
        return api_method

    def export_payment(self, method, arguments):
        """ Export payment data"""
        _logger.debug("Start calling QBO api %s", method)

        # for exporting invoices before exporting payments
        if not arguments[1].reconciled_invoice_ids.quickbook_id:
            backend = arguments[1].backend_id
            export = QboInvoiceExport(backend)
            method_1 = 'invoice'
            i_id = [None, arguments[1].reconciled_invoice_ids]
            res1 = export.export_invoice(method_1, i_id)
            if 'Invoice' in res1['data']:
                inv_id = res1['data']['Invoice']['Id']
                arguments[1].reconciled_invoice_ids.quickbook_id = res1['data']['Invoice']['Id']
            else:
                return {'status': res1['status'], 'data': res1['data'], 'applied_data': {'Invoice not found regarding this payment'},
                        'errors': res1 or {}, 'name': arguments[1]}

        result_dict = {
            "CustomerRef":
                {
                    "value": arguments[1].partner_id.quickbook_id,
                },
            "TotalAmt": arguments[1].reconciled_invoice_ids.amount_total,
            "Line": [
                {
                    "Amount": arguments[1].amount,
                    "LinkedTxn": [
                        {
                            "TxnId": arguments[1].reconciled_invoice_ids.quickbook_id or inv_id,
                            "TxnType": "Invoice"
                        }]
                }]
        }

        if arguments[1].currency_id:
            result_dict.update({
                "CurrencyRef": {
                   "value": str(arguments[1].currency_id.name)
                  }
                })

        method = 'payment'
        
        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Payment']['sparse'],
                "Id": result['Payment']['Id'],
                "SyncToken": result['Payment']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}

    def export_billpayment(self, method, arguments):
        """ Export billpayment Data"""
        _logger.debug("Start calling QBO api %s", method)

        result_dict = {
            "VendorRef":
                {
                    "value": arguments[1].partner_id.quickbook_id,
                },
            "TotalAmt": arguments[1].reconciled_bill_ids.amount_total,
            "PayType" : "Check" if (arguments[1].payment_method_id.name == "Manual" or arguments[1].payment_method_id.name == "Check") else "CreditCard",
            "CheckPayment" : {
                    "BankAccountRef" : {
                            "name" : arguments[1].journal_id.default_account_id.name,
                            "value" : arguments[1].journal_id.default_account_id.quickbook_id
                       }
                    },
            "Line": [
                {
                    "Amount": arguments[1].amount,
                    "LinkedTxn": [
                        {
                            "TxnId": arguments[1].reconciled_bill_ids.quickbook_id,
                            "TxnType": "Bill"
                        }]
                }]
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
                "sparse": result['BillPayment']['sparse'] if result['BillPayment']['sparse'] else None,
                "Id": result['BillPayment']['Id'],
                "SyncToken": result['BillPayment']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}