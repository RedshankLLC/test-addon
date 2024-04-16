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


class QboTaxExport(QuickExportAdapter):
    """ Models for QBO taxservice export """

    def get_api_method(self, method, args):
        """ get api for taxservice"""

        api_method = None
        if method == 'taxservice/taxcode':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/taxservice/taxcode?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/taxservice/taxcode?operation=update&minorversion=4'

        return api_method

    def export_tax(self, method, arguments):
        """ Export taxservice data"""
        _logger.debug("Start calling QBO api %s", method)
        
        temp_array = []
        if arguments[1].children_tax_ids:
            for order_line in arguments[1].children_tax_ids:
                if order_line.type_tax_use == 'sale':
                    apply_on = 'Sales'
                else:
                    apply_on = 'Purchase'
                temp = {
                    "TaxRateName": order_line.name,
                    "RateValue": order_line.amount,
                    "TaxAgencyId": "1",
                    "TaxApplicableOn": apply_on,
                }
                temp_array.append(temp)

        elif arguments[1]:
                if arguments[1].type_tax_use == 'sale':
                    apply_on = 'Sales'
                else:
                    apply_on = 'Purchase'
                temp = {
                    "TaxRateName": arguments[1].name,
                    "RateValue": arguments[1].amount,
                    "TaxAgencyId": "1",
                    "TaxApplicableOn": apply_on,
                }
                temp_array.append(temp)

        result_dict = {
            "TaxCode": 'QBO' + arguments[1].name,
            "TaxRateDetails": temp_array
        }

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = requests.get(ris, auth=headeroauth, headers=headers)
            result_dict.update({
                "sparse": result['Term']['sparse'],
                "Id": result['Term']['Id'],
                "SyncToken": result['Term']['SyncToken'], })
        res = self.export(method, result_dict, arguments)

        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict,'errors': errors_dict or {}, 'name': arguments[1]}