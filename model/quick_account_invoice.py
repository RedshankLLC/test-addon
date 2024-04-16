import logging
import time
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from requests_oauthlib import OAuth2Session
from ..unit.quick_invoice_exporter import QboInvoiceExport
from ..unit.backend_adapter import QuickExportAdapter
from . import quick_product

_logger = logging.getLogger(__name__)


class account_invoice(models.Model):
    _inherit = 'account.move'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbooks', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    doc_number = fields.Char(string='QBO Doc Number', help='Stores QBO document number for reference purpose')

    @api.model
    def create(self, vals):
        return super(account_invoice, self).create(vals)

    def get_ids(self, arguments, backend_id, filters, record_id):
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token, 'content-type': 'application/json',
                   'accept': 'application/json'}
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
                data = headeroauth.get(
                    backend.loaction + backend.company_id + '/' + arguments + str(record_id) + '?minorversion=4',
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

    def get_account_id(self, backend_id, qb_id):
        """This method is used to get Income account id from quickbook
        @param backend_id: Id of the backend configuration
        @param qb_id: Id of the quickbook to know the account id"""
        backend = self.env['qb.backend'].browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        data = headeroauth.get(
            backend.location + backend.company_id + "/item/" + qb_id + "/" + '?minorversion=40',
            headers=headers)
        if data.status_code == 200:
            data_json = data.json()
            if 'IncomeAccountRef' in data_json['Item']:
                property_item_income_id = data_json['Item']['IncomeAccountRef']['value']
                account_id = self.env['account.account'].search([('quickbook_id', '=', property_item_income_id)]).id
                return account_id

    def invoice_import_mapper(self, backend_id, data):
        record = data
        _logger.info("API DATA :%s", data)

        if 'Invoice' in record:
            rec = record['Invoice']
            inv_type = 'out_invoice'
            if 'Line' in rec:
                for lines in rec['Line']:
                    if 'SalesItemLineDetail' in lines:
                        if 'ItemRef' in lines['SalesItemLineDetail']:
                            if 'value' and 'name' in lines['SalesItemLineDetail']['ItemRef']:
                                # If product is deleted then we need to create that product
                                if 'deleted' in lines['SalesItemLineDetail']['ItemRef']['name']:
                                    product_exist = self.env['product.template'].search(
                                        [('quickbook_id', '=', lines['SalesItemLineDetail']['ItemRef']['value'])],
                                        limit=1)
                                    if not product_exist:
                                        qb_id = lines['SalesItemLineDetail']['ItemRef']['value']
                                        item_ref_name = lines['SalesItemLineDetail'].get('ItemRef', {}).get(
                                            'name', '')
                                        split_values = [part for part in
                                                        item_ref_name.split('-') + item_ref_name.split(':') if part]
                                        name = split_values[-1] if split_values else item_ref_name
                                        income_id = self.get_account_id(backend_id, qb_id)

                                        prod = self.env['product.template'].create({
                                            'name': name,
                                            'backend_id': backend_id,
                                            'quickbook_id': lines['SalesItemLineDetail']['ItemRef']['value'],
                                        })
                                        if lines['SalesItemLineDetail']['Qty']:
                                            prod.update({'qty_available': lines['SalesItemLineDetail']['Qty']})
                                        if income_id:
                                            prod.update({'property_account_income_id': income_id})
                                        prod.env.cr.commit()
                                product_template_id = self.env['product.template'].search(
                                    [('quickbook_id', '=', lines['SalesItemLineDetail']['ItemRef']['value']),
                                     ],limit=1)
                                product_id = self.env['product.product'].search(
                                    [('product_tmpl_id', '=', product_template_id.id)])

                                if product_id:
                                    if 'ItemAccountRef' in lines['SalesItemLineDetail']:
                                        if 'value' and 'name' in lines['SalesItemLineDetail']['ItemAccountRef']:
                                            property_item_income = self.env['account.account'].search(
                                                [('quickbook_id', '=', lines['SalesItemLineDetail']['ItemAccountRef']['value'])])
                                            property_item_income = property_item_income.id or False
                                            vals = {'property_account_income_id': property_item_income}
                                            product_id.update(vals)
                                else:
                                    backend = self.backend_id.browse(backend_id)
                                    headeroauth = OAuth2Session(backend.client_key)
                                    headers = {'Authorization': 'Bearer %s' % backend.access_token,
                                               'content-type': 'application/json', 'accept': 'application/json'}
                                    arguments = 'item'
                                    record_id = lines['SalesItemLineDetail']['ItemRef']['value']
                                    headeroauth.get(backend.location + backend.company_id +
                                                           '/' + arguments + '/' + str(record_id) + '?minorversion=4',
                                                           headers=headers)
                                    obj = quick_product.quickbook_product_template
                                    data2 = obj.get_ids(self, arguments, backend_id, {}, record_id)
                                    obj.product_import_mapper(self, backend_id, data2)
            if 'CustomerRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['CustomerRef']['value']),
                     ('name', '=', rec['CustomerRef']['name'])])
                if not partner_id:
                    filters = {'url': 'customer', 'count' : 1}
                    arguments = 'customer'
                    record_id=int(rec['CustomerRef']['value'])
                    cdata = self.env['res.partner'].get_ids(arguments=arguments, backend_id=backend_id, filters=filters, record_id=record_id)
                    crecord = cdata
                    _logger.info("API DATA :%s", cdata)
                    if 'Customer' in crecord:
                        supplier_rank = 0
                        customer_rank = 1
                        crec = crecord['Customer']
                        if 'GivenName' and 'FamilyName' in crec:
                            first_name = crec['GivenName'] or None
                            last_name = crec['FamilyName'] or None
                            name = crec['DisplayName'] or None
                        else:
                            name = crec['DisplayName'] or None
                            first_name = False or None
                            last_name = False or None
                        if 'CompanyName' in crec:
                            if crec['CompanyName']:
                                company_name = crec['CompanyName']
                        else:
                            company_name = None
                        if 'PrimaryEmailAddr' in crec:
                            if crec['PrimaryEmailAddr']:
                                email = crec['PrimaryEmailAddr']['Address'] or None
                        else:
                            email = None
                        if 'WebAddr' in crec:
                            if crec['WebAddr']:
                                website = crec['WebAddr']['URI'] or None
                        else:
                            website = False or None
                        if 'PrimaryPhone' in crec:
                            if crec['PrimaryPhone']:
                                phone = crec['PrimaryPhone']['FreeFormNumber'] or None
                        else:
                            phone = None
                        if 'BillAddr' in crec:
                            bil = crec['BillAddr']
                            if bil:
                                street = bil.get('Line1') or None
                                street2 = bil.get('Line2') or None
                                city = bil.get('City') or None
                                zip = bil.get('PostalCode') or None
                                if 'Country' in bil and bil['Country']:
                                    country_id = self.env['res.country'].search(
                                        [('code', '=', bil['Country'])])
                                    country_id = country_id.id
                                else:
                                    country_id = False
                                if 'CountrySubDivisionCode' in bil and bil['CountrySubDivisionCode']:
                                    state_id = self.env['res.country.state'].search(
                                        [('code', '=', bil['CountrySubDivisionCode'])])
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

                        if 'SalesTermRef' in crec:
                            if crec['SalesTermRef']:
                                payment_term = self.env['account.payment.term'].search(
                                    [('quickbook_id', '=', crec['SalesTermRef']['value'])])
                                payment_term = payment_term.id
                                supplier_payment_term = False
                        else:
                            payment_term = False
                            supplier_payment_term = False
                        if crec['Id']:
                            quickbook_id = crec['Id']
                        if 'CurrencyRef' in crec.keys():
                            price_list = self.env['product.pricelist'].search([('currency_id.name', '=', crec['CurrencyRef'].get('value'))], limit=1).id
                            if not price_list:
                                raise UserError('Create Pricelist of Currency' + str(crec['CurrencyRef'].get('value')) + ' - ' + str(crec['CurrencyRef'].get('name')))
                            currency = self.env['res.currency'].search([('name', '=', crec['CurrencyRef'].get('value'))]).id
                    vals = {
                        'first_name': first_name,
                        'last_name': last_name,
                        'name': name,
                        'supplier_rank': supplier_rank,
                        'customer_rank': customer_rank,
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
                        'property_payment_term_id': payment_term,
                        'property_supplier_payment_term_id': supplier_payment_term,
                        'property_product_pricelist': price_list or False,
                        'property_purchase_currency_id': currency,
                    }
                    partner_id = self.env['res.partner'].create(vals)
                if not partner_id:
                    raise UserError(('Please import "Customer" First'))
                account_id = partner_id.property_account_receivable_id.id or None
                partner_id = partner_id.id or False
            else:
                partner_id = False
                account_id = None

            if 'DocNumber' in rec:
                doc_number = rec['DocNumber']
            else:
                doc_number = None
            if 'DueDate' in record['Invoice']:
                date_due = rec['DueDate']
            else:
                date_due = None

            if 'SalesTermRef' in rec:
                payment_term = self.env['account.payment.term'].search(
                    [('quickbook_id', '=', rec['SalesTermRef']['value'])])

                payment_term = payment_term.id
            else:
                payment_term = False

            if 'TxnDate' in rec:
                date_invoice = rec['TxnDate']
            else:
                date_invoice = None

            quickbook_id = rec['Id']

            product_ids = []
            if 'Line' in rec:
                for lines in rec['Line']:
                    if 'SalesItemLineDetail' in lines:
                        if 'value' and 'name' in lines['SalesItemLineDetail']['ItemRef']:
                            product_template_id = self.env['product.template'].search(
                                [('quickbook_id', '=', lines['SalesItemLineDetail']['ItemRef']['value']),
                                 ],limit=1)
                            product_id = self.env['product.product'].search(
                                [('product_tmpl_id', '=', product_template_id.id),
                                 ])
                            order_id = self.env['account.move'].search(
                                [('backend_id', '=', backend_id), ('quickbook_id', '=', rec['Id'])])

                            tax_id = []
                            if not self.env.company.partner_id.country_id.code is 'US':
                                if 'TaxCodeRef' in lines.get('SalesItemLineDetail'):
                                    if 'TxnTaxDetail' in rec and 'TxnTaxCodeRef' in rec.get('TxnTaxDetail'):
                                        taxs_id = self.env['account.tax'].search(
                                            [('type_tax_use', '=', 'sale'), ('amount_type', '=', 'group'),
                                             ('quickbook_id', '=', rec['TxnTaxDetail']['TxnTaxCodeRef']['value'])]).id
                                        if taxs_id:
                                            tax_id.append(taxs_id)
                            else:
                                if lines['SalesItemLineDetail']['TaxCodeRef']['value'] == 'TAX':
                                    if 'TxnTaxDetail' in rec and 'TxnTaxCodeRef' in rec.get('TxnTaxDetail'):
                                        taxs_id = self.env['account.tax'].search(
                                            [('type_tax_use', '=', 'sale'), ('amount_type', '=', 'group'),
                                             ('quickbook_id', '=', rec['TxnTaxDetail']['TxnTaxCodeRef']['value'])]).id
                                        if taxs_id:
                                            tax_id.append(taxs_id)
                            order = self.env['account.move.line'].search(
                                [('move_id', '=', order_id.id), ('quickbook_id', '=', lines['Id']),
                                 ('name', '=', lines.get('Description'))])

                            if 'UnitPrice' in lines['SalesItemLineDetail']:
                                unitprice = lines['SalesItemLineDetail']['UnitPrice']
                            else:
                                unitprice = product_id.list_price

                            if 'Qty' in lines['SalesItemLineDetail']:
                                quantity = lines['SalesItemLineDetail']['Qty']
                            else:
                                quantity = product_id.qty_available
                            try:
                                name = lines['Description']
                            except KeyError:
                                name = lines['SalesItemLineDetail']['ItemRef']['name']
                            result = {'product_id': product_id.id,
                                      'price_unit': unitprice,
                                      'quantity': quantity,
                                      'tax_ids': [(6, 0, tax_id)],
                                      'account_id': product_id.property_account_income_id.id or None,
                                      'product_uom_id': 1,
                                      'price_subtotal': lines['Amount'],
                                      'name': name,
                                      'quickbook_id': lines['Id'],
                                      }
                            if not order:
                                product_ids.append([0, 0, result]) or False
                            else:
                                product_ids.append([1, order.id, result])
                    else:
                        if 'DiscountLineDetail' in lines:
                            if 'PercentBased' in lines['DiscountLineDetail']:
                                if lines['DiscountLineDetail']['PercentBased'] == True:
                                    discount_percentage = lines['DiscountLineDetail']['DiscountPercent']
                        else:
                            discount_percentage = 0

            tax_lines = []
            if 'TxnTaxDetail' in rec:
                rec_t = record['Invoice'].get('TxnTaxDetail')
                if 'TaxLine' in rec_t:
                    for line in rec_t.get('TaxLine'):
                        line_tax = line['TaxLineDetail'].get('TaxRateRef')
                        tax_id = self.env['account.tax'].search(
                            [('amount_type', '!=', 'group'), ('rate_quickbook_id', '=', line_tax.get('value'))])
                        order_id = self.env['account.move'].search(
                            [('backend_id', '=', backend_id), ('quickbook_id', '=', record['Invoice']['Id'])])

                        result = {
                            'name': tax_id.name,
                            'tax_id': tax_id.id or None,
                            'amount': line['Amount'],
                            'manual': False,
                            'company_id': tax_id.company_id.id or None,
                            'currency_id': tax_id.company_id.currency_id.id or None,
                            'base': line['TaxLineDetail'].get('NetAmountTaxable'),
                        }

            if rec['Id']:
                quickbook_id = rec['Id']
            
            for prods in product_ids:
                for entry in prods:
                    if type(entry) == dict:
                        entry.update({'discount':discount_percentage})

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id

        elif 'Bill' in record:
            rec = record['Bill']
            inv_type = 'in_invoice'
            if 'Line' in rec:
                for lines in rec['Line']:
                    if 'ItemBasedExpenseLineDetail' in lines:
                        if 'ItemRef' in lines['ItemBasedExpenseLineDetail']:
                            if 'value' and 'name' in lines['ItemBasedExpenseLineDetail']['ItemRef']:
                                # If product is deleted then we need to  create that product
                                if 'deleted' in lines['ItemBasedExpenseLineDetail']['ItemRef']['name']:
                                    product_exist = self.env['product.template'].search(
                                        [(
                                            'quickbook_id', '=',
                                            lines['ItemBasedExpenseLineDetail']['ItemRef']['value'])],
                                        limit=1)
                                    if not product_exist:
                                        qb_id = lines['ItemBasedExpenseLineDetail']['ItemRef']['value']
                                        item_ref_name = lines['ItemBasedExpenseLineDetail'].get('ItemRef', {}).get(
                                            'name', '')
                                        split_values = [part for part in
                                                        item_ref_name.split('-') + item_ref_name.split(':') if part]
                                        name = split_values[-1] if split_values else item_ref_name
                                        income_id = self.get_account_id(backend_id, qb_id)

                                        prod = self.env['product.template'].create({
                                            'name': name,
                                            'backend_id': backend_id,
                                            'quickbook_id': lines['ItemBasedExpenseLineDetail']['ItemRef']['value'],
                                        })
                                        if lines['ItemBasedExpenseLineDetail']['Qty']:
                                            prod.update({'qty_available': lines['ItemBasedExpenseLineDetail']['Qty']})
                                        if income_id:
                                            prod.update({'property_account_income_id': income_id})
                                        prod.env.cr.commit()
                                product_template_id = self.env['product.template'].search(
                                    [('quickbook_id', '=', lines['ItemBasedExpenseLineDetail']['ItemRef']['value']),
                                     ])
                                product_id = self.env['product.product'].search(
                                    [('product_tmpl_id', '=', product_template_id.id),
                                     ])

                                if product_id:
                                    if 'ItemAccountRef' in lines['ItemBasedExpenseLineDetail']:
                                        if 'value' and 'name' in lines['ItemBasedExpenseLineDetail']['ItemAccountRef']:
                                            property_item_income = self.env['account.account'].search(
                                                [('quickbook_id', '=', lines['ItemBasedExpenseLineDetail']['ItemAccountRef']['value'])])
                                            property_item_income = property_item_income.id or False
                                            vals = {'property_account_income_id': property_item_income}
                                            product_id.update(vals)
                                else:
                                    backend = self.backend_id.browse(backend_id)
                                    headeroauth = OAuth2Session(backend.client_key)
                                    headers = {'Authorization': 'Bearer %s' % backend.access_token,
                                               'content-type': 'application/json', 'accept': 'application/json'}
                                    arguments = 'item'
                                    record_id = lines['ItemBasedExpenseLineDetail']['ItemRef']['value']
                                    data1 = headeroauth.get(backend.location + backend.company_id +
                                                           '/' + arguments + '/' + str(record_id) + '?minorversion=4',
                                                           headers=headers)
                                    obj = quick_product.quickbook_product_template
                                    data2 = obj.get_ids(self, arguments, backend_id, {}, record_id)
                                    obj.product_import_mapper(self, backend_id, data2)
            if 'VendorRef' in rec:
                partner_id = self.env['res.partner'].search(
                    [('quickbook_id', '=', rec['VendorRef']['value']),
                     ('name', '=', rec['VendorRef']['name'])])
                if not partner_id:
                    filters = {'url': 'vendor', 'count' : 1}
                    arguments = 'vendor'
                    record_id=int(rec['VendorRef']['value'])
                    cdata = self.env['res.partner'].get_ids(arguments=arguments, backend_id=backend_id, filters=filters, record_id=record_id)
                    crecord = cdata
                    _logger.info("API DATA :%s", cdata)
                    if 'Vendor' in crecord:
                        supplier_rank = 1
                        customer_rank = 0
                        crec = crecord['Vendor']
                        if 'GivenName' and 'FamilyName' in crec:
                            first_name = crec['GivenName'] or None
                            last_name = crec['FamilyName'] or None
                            name = crec['DisplayName'] or None
                        else:
                            name = crec['DisplayName'] or None
                            first_name = False or None
                            last_name = False or None
                        if 'CompanyName' in crec:
                            if crec['CompanyName']:
                                company_name = crec['CompanyName']
                        else:
                            company_name = None
                        if 'PrimaryEmailAddr' in crec:
                            if crec['PrimaryEmailAddr']:
                                email = crec['PrimaryEmailAddr']['Address'] or None
                        else:
                            email = None
                        if 'WebAddr' in crec:
                            if crec['WebAddr']:
                                website = crec['WebAddr']['URI'] or None
                        else:
                            website = False or None
                        if 'PrimaryPhone' in crec:
                            if crec['PrimaryPhone']:
                                phone = crec['PrimaryPhone']['FreeFormNumber'] or None
                        else:
                            phone = None
                        if 'BillAddr' in crec:
                            bil = crec['BillAddr']
                            if bil:
                                street = bil.get('Line1') or None
                                street2 = bil.get('Line2') or None
                                city = bil.get('City') or None
                                zip = bil.get('PostalCode') or None
                                if 'Country' in bil and bil['Country']:
                                    country_id = self.env['res.country'].search(
                                        [('code', '=', bil['Country'])])
                                    country_id = country_id.id
                                else:
                                    country_id = False
                                if 'CountrySubDivisionCode' in bil and bil['CountrySubDivisionCode']:
                                    state_id = self.env['res.country.state'].search(
                                        [('code', '=', bil['CountrySubDivisionCode'])])
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

                        if 'TermRef' in crec:
                            if crec['TermRef']:
                                payment_term = self.env['account.payment.term'].search(
                                    [('quickbook_id', '=', crec['TermRef']['value'])])
                                payment_term = payment_term.id
                                supplier_payment_term = False
                        else:
                            payment_term = False
                            supplier_payment_term = False

                        if crec['Id']:
                            quickbook_id = crec['Id']

                        if 'CurrencyRef' in crec.keys():
                            price_list = self.env['product.pricelist'].search([('currency_id.name', '=', crec['CurrencyRef'].get('value'))], limit=1).id
                            if not price_list:
                                raise UserError('Create Pricelist of Currency' + str(crec['CurrencyRef'].get('value')) + ' - ' + str(crec['CurrencyRef'].get('name')))
                            currency = self.env['res.currency'].search([('name', '=', crec['CurrencyRef'].get('value'))]).id
                    vals = {
                        'first_name': first_name,
                        'last_name': last_name,
                        'name': name,
                        'supplier_rank': supplier_rank,
                        'customer_rank': customer_rank,
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
                        'property_payment_term_id': payment_term,
                        'property_supplier_payment_term_id': supplier_payment_term,
                        'property_product_pricelist': price_list or False,
                        'property_purchase_currency_id': currency,
                    }

                    partner_id = self.env['res.partner'].create(vals)
                if not partner_id: 
                    raise UserError(('Please import "Vendor Ref" First'))
                account_id = partner_id.property_account_payable_id.id or None
                for x in partner_id:
                    partner_id = x.id or False
            else:
                partner_id = False
                account_id = None

            if 'SalesTermRef' in rec:
                payment_term = self.env['account.payment.term'].search(
                    [('quickbook_id', '=', rec['SalesTermRef']['value'])])
                payment_term = payment_term.id
            else:
                payment_term = False

            if 'DocNumber' in rec:
                doc_number = rec['DocNumber']
            else:
                doc_number = None

            if 'DueDate' in rec:
                date_due = rec['DueDate']
            else:
                date_due = None

            if 'TxnDate' in rec:
                date_invoice = rec['TxnDate']
            else:
                date_invoice = None

            product_ids = []
            quickbook_id = rec['Id']


            if 'Line' in rec:
                for lines in rec['Line']:
                    if 'ItemBasedExpenseLineDetail' in lines:
                        if 'value' and 'name' in lines['ItemBasedExpenseLineDetail']['ItemRef']:
                            product_template_id = self.env['product.template'].search(
                                [('quickbook_id', '=', lines['ItemBasedExpenseLineDetail']['ItemRef']['value']),
                                 ])
                            product_id = self.env['product.product'].search(
                                [('product_tmpl_id', '=', product_template_id.id),
                                 ])
                            order_id = self.env['account.move'].search(
                                [('backend_id', '=', backend_id), ('quickbook_id', '=', rec['Id'])])

                            tax_id = []
                            if not self.env.company.partner_id.country_id.code is 'US':
                                if 'TaxCodeRef' in lines.get('ItemBasedExpenseLineDetail'):
                                    taxs_id = self.env['account.tax'].search(
                                        [('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'group'), (
                                        'quickbook_id', '=',
                                        lines['ItemBasedExpenseLineDetail']['TaxCodeRef']['value'])]).id
                                    if taxs_id:
                                        tax_id.append(taxs_id)
                            else:
                                if lines['ItemBasedExpenseLineDetail']['TaxCodeRef']['value'] == 'TAX':
                                    if 'TxnTaxDetail' in rec and 'TxnTaxCodeRef' in rec.get('TxnTaxDetail'):
                                        tax_id = [self.env['account.tax'].search(
                                            [('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'group'),
                                             ('quickbook_id', '=', rec['TxnTaxDetail']['TxnTaxCodeRef']['value'])]).id]

                            order = self.env['account.move.line'].search(
                                [('move_id', '=', order_id.id), ('quickbook_id', '=', lines['Id']),
                                 ('name', '=', lines.get('Description'))])

                            if 'UnitPrice' in lines['ItemBasedExpenseLineDetail']:
                                unitprice = lines['ItemBasedExpenseLineDetail']['UnitPrice']
                            else:
                                unitprice = product_id.list_price

                            if 'Qty' in lines['ItemBasedExpenseLineDetail']:
                                quantity = lines['ItemBasedExpenseLineDetail']['Qty']
                            else:
                                quantity = product_id.qty_available
                            result = {'product_id': product_id.id,
                                      'price_unit': unitprice,
                                      'quantity': quantity,
                                      'tax_ids': [(6, 0, tax_id)],
                                      'account_id': product_id.property_account_expense_id.id or None,
                                      'product_uom_id': 1,
                                      'price_subtotal': lines['Amount'],
                                      'name': lines.get('Description'),
                                      'quickbook_id': lines['Id'],
                                      }
                            if not order:
                                product_ids.append([0, 0, result]) or False
                            else:
                                product_ids.append([1, order.id, result])
                    elif 'AccountBasedExpenseLineDetail' in lines:
                        product_account_id = self.env['account.account'].search(
                            [('quickbook_id', '=', lines['AccountBasedExpenseLineDetail']['AccountRef']['value'])])
                        order_id = self.env['account.move'].search(
                            [('backend_id', '=', backend_id), ('quickbook_id', '=', rec['Id'])])

                        tax_id = []
                        if lines['AccountBasedExpenseLineDetail']['TaxCodeRef']['value'] == 'TAX':
                            if 'TxnTaxDetail' in rec and 'TxnTaxCodeRef' in rec.get('TxnTaxDetail'):
                                tax_id = [self.env['account.tax'].search(
                                    [('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'group'),
                                     ('quickbook_id', '=', rec['TxnTaxDetail']['TxnTaxCodeRef']['value'])]).id]

                        order = self.env['account.move.line'].search(
                            [('move_id', '=', order_id.id), ('quickbook_id', '=', lines['Id']),
                             ('name', '=', lines.get('Description'))])

                        result = {'product_id': False,
                                  'price_unit': lines['Amount'],
                                  'quantity': 1,
                                  'account_id': product_account_id.id or None,
                                  'product_uom_id': 1,
                                  'price_subtotal': lines['Amount'],
                                  'name': lines.get('Description') or product_account_id.name,
                                  'quickbook_id': lines['Id'],
                                  }
                        if not order:
                            product_ids.append([0, 0, result]) or False
                        else:
                            product_ids.append([1, order.id, result])

            tax_lines = []
            if 'TxnTaxDetail' in record['Bill']:
                rec_tx = record['Bill'].get('TxnTaxDetail')
                if 'TaxLine' in rec_tx:
                    for line in rec_tx.get('TaxLine'):
                        line_tax = line['TaxLineDetail'].get('TaxRateRef')
                        tax_id = self.env['account.tax'].search(
                            [('amount_type', '!=', 'group'), ('rate_quickbook_id', '=', line_tax.get('value'))])
                        order_id = self.env['account.move'].search(
                            [('backend_id', '=', backend_id), ('quickbook_id', '=', record['Bill']['Id'])])
                        result = {
                            'name': tax_id.name,
                            'tax_id': tax_id.id or None,
                            'amount': line['Amount'],
                            'manual': False,
                            'company_id': tax_id.company_id.id or None,
                            'currency_id': tax_id.company_id.currency_id.id or None,
                            'base': line['TaxLineDetail'].get('NetAmountTaxable'),
                        }
            if rec['Id']:
                quickbook_id = rec['Id']

            if 'CurrencyRef' in rec.keys():
                currency = self.env['res.currency'].search([('name', '=', rec['CurrencyRef'].get('value'))]).id
        invoice_id = self.env['account.move'].search(
            [('quickbook_id', '=', quickbook_id),
             ('backend_id', '=', backend_id)])
        if product_ids:
            vals = {
                'partner_id': partner_id,
                'move_type': inv_type,
                'doc_number': doc_number or rec.get('DocNumber'),
                'invoice_date_due': date_due or rec['DueDate'],
                'invoice_date': date_invoice or rec['TxnDate'],
                'invoice_line_ids': product_ids,
                'invoice_payment_term_id': payment_term,
                'partner_shipping_id': partner_id,
                'quickbook_id': quickbook_id,
                'backend_id': backend_id,
                'name': '/',
                'currency_id': currency,
            }
            if 'Invoice' in data:
                name = 'Import Invoice'
                rec_id = data['Invoice']['Id']
            elif 'Bill' in data:
                name = 'Import Bill'
                rec_id = data['Bill']['Id']
            else:
                name = 'Import Invoice/Bill'
                rec_id = None

            if not invoice_id:
                try:
                    invoice = super(account_invoice, self).create(vals)
                    invoice.action_post()
                    invoice.env.cr.commit()
                    QuickExportAdapter.create_or_update_job(self, name, 200, backend_id, data, vals, rec_id, invoice.id)
                    return invoice
                except Exception as e:
                    QuickExportAdapter.create_or_update_job(self, name, 400, backend_id, data, vals, rec_id, invoice_id.id)
                    _logger.error("Invoce not created "+str(e))
            else:
                QuickExportAdapter.create_or_update_job(self, name, 200, backend_id, data, vals, rec_id,
                                                        invoice_id.id)
                if invoice_id.state == 'draft':
                    invoice = invoice_id.write(vals)
                    return invoice

    def invoice_import_batch(self, model_name, backend_id, filters=None):
        """ Import Invoice Details. """
        arguments = 'invoice'
        count = 1
        filters['url'] = 'invoice'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Invoice' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Invoice']
                for record_id in record_ids:
                    self.env['account.move'].importer(arguments=arguments, backend_id=backend_id, filters=filters,
                                                      record_id=int(record_id['Id']))
            else:
                record_ids['QueryResponse']

    def bill_import_batch(self, model_name, backend_id, filters=None):
        """ Import Invoice Details. """
        arguments = 'bill'
        count = 1
        record_ids = ['start']
        filters['url'] = 'bill'
        filters['count'] = count
        record_ids = self.get_ids(arguments, backend_id, filters, record_id=False)

        if record_ids:
            if 'Bill' in record_ids['QueryResponse']:
                record_ids = record_ids['QueryResponse']['Bill']
                for record_id in record_ids:
                    self.env['account.move'].importer(arguments=arguments, backend_id=backend_id, filters=filters,
                                                      record_id=int(record_id['Id']))
            else:
                record_ids = record_ids['QueryResponse']

    def importer(self, arguments, backend_id, filters, record_id):
        data = self.get_ids(arguments, backend_id, filters, record_id)
        if data:
            self.invoice_import_mapper(backend_id, data)

    def sync_invoice(self):
        for backend in self.backend_id:
            self.export_invoice_data(backend)
            payment_ids = self.env['account.payment'].search([('ref', '=', self.name)])
            if payment_ids:
                for payment in payment_ids:
                    payment.export_payment_data(backend)

    def sync_bill(self):
        for backend in self.backend_id:
            self.export_bill_data(backend)
            payment_ids = self.env['account.payment'].search([('ref', '=', self.name)])
            if payment_ids:
                for payment in payment_ids:
                    payment.export_billpayment_data(backend)

    def export_invoice_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['account.move'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'invoice'
        arguments = [mapper.quickbook_id or None, self]
        export = QboInvoiceExport(backend)
        res = export.export_invoice(method, arguments)
        # code for logger
        if res:
            if 'Invoice' in res['data']:
                qb_id = res['data']['Invoice']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Invoice', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)
        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Invoice']['Id']})
                response = res['data']
                count = 0
                for lines in response['Invoice']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Invoice']['Id']})
                response = res['data']
                count = 0
                for lines in response['Invoice']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Invoice']['Id']})
            response = res['data']
            count = 0
            for lines in response['Invoice']['Line']:
                if 'Id' in lines:
                    order_lines = arguments[1].invoice_line_ids
                    order_lines[count].write({'quickbook_id': lines['Id']})
                    count += 1

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: ' + str(
                    name.name) + '\n' + 'Detail: ' + errors['Detail']  +'\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Export Invoice"+ str(details)))

    def export_bill_data(self, backend):
        if not self.backend_id:
            return

        mapper = self.env['account.move'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'bill'
        arguments = [mapper.quickbook_id or None, self]
        export = QboInvoiceExport(backend)
        res = export.export_bill(method, arguments)
        # code for logger
        if res:
            if 'Bill' in res['data']:
                qb_id = res['data']['Bill']['Id']
            else:
                qb_id = None
            QuickExportAdapter.create_or_update_job(self, 'Export Bill', res['status'], backend.id,
                                                    res['data'] if res['data'] else res['errors'], res['applied_data'],
                                                    qb_id, self.id)
        if res['name'].payment_state == 'paid':
            pass

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Bill']['Id']})
                response = res['data']
                count = 0
                for lines in response['Bill']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['Bill']['Id']})
                response = res['data']
                count = 0
                for lines in response['Bill']['Line']:
                    if 'Id' in lines:
                        order_lines = arguments[1].invoice_line_ids
                        order_lines[count].write({'quickbook_id': lines['Id']})
                        count += 1
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['Bill']['Id']})
            response = res['data']
            count = 0
            for lines in response['Bill']['Line']:
                if 'Id' in lines:
                    order_lines = arguments[1].invoice_line_ids
                    order_lines[count].write({'quickbook_id': lines['Id']})
                    count += 1

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + code + '\n' + 'Name: ' + str(
                    name.name) + '\n' + 'Detail: ' + errors['Detail']  +'\n' +'Applied Data: ' + str(res['applied_data'])
                if errors['code']:
                    _logger.info(_("Invoice Export :"+details))


class quickbook_product(models.Model):
    _inherit = 'account.move.line'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)


class quickbook_acount_tax(models.Model):
    _inherit = 'account.tax'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)


class quickbook_product_product(models.Model):
    _inherit = 'product.product'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
