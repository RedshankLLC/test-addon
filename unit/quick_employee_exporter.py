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


class QboEmployeeExport(QuickExportAdapter):
    """ Models for QBO Employee export """

    def get_api_method(self, method, args):
        """ get api for employee"""
        api_method = None
        if method == 'employee':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/employee?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/employee?operation=update&minorversion=4'

        return api_method

    def export_employee(self, method, arguments):

        """ Export employee data"""
        _logger.debug("Start calling QBO api %s", method)

        if arguments[1].gender == 'male':
            gender = 'Male'
        elif arguments[1].gender == 'female':
            gender = 'Female'
        else:
            gender = None
        result_dict = {
            "PrimaryAddr": {
                "Line1": arguments[1].address_id.street or None,
                "City": arguments[1].address_id.city or None,
                "Country": arguments[1].address_id.country_id.name or None,
                "PostalCode": arguments[1].address_id.zip or None,
            },
            "BillableTime": arguments[1].billable_time or None,
            "BillRate": arguments[1].bill_rate or None,
            "BirthDate": arguments[1].birthday.strftime('%Y-%m-%d') if arguments[1].birthday else None,
            "Gender": gender,
            "HiredDate": arguments[1].hired_date.strftime('%Y-%m-%d') if arguments[1].hired_date else None,
            "ReleasedDate": arguments[1].released_date or None,
            "GivenName": arguments[1].first_name or None,
            "MiddleName": arguments[1].middle_name or None,
            "FamilyName": arguments[1].last_name or None,
            "DisplayName": arguments[1].name,
            "PrintOnCheckName": arguments[1].name,
            "Active": arguments[1].active,
            "PrimaryPhone": {
                "FreeFormNumber": arguments[1].work_phone or None
            },
            "Mobile": {
                "FreeFormNumber": arguments[1].mobile_phone or None
            },
            "PrimaryEmailAddr": {
                "Address": arguments[1].work_email or None
            }
        }
        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Employee']['sparse'],
                "Id": result['Employee']['Id'],
                "SyncToken": result['Employee']['SyncToken'], })
        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}