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


class QboDepartmentExport(QuickExportAdapter):
    """ Models for QBO Employee export """

    def get_api_method(self, method, args):
        """ get api for department"""
        api_method = None
        if method == 'department':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/department?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/department?operation=update&minorversion=4'

        return api_method

    def export_department(self, method, arguments):
        """ Export department data"""
        _logger.debug("Start calling QBO api %s", method)

        if arguments[1].parent_id:
            SubDepartment = True
            result_dict = {
                'Name': arguments[1].name,
                'SubDepartment': SubDepartment or None,
                'FullyQualifiedName': arguments[1].name,
                'Active': arguments[1].active,
                'ParentRef': {
                    "value": arguments[1].parent_id.quickbook_id or None
                },
            }
        else:
            SubDepartment = False
            result_dict = {
                'Name': arguments[1].name,
                'SubDepartment': SubDepartment or None,
                'FullyQualifiedName': arguments[1].name,
                'Active': arguments[1].active,
            }

        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Department']['sparse'],
                "Id": result['Department']['Id'],
                "SyncToken": result['Department']['SyncToken'], })

        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict, 'errors': errors_dict or {}, 'name': arguments[1]}