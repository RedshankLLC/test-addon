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


class QboPaymentTermExport(QuickExportAdapter):
    """ Models for QBO PaymentTerm export """

    def get_api_method(self, method, args):
        """ get api for PaymentTerm/item"""
        api_method = None
        if method == 'term':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/term?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/term?operation=update&minorversion=4'
        return api_method

    def export_payment_term(self, method, arguments):
        """ Export PaymentTerm data"""
        _logger.debug("Start calling QBO api %s", method)

        if arguments[1]:
            if arguments[1].line_ids[0].days == 0:
                typed = 'DATE_DRIVEN'
                due_date = 0
            else:
                typed = 'STANDARD'
                due_date = arguments[1].line_ids[0].days

        result_dict = {
            "Name": arguments[1].name,
            "Active": arguments[1].active,
            "Type": typed,
            "DueDays": due_date,
        }
        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
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