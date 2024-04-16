import logging
import time

from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from requests_oauthlib import OAuth2Session

_logger = logging.getLogger(__name__)

class quickbook_vendors_custom(models.Model):
    _name = 'quickbook.vendors'
    _description = 'Quickbook Vendors'

    name = fields.Char(required=False)
    quickbook_id = fields.Char(string='ID on Quickbook', readonly=True)
    vendor_odoo = fields.Many2one('res.partner', readonly=False, domain="[('quickbook_id','=',False),('supplier','=',True)]")
    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    city = fields.Char(string='City')
    street = fields.Char(string='Address')
    street2 =fields.Char(string='Street2')
    zip = fields.Char(string='Zip')
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    website = fields.Char(string='Website')
    customer = fields.Boolean(string='Is a customer')
    supplier = fields.Boolean(string='Is a vendor')
    property_payment_term_id = fields.Many2one('account.payment.term',readonly=False)
    property_supplier_payment_term_id = fields.Many2one('account.payment.term', readonly=False)

    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token, 'content-type': 'application/json',
                   'accept': 'application/json'}
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
                data = headeroauth.get(
                    backend.location + backend.company_id + '/' + arguments + '/' + str(record_id) + '?minorversion=4',
                    headers=headers)

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

    def vendor_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        if 'Customer' in record:
            supplier = False
            customer = True
            rec = record['Customer']
            if 'GivenName' and 'FamilyName' in rec:
                first_name = rec['GivenName'] or None
                last_name = rec['FamilyName'] or None
                name = rec['DisplayName'] or None
            else:
                name = rec['DisplayName'] or None
                first_name = False or None
                last_name = False or None

            if 'CompanyName' in rec:
                if rec['CompanyName']:
                    company_name = rec['CompanyName']
            else:
                company_name = None

            if 'PrimaryEmailAddr' in rec:
                if rec['PrimaryEmailAddr']:
                    email = rec['PrimaryEmailAddr']['Address'] or None
            else:
                email = None
            if 'WebAddr' in rec:
                if rec['WebAddr']:
                    website = rec['WebAddr']['URI'] or None
            else:
                website = False or None

            if 'PrimaryPhone' in rec:
                if rec['PrimaryPhone']:
                    phone = rec['PrimaryPhone']['FreeFormNumber'] or None
            else:
                phone = None
            if 'BillAddr' in rec:
                bil = rec['BillAddr']
                if bil:
                    street = bil['Line1'] or None
                    street2 = bil.get('Line2') or None
                    city = bil.get('City') or None
                    zip = bil.get('PostalCode') or None
                    if 'Country' in bil and bil['Country']:
                        country_id = self.env['res.country'].search(
                            [('name', '=ilike', bil['Country'])])
                        country_id = country_id.id
                    else:
                        country_id = False
                    if 'CountrySubDivisionCode' in bil and bil['CountrySubDivisionCode']:
                        state_id = self.env['res.country.state'].search(
                            [('name', '=ilike', bil['CountrySubDivisionCode'])])
                        if len(state_id) > 1:
                            state_id = state_id[0].id
                        else:
                            state_id = state_id.id
                    else:
                        state_id = False
            else:
                street = False or None
                street2 = False or None
                city = False or None
                zip = False or None
                state_id = False
                country_id = False

            if 'SalesTermRef' in rec:
                if rec['SalesTermRef']:
                    payment_term = self.env['account.payment.term'].search(
                        [('quickbook_id', '=', rec['SalesTermRef']['value'])])
                    payment_term = payment_term.id
                    supplier_payment_term = False
            else:
                payment_term = False
                supplier_payment_term = False

            if rec['Id']:
                quickbook_id = rec['Id']

        elif 'Vendor' in record:
            supplier = True
            customer = False
            rec = record['Vendor']
            if 'GivenName' and 'FamilyName' in rec:
                first_name = rec['GivenName'] or None
                last_name = rec['FamilyName'] or None
                name = rec['DisplayName'] or None
            else:
                name = rec['DisplayName'] or None
                first_name = False or None
                last_name = False or None
            if 'CompanyName' in rec:
                if rec['CompanyName']:
                    company_name = rec['CompanyName']
            else:
                company_name = None

            if 'PrimaryEmailAddr' in rec:
                if rec['PrimaryEmailAddr']:
                    email = rec['PrimaryEmailAddr']['Address'] or None
            else:
                email = None
            if 'WebAddr' in rec:
                if rec['WebAddr']:
                    website = rec['WebAddr']['URI'] or None
            else:
                website = False or None

            if 'PrimaryPhone' in rec:
                if rec['PrimaryPhone']:
                    phone = rec['PrimaryPhone']['FreeFormNumber'] or None
            else:
                phone = None
            if 'BillAddr' in rec:
                bil = rec['BillAddr']
                if bil:
                    street = bil.get('Line1') or None
                    street2 = bil.get('Line2') or None
                    city = bil.get('City') or None
                    zip = bil.get('PostalCode') or None
                    if 'Country' in bil and bil['Country']:
                        country_id = self.env['res.country'].search(
                            [('name', '=ilike', bil['Country'])])
                        country_id = country_id.id
                    else:
                        country_id = False
                    if 'CountrySubDivisionCode' in bil and bil['CountrySubDivisionCode']:
                        state_id = self.env['res.country.state'].search(
                            [('name', '=ilike', bil['CountrySubDivisionCode'])])
                        if len(state_id) > 1:
                            state_id = state_id[0].id
                        else:
                            state_id = state_id.id
                    else:
                        state_id = False
            else:
                street = False or None
                street2 = False or None
                city = False or None
                zip = False or None
                state_id = False
                country_id = False

            if 'TermRef' in rec:
                if rec['TermRef']:
                    payment_term = self.env['account.payment.term'].search(
                        [('quickbook_id', '=', rec['TermRef']['value'])])
                    supplier_payment_term = payment_term.id
                    payment_term = False
            else:
                supplier_payment_term = False
                payment_term = False

            if rec['Id']:
                quickbook_id = rec['Id']
        partner_id = self.env['quickbook.customers'].search(
            [('quickbook_id', '=', quickbook_id), ('supplier', '=', supplier), ('customer', '=', customer),
             ('backend_id', '=', backend_id)])
        vals_quick_vendor = {
            'name': name,
            'supplier': supplier,
            'customer': customer,
            'phone': phone,
            'email': email,
            'website': website,
            'street': street,
            'street2': street2,
            'city': city,
            'zip': zip,
            'country_id': country_id,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
            'property_payment_term_id': payment_term,
            'property_supplier_payment_term_id': supplier_payment_term
        }
        vals_res_partner = {
            'first_name': first_name,
            'last_name': last_name,
            'name': name,
            'supplier_rank': 1 if supplier else 0,
            'customer_rank': 1 if customer else 0,
            'phone': phone,
            'email': email,
            'website': website,
            'street': street,
            'street2': street2,
            'city': city,
            'zip': zip,
            'state_id': state_id,
            'country_id': country_id,
            'backend_id': backend_id,
            'quickbook_id': quickbook_id,
            'company_name': company_name,
        }

        if not partner_id:
            return super(quickbook_vendors_custom, self).create(vals_quick_vendor)
        else:
            partner = partner_id.write(vals_quick_vendor)
            return partner

    def vendor_import_batch(self, model_name, backend_id, filters=None):
        """ Prepare the import of vendor """
        arguments = 'vendor'
        count = 1
        record_ids = ['start']
        filters['url'] = 'vendor'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Vendor' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Vendor']
                for record_id in record_ids:
                    self.env['quickbook.vendors'].importer(arguments=arguments, backend_id=backend_id,
                                                                  filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.vendor_import_mapper(backend_id, data)

    def write(self, fields):
        res = super(quickbook_vendors_custom, self).write(fields)
        if self.vendor_odoo:
            old_qb_vendor = self.env['res.partner'].search([('quickbook_id', '=', self.quickbook_id)])
            for vendor in old_qb_vendor:
                if self.vendor_odoo == vendor:
                    self.vendor_odoo.quickbook_id = self.quickbook_id
                else:
                    vendor.update({'quickbook_id': False})
            self.vendor_odoo.quickbook_id = self.quickbook_id
        return res