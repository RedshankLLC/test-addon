import logging
import time

from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import  UserError
from requests_oauthlib import OAuth2Session
from ..unit.quick_customer_exporter import QboCustomerExport
from ..unit.backend_adapter import QuickExportAdapter

_logger = logging.getLogger(__name__)

class quick_customer(models.Model):
    _inherit = 'res.partner'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    company_name = fields.Char('Company Name', help='Quickbook Company Name')
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False, store=True)
    sync_date = fields.Datetime(string='Last synchronization date')
    first_name = fields.Char('First Name', readonly=False)
    last_name = fields.Char('Last Name', readonly=False)
    def get_partner_street2(self, partner_id):
        partner = self.env['res.partner'].browse(partner_id)
        if partner:
            street2 = partner.street2
            return street2
        return None

    def get_ids(self, arguments, backend_id, filters, record_id):

        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token, 'content-type': 'application/json',
                   'accept': 'application/json'}
        method = '/query?query=select%20ID%20from%20'
        #
        # not_imp_cust=headeroauth.get(
        #     backend.location + backend.company_id + '/' + arguments + '/' + '630' + '?minorversion=4',
        #     headers=headers).json()
        #
        
        if not record_id:
            if backend.data == 'custom':
                sd = str(backend.start_date.year) +'-'+str(backend.start_date.month).zfill(2)+'-'+str(backend.start_date.day).zfill(2)
                ed = str(backend.end_date.year) +'-'+str(backend.end_date.month).zfill(2)+'-'+str(backend.end_date.day).zfill(2)
                data = headeroauth.get(backend.location + backend.company_id +"/query?query=select ID from "+ arguments +" Where Metadata.CreateTime>'" + str(sd) +"' and Metadata.CreateTime<'"+ str(ed)+"'" + ' MAXRESULTS ' + str(1000) +'&minorversion=54', headers=headers)
            elif backend.data == 'all':
                if backend.company_id:
                    data = headeroauth.get(backend.location + backend.company_id +method + arguments + '%20STARTPOSITION%20'+ str(backend.record_no) + '%20MAXRESULTS%20' + str(500) + '&minorversion=54', headers=headers)
                else:
                    raise UserError(_('Please add company ID'))
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

    def customer_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)
        child_ids = []
        billing_details = {'type': 'invoice'}
        billing_zip=None
        shipping_detail = {'type': 'delivery'}
        shipping_zip=None
        if 'Customer' in record:
            supplier_rank = 0
            customer_rank = 1
            rec = record['Customer']
            
            if 'GivenName' in rec and 'FamilyName' in rec:
                first_name = rec['GivenName'] or None
                last_name = rec['FamilyName'] or None
                name = rec['DisplayName'] or None
            else:
                name = rec['DisplayName'] or None
                first_name = False or None
                last_name = False or None
            if name:
                billing_details['name']=name
                shipping_detail['name']=name

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
                
            if 'Mobile' in rec:
                
                if rec['Mobile']:
                    Mob_no = rec['Mobile']['FreeFormNumber'] or None
            else:
                Mob_no = None

            if 'BillAddr' in rec:
                bil = rec['BillAddr']

                if bil:
                    if 'Line1' in bil:
                        street = bil.get('Line1')
                        billing_details['street'] = street
                    else:
                        street = None
                    if 'Line2' in bil:
                        street2 = bil.get('Line2')
                        billing_details['street2'] = street2
                    else:
                        street2 = None
                    city = bil.get('City') or None
                    if city:
                        billing_details['city'] = city
                    zip = bil.get('PostalCode') or None
                    if zip:
                        billing_details['zip'] = zip
                        billing_zip=zip
                    else:
                        raise UserError('Please provide zip to billing address of customer' + " " + str(name))

                    if 'Country' in bil and bil['Country']:
                        country_id = self.env['res.country'].search(
                            [('name', '=', bil['Country'])])
                        country_id = country_id.id
                        if country_id:
                            
                            billing_details['country_id'] = country_id
                    else:
                        billing_details['country_id']=False
                        country_id = False

                    if 'CountrySubDivisionCode' in bil and bil['CountrySubDivisionCode']:
                        state_id = self.env['res.country.state'].search(
                            [('code', '=', bil['CountrySubDivisionCode'])])
                        if len(state_id) > 1:
                            state_id = state_id[0].id
                            if state_id:
                                billing_details['state_id'] = state_id
                        else:
                            state_id = state_id.id
                            if state_id:
                                billing_details['state_id'] = state_id
                    else:
                        state_id = False
                        billing_details['state_id'] = False

            else:
                street = False or None
                street2 = False or None
                city = False or None
                zip = False or None
                state_id = False
                country_id = False

            if 'ShipAddr' in rec:
                bil = rec['ShipAddr']

                if bil:
                    if 'Line1' in bil:
                        street = bil.get('Line1')
                        shipping_detail['street'] = street
                    else:
                        street = None
                    if 'Line2' in bil:
                        street2 = bil.get('Line2')
                        shipping_detail['street2'] = street2
                    else:
                        street2 = None
                    city = bil.get('City') or None
                    if city:
                        shipping_detail['city'] = city
                    zip = bil.get('PostalCode') or None
                    if zip:
                        shipping_detail['zip'] = zip
                        shipping_zip=zip
                    else:
                        raise UserError('Please provide zip to shipping address of customer' +" " +str(name))

                    if 'Country' in bil and bil['Country']:
                        country_id = self.env['res.country'].search(
                            [('name', '=', bil['Country'])])
                        country_id = country_id.id
                        if country_id:
                            shipping_detail['country_id'] = country_id
                    else:
                        country_id = False
                        shipping_detail['country_id'] = False

                    if 'CountrySubDivisionCode' in bil and bil['CountrySubDivisionCode']:
                        state_id = self.env['res.country.state'].search(
                            [('name', '=', bil['CountrySubDivisionCode'])])
                        if len(state_id) > 1:
                            state_id = state_id[0].id
                            if state_id:
                                shipping_detail['state_id'] = state_id
                        else:
                            state_id = state_id.id
                            if state_id:
                                shipping_detail['state_id'] = state_id
                    else:
                        state_id = False
                        shipping_detail['state_id'] = False

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

            if 'CurrencyRef' in rec.keys():
                price_list = self.env['product.pricelist'].search([('currency_id.name', '=', rec['CurrencyRef'].get('value'))], limit=1).id
                if not price_list:
                    raise UserError('Create Pricelist of Currency' + str(rec['CurrencyRef'].get('value')) + ' - ' + str(rec['CurrencyRef'].get('name')))
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        elif 'Vendor' in record:
            supplier_rank = 1
            customer_rank = 0
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
                
            if 'Mobile' in rec:
                
                if rec['Mobile']:
                    Mob_no = rec['Mobile']['FreeFormNumber'] or None
            else:
                Mob_no = None
            if 'BillAddr' in rec:
                bil = rec['BillAddr']
                if bil:
                    if 'Line1' in bil:
                        street = bil.get('Line1')
                    else:
                        street = None
                    if 'Line2' in bil:
                        street2 = bil.get('Line2')
                    else:
                        street2 = None
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

            if 'CurrencyRef' in rec.keys():
                price_list = self.env['product.pricelist'].search([('currency_id.name', '=', rec['CurrencyRef'].get('value'))], limit=1).id
                if not price_list:
                    raise UserError('Create Pricelist of Currency' + str(rec['CurrencyRef'].get('value')) + ' - ' + str(rec['CurrencyRef'].get('name')))
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        if (supplier_rank > 0):
            partner_id = self.env['res.partner'].search(
                [('quickbook_id', '=', quickbook_id), ('supplier_rank', '>', 0),('backend_id', '=', backend_id),('quickbook_id', '=', quickbook_id)])
        elif (customer_rank > 0):
            partner_id = self.env['res.partner'].search(
                [('quickbook_id', '=', quickbook_id),('customer_rank', '>', 0),('backend_id', '=', backend_id),('quickbook_id', '=', quickbook_id)])
        
        vals = {
            'first_name': first_name,
            'last_name': last_name,
            'name': name,
            'supplier_rank': supplier_rank,
            'customer_rank': customer_rank,
            'phone': phone,
            'mobile':Mob_no,
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
            'property_payment_term_id': payment_term,
            'property_supplier_payment_term_id': supplier_payment_term,
            'property_product_pricelist': price_list or False,
            'property_purchase_currency_id': currency,
        }
        delivery_add=False
        invoice_add=False
        if 'Customer' in record:
            if partner_id:
                if shipping_zip is not None:
                    delivery_add=self.env['res.partner'].search([('parent_id','=',partner_id.id),('zip','=',shipping_zip)])

                if billing_zip is not None:
                    invoice_add = self.env['res.partner'].search([('parent_id', '=', partner_id.id), ('zip', '=', shipping_zip)])

            if 'BillAddr' in record['Customer'] and 'ShipAddr' in record['Customer']:
                if partner_id and invoice_add is False:
                    child_ids.append((0, 0, billing_details))
                if partner_id and delivery_add is False:
                    child_ids.append((0, 0, shipping_detail))
                vals['child_ids']=child_ids
        if 'Customer' in data:
            name = 'Import Customer'
            rec_id = data['Customer']['Id']
        else:
            name = 'Import Vendor'
            rec_id = data['Vendor']['Id']
        if not partner_id:
            try:
                if 'Customer' in record:
                    if 'BillAddr' in record['Customer'] and 'ShipAddr' in record['Customer']:
                        child_ids.append((0, 0, billing_details))
                        child_ids.append((0, 0, shipping_detail))
                        vals['child_ids'] = child_ids
                a=super(quick_customer, self).create(vals)
                a.env.cr.commit()
                QuickExportAdapter.create_or_update_job(self, name, 200, backend_id, data, vals, rec_id, a.id)
                return a
            except:
                QuickExportAdapter.create_or_update_job(self, name, 400, backend_id, data, vals, rec_id, partner_id.id)
                raise UserError(_("Issue while importing " + vals.get('name') + ". Please check if there are any missing values in Quickbooks."))
        else:
            partner = partner_id.write(vals)
            QuickExportAdapter.create_or_update_job(self, name, 200, backend_id, data, vals, rec_id, partner_id.id)
            return partner

    def customer_import_batch_new(self, model_name, backend_id, filters=None):
        """ Import Customer Details."""
        arguments = 'customer'
        count = 1
        end=1000
        record_ids = ['start']
        filters['url'] = 'customer'
        filters['count'] = count
        filters['end'] = end

        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        list_of_id = []
        if record_ids:
            if 'Customer' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Customer']
                for record_id in record_ids:
                    list_of_id.append(int(record_id['Id']))
                    self.env['res.partner'].importer(arguments=arguments, backend_id=backend_id,
                                                                  filters=filters,
                                                                  record_id=int(record_id['Id']))

                if len(list_of_id) == 1000:
                    list_check = []
                    while True:

                        # if len(list_of_id)==1000:
                        count = count + 1000

                        record_ids = ['start']
                        filters['url'] = 'customer'
                        filters['count'] = count
                        filters['end'] = end
                        record_ids = None
                        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)
                        if 'Customer' in record_ids['QueryResponse']:
                            record_ids = record_ids['QueryResponse']['Customer']
                            for record_id in record_ids:
                                self.env['res.partner'].importer(arguments=arguments, backend_id=backend_id,
                                                                 filters=filters,
                                                                 record_id=int(record_id['Id']))

                                list_check.append(int(record_id['Id']))

                            if len(list_check) < 1000:
                                break
                            else:
                                list_check.clear()
            else:
                record_ids = record_ids['QueryResponse']

    def vendor_import_batch_new(self, model_name, backend_id, filters=None):
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
                    self.env['res.partner'].importer(arguments=arguments, backend_id=backend_id,
                                                                  filters=filters, record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.customer_import_mapper(backend_id, data)

    def sync_customer_vendor(self):
        for rec in self:
            for backend in rec.backend_id:
                if rec.supplier_rank > 0:
                    rec.export_vendor_data(backend)
                else:
                    rec.export_customer_data(backend)
            return

    def sync_customer_multiple(self):
        for rec in self:
            for backend in rec.backend_id:
                if rec.customer_rank > 0:
                    rec.export_customer_data(backend)
                else:
                    rec.export_vendor_data(backend)
        return

    def export_customer_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.customer_rank > 0:
            return
        mapper = self.env['res.partner'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'customer'
        arguments = [mapper.quickbook_id or None, self]
        export = QboCustomerExport(backend)
        res = export.export_customer(method, arguments)
        # code for logger
        if res:
            if 'Customer' in res['data']:
                qb_id = res['data']['Customer']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self,'Export Customer', res['status'], backend.id, res['data'] if res['data'] else res['errors'], res['applied_data'], qb_id,
                                      self.id)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Customer']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Customer']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Customer']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + \
                          errors['Detail']  +'\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Export customer : " + details))

    def export_vendor_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.supplier_rank > 0:
            return
        mapper = self.env['res.partner'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'vendor'

        arguments = [mapper.quickbook_id or None, self]
        export = QboCustomerExport(backend)
        res = export.export_vendor(method, arguments)
        # code for logger
        if res:
            if 'Vendor' in res['data']:
                qb_id = res['data']['Vendor']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Vendor', res['status'], backend.id,
                                      res['data'] if res['data'] else res['errors'], res['applied_data'], qb_id,
                                      self.id)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Vendor']['Id']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Vendor']['Id']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Vendor']['Id']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + \
                          errors['Detail']  +'\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Export vendor: " + details))

    @api.model
    def default_get(self, fields):
        res = super(quick_customer, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res