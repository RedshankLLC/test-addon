import logging
from odoo import models, fields, api, _
from requests_oauthlib import OAuth2Session
from odoo.exceptions import RedirectWarning
from ..unit.quick_product_category_exporter import QboProductCategoryExport
from ..unit.backend_adapter import QuickExportAdapter
_logger = logging.getLogger(__name__)


class quickbook_product_category(models.Model):
    _inherit = 'product.category'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )

    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')
    quickbook_name=fields.Char(string='Quickbook Name')

    def get_ids(self, arguments, backend_id, record_id):
        # arguments = 'customer'
        backend = self.backend_id.browse(backend_id)
        headeroauth = OAuth2Session(backend.client_key)
        headers = {'Authorization': 'Bearer %s' % backend.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}
        data = headeroauth.get(
            backend.location + backend.company_id + "/query?query=select * from " + arguments + " where Type='Category'" + '&minorversion=54', headers=headers)
        filter_list = []
        if 'Item' in data.json()['QueryResponse']:
            for result in data.json()['QueryResponse']['Item']:
                filter_list.append(result)
        return filter_list


    def product_category_import_mapper(self, backend_id, data):
        rec = data
        _logger.info("API DATA :%s", data)
        if 'Name' in rec:
            name = rec['Name']
        else:
            name = False
        if 'ParentRef' in rec:
            parent_ref_value = rec['ParentRef']['value']
            if parent_ref_value:
                parent_id = self.env['product.category'].search([('quickbook_id', '=', parent_ref_value)],limit=1)
                if parent_id:
                    parent_id = parent_id.id
                else:
                    parent_id = False
            else:
                parent_id = False
        else:
            parent_id = False
        if rec['Id']:
            quickbook_id = rec['Id']

        vals = {
            'name': name,
            'parent_id': parent_id,
            'quickbook_id': quickbook_id,
        }
        if vals:
            qb_id = self.env['product.category'].search([('quickbook_id', '=', quickbook_id)], limit=1)
            if qb_id:
                qb_id.write(vals)
                QuickExportAdapter.create_or_update_job(self, 'Import Category', 200, backend_id, rec,
                                                        vals, rec['Id'], qb_id.id)
            else:
                new_categ = super(quickbook_product_category, self).create(vals)
                QuickExportAdapter.create_or_update_job(self, 'Import Category', 200, backend_id, rec,
                                                        vals, rec['Id'], new_categ.id)

    def sync_product(self):
        """ Export the inventory configuration and quantity of a product. """
        for backend in self.backend_id:
            self.export_product_category_data(backend)
        return

    def export_product_category_data(self, backend):
        """ export customer details, save username and create or update backend mapper """
        if not self.backend_id:
            return
        mapper = self.env['product.category'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)
        method = 'item'
        arguments = [mapper.quickbook_id or None, self]
        export = QboProductCategoryExport(backend)
        res = export.export_product_category(method, arguments,backend)
        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):

                try:
                    mapper.write(
                        {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id'],'quickbook_name':res['data']['Item']['FullyQualifiedName']})
                except:
                    mapper.write(
                        {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id']})

            elif (res['status'] == 200 or res['status'] == 201):
                try:
                    arguments[1].write(
                        {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id'],
                         'quickbook_name': res['data']['Item']['FullyQualifiedName']})
                except:
                    arguments[1].write(
                        {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id']})

        elif (res['status'] == 200 or res['status'] == 201):
                try:
                    arguments[1].write(
                        {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id'],'quickbook_name':res['data']['Item']['FullyQualifiedName']})
                except:
                    arguments[1].write(
                        {'backend_id': backend.id, 'quickbook_id': res['data']['Item']['Id']})



        if res['status'] == 500 or res['status'] == 400:
            try:
                for errors in res['data']['Fault']['Error']:
                    msg = errors['Message']
                    code = errors['code']
                    name = res['name']
                    details = 'Message: ' + msg + '\n' + 'Code: ' + \
                        code + '\n' + 'Name: '+ str(name.name) + '\n' + 'Detail: ' + errors['Detail'] \
                            +'\n' + 'Applied Data: ' + str(res['applied_data'])
                    if errors['code']:
                        _logger.info(_(details))
            except:
                for errors in res['errors']['Fault']['Error']:
                    msg = errors['Message']
                    code = errors['code']
                    name = res['name']
                    details = 'Message: ' + msg + '\n' + 'Code: ' + \
                        code + '\n' + 'Name: '+ str(name.name) + '\n' + 'Detail: ' + errors['Detail'] \
                              +'\n' + 'Applied Data: ' + str(res['applied_data'])
                    if errors['code']:
                        _logger.info(_(details))

    def item_category_import_batch_new(self, model_name, backend_id, filters=None):
        """ Import Product Category Details. """
        arguments = 'item'
        record_ids = self.get_ids(arguments, backend_id, record_id=False)
        if record_ids:
            for categ in record_ids:
                self.env['product.category'].importer(arguments=arguments, backend_id=backend_id,  record_id=int(categ['Id']))
        else:
            raise RedirectWarning(_("No Product Category found in Quickbooks"))

    def importer(self, arguments, backend_id, record_id):
        data = self.get_ids(arguments, backend_id, record_id)
        level_one = []
        level_two = []
        level_three = []
        normal_list = []
        for rec in data:
            if rec.get('ParentRef'):
                if rec['Level'] == 1:
                    level_one.append(rec)
                elif rec['Level'] == 2:
                    level_two.append(rec)
                else:
                    level_three.append(rec)
            else:
                normal_list.append(rec)
        for data in normal_list:
            self.product_category_import_mapper(backend_id, data)
        for data in level_one:
            self.product_category_import_mapper(backend_id, data)
        for data in level_two:
            self.product_category_import_mapper(backend_id, data)
        for data in level_three:
            self.product_category_import_mapper(backend_id, data)

    @api.model
    def default_get(self, fields):
        res = super(quickbook_product_category, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res