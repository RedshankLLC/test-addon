from odoo import _, fields, models, api
import os, json

class AccountInherit(models.Model):
    _inherit = 'account.account'

    def __init__(self, cr, uid, name):
        file_path = os.path.dirname(os.path.realpath(__file__))[:-6] + '/static/test.json'
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        option =[]
        for i in data['data']:
            option.append(tuple(i))
        super(AccountInherit, self).__init__(cr, uid, name)
        type_selection = self._fields['account_type'].selection
        for x in option:
            if x not in type_selection:
                type_selection.append(x)