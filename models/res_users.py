from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = 'res.users'

    saran_otp_enabled = fields.Boolean(string='Allow OTP Login', default=True)

    @api.constrains('saran_otp_enabled', 'partner_id')
    def _check_unique_mobile_when_otp_enabled(self):
        for user in self.filtered(lambda u: u.saran_otp_enabled and u.partner_id and (u.partner_id.mobile or u.partner_id.phone)):
            mobile_candidates = [m for m in [user.partner_id.mobile, user.partner_id.phone] if m]
            if not mobile_candidates:
                continue
            peers = self.search([
                ('id', '!=', user.id),
                ('saran_otp_enabled', '=', True),
                ('partner_id', '!=', False),
                '|', ('partner_id.mobile', 'in', mobile_candidates), ('partner_id.phone', 'in', mobile_candidates),
            ], limit=1)
            if peers:
                raise ValidationError('OTP-enabled users must have unique mobile numbers.')
