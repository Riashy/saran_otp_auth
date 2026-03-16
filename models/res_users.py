from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    otp_auth_enabled = fields.Boolean(string='Enable OTP Authentication', default=True)
