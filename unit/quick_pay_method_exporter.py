# -*- coding: utf-8 -*-
#
#
#    Techspawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY Techspawn(<http://www.Techspawn.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the Methods of the GNU Affero General Public License as
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

class QboPaymentMethodExport(QuickExportAdapter):
    """ Models for QBO PaymentMethod export """

    def get_api_method(self, method, args):
        """ get api for PaymentMethod/item"""
        api_method = None
        if method == 'paymentmethod':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/paymentmethod?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/paymentmethod?operation=update&minorversion=4'
        return api_method

    def export_payment_Method(self, method, arguments):
        """ Export PaymentMethod data"""
        _logger.debug("Start calling QBO api %s", method)

        result_dict = {
            "Name": arguments[1].name,
            "Type": arguments[1].payment_type,
        }

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['PaymentMethod']['sparse'],
                "Id": result['PaymentMethod']['Id'],
                "SyncToken": result['PaymentMethod']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}