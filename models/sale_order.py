from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    saran_otp_checkout_verified = fields.Boolean(string='Checkout OTP Verified', default=False)
    saran_otp_checkout_verified_at = fields.Datetime(string='Checkout OTP Verified At')
