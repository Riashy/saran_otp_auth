from odoo import api, fields, models

from .otp_code import normalize_mobile


class ResPartner(models.Model):
    _inherit = 'res.partner'

    otp_mobile_verified = fields.Boolean(string='OTP Mobile Verified', default=False, copy=False)
    otp_mobile_last_verified_at = fields.Datetime(string='OTP Verified At', copy=False)
    otp_mobile_normalized = fields.Char(
        string='Normalized Mobile',
        compute='_compute_otp_mobile_normalized',
        store=True,
        index=True,
    )

    @api.depends('mobile')
    def _compute_otp_mobile_normalized(self):
        default_cc = self.env['ir.config_parameter'].sudo().get_param('saran_otp_auth.default_country_code', default='20')
        for partner in self:
            partner.otp_mobile_normalized = normalize_mobile(partner.mobile, default_cc)
