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

class QboCustomerExport(QuickExportAdapter):
    """ Models for QBO customer export """

    def get_api_method(self, method, args):
        """ get api for customer"""
        api_method = None
        if method == 'customer':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/customer?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/customer?operation=update&minorversion=4'
        elif method == 'vendor':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/vendor?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/vendor?operation=update&minorversion=4'
        return api_method

    def get_shipping_address(self, shipping_ids):
        """ return shipping address od customer """
        shipping = []
        if shipping_ids:
            for shipping_id in shipping_ids:
                shipping.append({
                    "first_name": shipping_id.ship_first_name or None,
                    "last_name": shipping_id.ship_last_name or None,
                    "address_1": shipping_id.ship_address1 or None,
                    "address_2": shipping_id.ship_address2 or None,
                    "city": shipping_id.ship_city or None,
                    "state": shipping_id.ship_state.code or None,
                    "postcode": shipping_id.ship_zip or None,
                    "country": shipping_id.ship_country.code or None,
                })
            return shipping[0]
        return shipping

    def export_customer(self, method, arguments):
        """ Export customer data"""
        _logger.debug("Start calling QBO api %s", method)
        result_dict = {
            "BillAddr": {
                "Line1": arguments[1].street or None,
                "Line2": arguments[1].street2 or None,
                "City": arguments[1].city or None,
                "Country": arguments[1].country_id.name or None,
                "CountrySubDivisionCode": arguments[1].state_id.name or None,
                "PostalCode": arguments[1].zip or None,
                
            },
            "Title": arguments[1].title.name or None,
            "GivenName": arguments[1].first_name or None,
            "FamilyName": arguments[1].last_name or None,
            "CompanyName": arguments[1].company_name or None,
            "DisplayName": arguments[1].name,
            "PrimaryPhone": {
                "FreeFormNumber": arguments[1].phone or None,
            },
            "PrimaryEmailAddr": {
                "Address": arguments[1].email or None,
            },
            "Mobile": {
                "FreeFormNumber": arguments[1].mobile or None,
            },
            "WebAddr": {
                "URI": arguments[1].website or None,
            },
            "SalesTermRef": {
                "value": arguments[1].property_payment_term_id.quickbook_id or None,
            },

        }

        if arguments[1].property_product_pricelist:
            result_dict.update({
                "CurrencyRef": {
                   "value": str(arguments[1].property_product_pricelist.currency_id.name)
                  }
                })

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Customer']['sparse'],
                "Id": result['Customer']['Id'],
                "SyncToken": result['Customer']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}

    def export_vendor(self, method, arguments):
        """ Export Vendor Data"""
        _logger.debug("Start calling QBO api %s", method)

        result_dict = {
            "BillAddr": {
                "Line1": arguments[1].street or None,
                "Line2": arguments[1].street2 or None,
                "City": arguments[1].city or None,
                "Country": arguments[1].country_id.name or None,
                "CountrySubDivisionCode": arguments[1].state_id.name or None,
                "PostalCode": arguments[1].zip or None,
            },
            "Title": arguments[1].title.name or None,
            "GivenName": arguments[1].first_name or None,
            "FamilyName": arguments[1].last_name or None,
            "CompanyName": arguments[1].company_name or None,
            "DisplayName": arguments[1].name,
            "PrimaryPhone": {
                "FreeFormNumber": arguments[1].phone or None,
            },
            "PrimaryEmailAddr": {
                "Address": arguments[1].email or None,
            },
            "Mobile": {
                "FreeFormNumber": arguments[1].mobile or None,
            },
            "WebAddr": {
                "URI": arguments[1].website or None,
            },
            "TermRef": {
                "value": arguments[1].property_supplier_payment_term_id.quickbook_id or None,
            },

        }

        if arguments[1].property_purchase_currency_id:
            result_dict.update({
                "CurrencyRef": {
                   "value": str(arguments[1].property_purchase_currency_id.name)
                  }
                })

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Vendor']['sparse'],
                "Id": result['Vendor']['Id'],
                "SyncToken": result['Vendor']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict,'errors': errors_dict or {}, 'name': arguments[1]}