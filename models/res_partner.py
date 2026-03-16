from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    saran_otp_mobile_verified = fields.Boolean(string='OTP Mobile Verified', default=False)
    saran_otp_mobile_verified_at = fields.Datetime(string='OTP Verified At')
