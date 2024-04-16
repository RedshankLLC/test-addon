# -*- coding: utf-8 -*-
#
#
#    TechSpawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY TechSpawn(<http://www.techspawn.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the departments of the GNU Affero General Public License as
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
import time
from datetime import datetime
from odoo.exceptions import UserError
from odoo import models, fields, api, _
from requests_oauthlib import OAuth2Session
from ..unit.quick_department_exporter import QboDepartmentExport
from ..unit.backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)

class quickbook_department(models.Model):

    _inherit = 'hr.department'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')


    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            if backend.data == 'custom':
                sd = str(backend.start_date.year) +'-'+str(backend.start_date.month).zfill(2)+'-'+str(backend.start_date.day).zfill(2)
                ed = str(backend.end_date.year) +'-'+str(backend.end_date.month).zfill(2)+'-'+str(backend.end_date.day).zfill(2)
                data = headeroauth.get(backend.location + backend.company_id +"/query?query=select ID from "+ arguments +" Where Metadata.CreateTime>'" + str(sd) +"' and Metadata.CreateTime<'"+ str(ed)+"'" + ' MAXRESULTS ' + str(1000) +'&minorversion=54', headers=headers)
            elif backend.data == 'all':
                if backend.company_id:
                    data = headeroauth.get(backend.location + backend.company_id +
                                   method + arguments + '%20STARTPOSITION%20'+ str(backend.record_no) + '%20MAXRESULTS%20' + str(500) + '&minorversion=54', headers=headers)
                else:
                    raise UserError(_('Please add company ID'))
        else:
            data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=4', headers=headers)
            if data.status_code == 429:
                self.env.cr.commit()
                time.sleep(60)
                data = headeroauth.get(backend.location + backend.company_id +
                                   '/' + arguments + '/' + str(record_id) + '?minorversion=4', headers=headers)
        if data:
            if isinstance(arguments, list):
                while arguments and arguments[-1] is None:
                    arguments.pop()
            start = datetime.now()
            try:
                if 'false' or 'true' or 'null'in data.content:
                    # converting str data contents to bytes
                    data1 = bytes(data.content)
                    # decoding data contents
                    data_decode = data.content.decode('utf-8')
                    # encoding data contents
                    result = data_decode.replace('false', 'False').encode('utf-8')

                    data_decode_one = result.decode('utf-8')
                    result = data_decode_one.replace('true', 'True').encode('utf-8')

                    data_decode_two = result.decode('utf-8')
                    result = data_decode_two.replace('null', 'False')

                    result = eval(result)
                else:
                    result = eval(data.content)
            except:
                _logger.error("api.call(%s, %s) failed", method, arguments)
            else:
                _logger.debug("api.call(%s, %s) returned %s in %s seconds",
                              method, arguments, result,
                              (datetime.now() - start).seconds)
            return result

    def department_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Department' in record:
            rec = record['Department']
            if 'Name' in rec:
                name = rec.get('Name')
            else:
                name = None
            if 'SubDepartment' in rec:
                if rec.get('SubDepartment') == True:
                    partner_id = rec.get('ParentRef')
                    partner_id = self.env['hr.department'].search(
                        [('quickbook_id', '=', partner_id.get('value'))])
                    parent_id = partner_id.id
                else:
                    parent_id = False
            else:
                parent_id = False

            if 'Active' in rec:
                active = rec['Active']
            else:
                active = False

            if rec['Id']:
                quickbook_id = rec['Id']
        dept_id = self.env['hr.department'].search(
            [('quickbook_id', '=', quickbook_id),
             ('backend_id', '=', backend_id)])
        vals = {
            'name': name,
            'active': active,
            'parent_id': parent_id,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
        }
        if not dept_id:
            try:
                a =  super(quickbook_department, self).create(vals)
                a.env.cr.commit()
                QuickExportAdapter.create_or_update_job(self, 'Import Department', 200, backend_id, data, vals,
                                                        data['Department']['Id'], a.id)
                return a
            except:
                QuickExportAdapter.create_or_update_job(self, 'Import Department', 400, backend_id, data, vals,
                                                        data['Department']['Id'], dept_id.id)
                raise UserError(_("Issue while importing Employee " + vals.get(
                    'name') + ". Please check if there are any missing values in Quickbooks."))
        else:
            dep = dept_id.write(vals)
            QuickExportAdapter.create_or_update_job(self, 'Import Department', 200, backend_id, data, vals,
                                                    data['Department']['Id'], dept_id.id)
            return dep

    def department_import_batch(self, model_name, backend_id, filters=None):
        """ Import Customer Details. """
        arguments = 'department'
        count = 1
        record_ids = ['start']
        filters['url'] = 'department'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Department' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Department']
                for record_id in record_ids:
                    self.env['hr.department'].importer(arguments=arguments, backend_id=backend_id, filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self._import_dependencies(data, filters, backend_id)
            self.department_import_mapper(backend_id, data)

    def sync_department(self):
        for backend in self.backend_id:
            self.export_department_data(backend)
        return

    def sync_employeedepartment_multiple(self):
        for rec in self:
            for backend in rec.backend_id:
               rec.export_department_data(backend)
        return

    def export_department_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['hr.department'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'department'
        arguments = [mapper.quickbook_id or None, self]
        export = QboDepartmentExport(backend)
        res = export.export_department(method, arguments)
        # code for logger
        if res:
            if 'Department' in res['data']:
                qb_id = res['data']['Department']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Department', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)
        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Department']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Department']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Department']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                    code + '\n' + 'Name: '+ str(name.name) + '\n' + 'Detail: ' + errors['Detail'] \
                          + '\n' + 'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Export Dept. :" +details))

    def _import_dependencies(self, data, filters, backend_id):
        """ Import the dependencies for the record"""
        record = data
        arguments = 'department'
        rec = record['Department']
        if rec.get('ParentRef'):
            parent_id = rec['ParentRef']['value']
            values = self.get_ids(arguments, backend_id,
                                  filters, record_id=int(parent_id))
            if values:
                self.department_import_mapper(backend_id, data=values)

    @api.model
    def default_get(self,fields):
        res=super(quickbook_department,self).default_get(fields)
        ids=self.env['qb.backend'].search([]).id
        res['backend_id']=ids
        return res
