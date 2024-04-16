import logging
from .backend_adapter import QuickExportAdapter
from requests_oauthlib import OAuth1
from requests_oauthlib import OAuth2Session
from odoo.http import request
_logger = logging.getLogger(__name__)

class QboProductCategoryExport(QuickExportAdapter):
    """ Models for QBO customer export """

    def get_api_method(self, method, args):
        """ get api for Product/item"""
        api_method = None
        if method == 'item':
            if not args[0]:
                api_method = self.quick.location + \
                             self.quick.company_id + '/item?minorversion=4'
            else:
                api_method = self.quick.location + self.quick.company_id + '/item?operation=update&minorversion=4'
        return api_method
    # To get the api response of that particular category
    def get_api(self, name):
        if self.quick.type == 'oauth1':

            headeroauth = OAuth1(self.quick.client_key, self.quick.client_secret,
                                 self.quick.resource_owner_key, self.quick.resource_owner_secret,
                                 signature_type='auth_header')
        elif self.quick.type == 'oauth2':

            headeroauth = OAuth2Session(self.quick.client_key)

        headers = {'Authorization': 'Bearer %s' % self.quick.access_token,
                   'content-type': 'application/json', 'accept': 'application/json'}

        ris = self.quick.location + self.quick.company_id + \
              "/query?query=select * from Item where type='Category' and Name=" + "\'" + name + "\'" + '&minorversion=65'
        response = headeroauth.get(ris, headers=headers)
        res1 = response.json()
        if res1:
            res1.update({'status': response.status_code})
        return res1

    def update_category(self, method, arguments, result_dict):
        if '?operation=update&minorversion=4' in self.get_api_method(method, arguments):
            result = self.importer_updater(method, arguments)
            result_dict.update({
                "sparse": result['Item']['sparse'],
                "Id": result['Item']['Id'],
                "SyncToken": result['Item']['SyncToken'], })

        res = self.export(method, result_dict, arguments)
        if res:
            res_dict = res.json()
            errors_dict = None
        else:
            res_dict = None
            errors_dict = res.json()
        return {'status': res.status_code, 'data': res_dict or {}, 'applied_data': result_dict,
                'errors': errors_dict or {}, 'name': arguments[1]}

    def export_product_category(self, method, arguments, backend):
        """ Export Product category"""
        _logger.debug("Start calling QBO api %s", method)
        name = arguments[1].name
        if len(self.category_list) >= 1:
            self.category_list.clear()
        if arguments[1]:
            if arguments[1].parent_id:
                val_list = self.recur(name, method, arguments)
                self.export_parent_category(method, arguments, val_list, backend)
                return {'status': 700, 'data':  {}, 'name': arguments[1]}
            else:
                res1 = self.get_api(name)
                try:
                    cat = request.env['product.category'].search([('name', '=', arguments[1].name)], limit=1)
                    vals = {
                        {'quickbook_id': res1['QueryResponse']['Item'][0]['Id'],
                         'backend_id': backend.id,
                         'quickbook_name': res1['QueryResponse']['Item'][0]['FullyQualifiedName']}
                    }
                    cat.write(vals)
                    cat.env.cr.commit()
                    return {'status': 700, 'data': res1 or {}, 'applied_data': vals, 'name': arguments[1]}
                except:
                    result_dict = {
                        "SubItem": False,
                        "Type": "Category",
                        "Name": arguments[1].name
                    }
                    res = self.update_category(method, arguments, result_dict)
                    return res

    category_list = []
    def recur(self, name, arguments, method):
        category = request.env['product.category'].search([('name', '=', name)], limit=1)
        if category.parent_id:
            self.category_list.append(category.name)
            self.recur(category.parent_id.name, method, arguments)
        else:
            self.category_list.append(category.name)
            self.category_list.reverse()
        return self.category_list

    def export_parent_category(self, method, arguments, category_list, backend):
        """ Export Product category"""
        id_list = []
        for categ in category_list:
            if category_list.index(categ) == 0:
                res1 = self.get_api(categ)
                try:
                    if res1['QueryResponse']['Item']:
                        id_list.append(int(res1['QueryResponse']['Item'][0]['Id']))

                    cat = request.env['product.category'].search([('name', '=', categ)], limit=1)
                    vals = {'quickbook_id': res1['QueryResponse']['Item'][0]['Id'],
                               'backend_id': backend.id,
                               'quickbook_name': res1['QueryResponse']['Item'][0]['FullyQualifiedName']
                           }
                    cat.write(vals)
                    cat.env.cr.commit()
                except:
                    result_dict = {
                        "SubItem": False,
                        "Type": "Category",
                        "Name": categ
                    }
                    res2 = self.update_category(method, arguments, result_dict)

                    if res2['status'] in [200, 201]:
                        id_list.append(int(res2['data']['Item']['Id']))
                        cat = request.env['product.category'].search([('name', '=', categ)], limit=1)
                        vals = {'quickbook_id': res2['Item']['Id'],
                                   'backend_id': backend.id,
                                   'quickbook_name': res2['Item']['FullyQualifiedName']
                                   }
                        cat.write(vals)
                        cat.env.cr.commit()
                    else:
                        if res2['name'].quickbook_id:
                            id_list.append(int(res2['name'].quickbook_id))
            else:
                res1 = self.get_api(categ)
                try:
                    if len(res1['QueryResponse']) != 0:
                        if res1['status'] in [200, 201]:
                            cat = request.env['product.category'].search([('name', '=', categ)], limit=1)
                            cat.write({'quickbook_id': res1['QueryResponse']['Item'][0]['Id'],
                                       'backend_id': backend.id,
                                       'quickbook_name': res1['QueryResponse']['Item'][0]['FullyQualifiedName']
                                       })
                            cat.env.cr.commit()
                    else:
                        try:
                            if res1['QueryResponse']['Item']:
                                id_list.append(int(res1['QueryResponse']['Item'][0]['Id']))
                                result_dict = {
                                    "SubItem": True,
                                    "Type": "Category",
                                    "Name": categ,
                                    "ParentRef": {
                                        "name": category_list[category_list.index(categ) - 1],
                                        "value": id_list[category_list.index(categ) - 1],
                                    },
                                }
                                res = self.export(method, result_dict, arguments)
                                res2 = res.json()
                                cat = request.env['product.category'].search([('name', '=', categ)], limit=1)
                                cat.write({'quickbook_id': res2['Item']['Id'],
                                           'backend_id': backend.id,
                                           'quickbook_name': res2['Item']['FullyQualifiedName']
                                           })
                                cat.env.cr.commit()
                        except:
                            result_dict = {
                                "SubItem": True,
                                "Type": "Category",
                                "Name": categ,
                                "ParentRef": {
                                    "name": category_list[category_list.index(categ) - 1],
                                    "value": id_list[category_list.index(categ) - 1],
                                },
                            }
                            res2 = self.update_category(method, arguments, result_dict)
                            cat = request.env['product.category'].search([('name', '=', categ)], limit=1)

                            cat.write({'quickbook_id': res2['data']['Item']['Id'],
                                       'backend_id': backend.id,
                                       'quickbook_name': res2['data']['Item']['FullyQualifiedName']
                                       })
                            cat.env.cr.commit()
                            try:
                                id_list.append(int(res2['data']['Item']['Id']))
                            except:
                                pass
                except:
                    pass
                try:
                    id_list.append(int(res1['QueryResponse']['Item'][0]['Id']))
                except:
                    pass
