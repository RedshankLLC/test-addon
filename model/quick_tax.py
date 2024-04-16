# -*- coding: utf-8 -*-
#
#
#    TechSpawn Solutions Pvt. Ltd.
#    Copyright (C) 2016-TODAY TechSpawn(<http://www.techspawn.com>).
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
from odoo import models, fields, api, _
from odoo.exceptions import UserError

from ..unit.quick_tax_exporter import QboTaxExport


_logger = logging.getLogger(__name__)

class quickbook_tax_template(models.Model):
    _inherit = 'account.tax'

    backend_id = fields.Many2one(comodel_name='qb.backend',
                                 string='Quick Backend', store=True,
                                 readonly=False, required=False,
                                 )
    quickbook_id = fields.Char(
        string='ID on Quickbook', readonly=False, required=False)
    rate_quickbook_id = fields.Char(
        string='Rate ID on Quickbook', readonly=False, required=False)
    sync_date = fields.Datetime(string='Last synchronization date')

    def sync_Tax(self):
        for backend in self.backend_id:
            self.export_tax_data(backend)
        return

    def export_tax_data(self, backend):
        if not self.backend_id or self.quickbook_id:
            raise UserError(_("You can't update created taxes. QBO doesn't support tax update."))
        mapper = self.env['account.tax'].search(
            [('backend_id', '=', backend.id), ('quickbook_id', '=', self.quickbook_id)], limit=1)

        method = 'taxservice/taxcode'
        arguments = [mapper.quickbook_id or None, self]

        export = QboTaxExport(backend)
        res = export.export_tax(method, arguments)

        if mapper.id == self.id and self.quickbook_id:
            if mapper and (res['status'] == 200 or res['status'] == 201):
                mapper.write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['TaxCodeId']})
                for child_id in arguments[1].children_tax_ids:
                    for child_tax_id in res['data']['TaxRateDetails']:
                        child_id.write({'rate_quickbook_id': child_tax_id['TaxRateId']})
            elif (res['status'] == 200 or res['status'] == 201):
                arguments[1].write(
                    {'backend_id': backend.id, 'quickbook_id': res['data']['TaxCodeId']})
                for child_id in arguments[1].children_tax_ids:
                    for child_tax_id in res['data']['TaxRateDetails']:
                        child_id.write({'rate_quickbook_id': child_tax_id['TaxRateId']})
        elif (res['status'] == 200 or res['status'] == 201):
            arguments[1].write(
                {'backend_id': backend.id, 'quickbook_id': res['data']['TaxCodeId']})
            for child_id in arguments[1].children_tax_ids:
                for child_tax_id in res['data']['TaxRateDetails']:
                    child_id.write({'rate_quickbook_id': child_tax_id['TaxRateId']})

        if res['status'] == 500 or res['status'] == 400:
            for errors in res['errors']['Fault']['Error']:
                msg = errors['Message']
                code = errors['code']
                name = res['name']
                details = 'Message: ' + msg + '\n' + 'Code: ' + \
                          code + '\n' + 'Name: ' + str(name.name) + '\n' + 'Detail: ' + errors['Detail']
                if errors['code']:
                    _logger.info(_(details))

    @api.model
    def default_get(self, fields):
        res = super(quickbook_tax_template, self).default_get(fields)
        ids = self.env['qb.backend'].search([]).id
        res['backend_id'] = ids
        return res