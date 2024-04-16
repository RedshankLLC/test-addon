import logging
import time

from datetime import datetime
from odoo import models, fields, api
from odoo.exceptions import UserError

from requests_oauthlib import OAuth2Session
from ..unit.quick_employee_exporter import QboEmployeeExport

_logger = logging.getLogger(__name__)

class quickbook_employees_custom(models.Model):
    _name = 'quickbook.employees'
    _description ='Quickbook Employees'

    name = fields.Char(required=False)
    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=True, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    employee_odoo = fields.Many2one('hr.employee', readonly=False, domain="[('quickbook_id','=',False)]")
    first_name = fields.Char()
    middle_name = fields.Char()
    last_name = fields.Char()
    billable_time = fields.Boolean()
    hired_date = fields.Date('Hired Date', readonly=False, required=False)
    released_date = fields.Date(
        'Released Date', readonly=False, required=False)
    bill_rate = fields.Float()
    mobile_phone = fields.Char()
    work_email = fields.Char()
    work_phone = fields.Char()

    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        if not record_id:
            data = headeroauth.get(backend.location + backend.company_id +
                                   method + arguments + '%20STARTPOSITION%20'+ str(filters['count']) + '%20MAXRESULTS%20' + str(1000) + '&minorversion=4', headers=headers)
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
                if 'false' or 'true' or 'null' in data.content:
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

    def employee_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Employee' in record:
            rec = record['Employee']

            if rec['DisplayName']:
                name = rec['DisplayName']
            else:
                name = rec.get('GivenName') + '' + rec.get('FamilyName')

            if 'GivenName' in rec:
                first_name = rec.get('GivenName')
            else:
                first_name = None

            if 'FamilyName' in rec:
                last_name = rec.get('FamilyName')
            else:
                last_name = None

            if 'MiddleName' in rec:
                middle_name = rec.get('MiddleName')
            else:
                middle_name = None
            if 'PrimaryPhone' in rec:
                phone = rec['PrimaryPhone']
                phone = phone.get('FreeFormNumber')
            else:
                phone = None

            if 'PrimaryPhone' in rec:
                phone = rec['PrimaryPhone']
                phone = phone.get('FreeFormNumber')
            else:
                phone = None

            if 'PrimaryEmailAddr' in rec:
                email = rec['PrimaryEmailAddr']
                email = email.get('Address')
            else:
                email = None

            if 'Mobile' in rec:
                mobile = rec['Mobile']
                mobile = mobile.get('FreeFormNumber')
            else:
                mobile = None

            if rec.get('Gender') == 'Male':
                gender = 'male'
            elif rec.get('Gender') == 'Female':
                gender = 'female'
            else:
                gender = None

            if rec['Id']:
                quickbook_id = rec['Id']
        partner_id = self.env['quickbook.employees'].search([('quickbook_id', '=', quickbook_id),
                                                             ('backend_id', '=', backend_id)])

        vals_quick_employees = {
            'name': name or rec.get('DisplayName'),
            'first_name': first_name or rec.get('GivenName'),
            'last_name': last_name or rec.get('FamilyName'),
            'work_phone': phone,
            'work_email': email,
            'mobile_phone': mobile,
            'billable_time': rec.get('BillableTime'),
            'hired_date': rec.get('HiredDate'),
            'released_date': rec.get('ReleasedDate'),
            'bill_rate': rec.get('BillRate'),
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
        }
        vals_hr_employee = {
            'name': name or rec.get('DisplayName'),
            'first_name': first_name or rec.get('GivenName'),
            'last_name': last_name or rec.get('FamilyName'),
            'gender': gender,
            'active': rec.get('Active'),
            'work_phone': phone,
            'work_email': email,
            'birthday': rec.get('BirthDate'),
            'barcode': rec.get('EmployeeNumber'),
            'identification_id': rec.get('SSN'),
            'mobile_phone': mobile,
            'billable_time': rec.get('BillableTime'),
            'hired_date': rec.get('HiredDate'),
            'released_date': rec.get('ReleasedDate'),
            'bill_rate': rec.get('BillRate'),
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
        }

        if not partner_id:
            return super(quickbook_employees_custom, self).create(vals_quick_employees)
        else:
            partner = partner_id.write(vals_quick_employees)
            return partner

    def employee_import_batch(self, model_name, backend_id, filters=None):
        """ Import Employee Details. """
        arguments = 'employee'
        count = 1
        record_ids = ['start']
        filters['url'] = 'employee'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Employee' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Employee']
                for record_id in record_ids:
                    self.env['quickbook.employees'].importer(arguments=arguments, backend_id=backend_id,
                                                                  filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.employee_import_mapper(backend_id, data)

    def write(self, fields):
        res = super(quickbook_employees_custom, self).write(fields)
        if self.employee_odoo:
            old_qb_emp = self.env['hr.employee'].search([('quickbook_id', '=', self.quickbook_id)])
            for emp in old_qb_emp:
                if self.employee_odoo == emp:
                    self.employee_odoo.quickbook_id = self.quickbook_id
                else:
                    emp.update({'quickbook_id': False})
            self.employee_odoo.quickbook_id = self.quickbook_id
        return res