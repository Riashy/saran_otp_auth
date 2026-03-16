from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    saran_otp_enabled = fields.Boolean(string='Enable OTP', config_parameter='saran_otp_auth.enabled')
    saran_otp_login_enabled = fields.Boolean(string='Enable OTP Login', config_parameter='saran_otp_auth.login_enabled')
    saran_otp_signup_enabled = fields.Boolean(string='Enable OTP Signup', config_parameter='saran_otp_auth.signup_enabled')
    saran_otp_checkout_enabled = fields.Boolean(string='Enable OTP Checkout', config_parameter='saran_otp_auth.checkout_enabled')
    saran_otp_gateway_username = fields.Char(string='Gateway Username', config_parameter='saran_otp_auth.gateway_username')
    saran_otp_gateway_password = fields.Char(string='Gateway Password', config_parameter='saran_otp_auth.gateway_password')
    saran_otp_gateway_sender = fields.Char(string='Sender Name', config_parameter='saran_otp_auth.gateway_sender')
    saran_otp_send_url = fields.Char(
        string='Send URL',
        config_parameter='saran_otp_auth.send_url',
        default='https://smsvas.vlserv.com/VLSMSPlatformResellerAPI/NewSendingAPI/api/SMSSender/SendSMS',
    )
    saran_otp_check_credit_url = fields.Char(
        string='Check Credit URL',
        config_parameter='saran_otp_auth.check_credit_url',
        default='https://smsvas.vlserv.com//VLSMSPlatformResellerAPI/CheckCreditApi/api/CheckCredit',
    )
    saran_otp_default_country_code = fields.Char(string='Default Country Code', config_parameter='saran_otp_auth.default_country_code', default='20')
    saran_otp_length = fields.Integer(string='OTP Length', config_parameter='saran_otp_auth.otp_length', default=6)
    saran_otp_ttl_minutes = fields.Integer(string='OTP TTL (minutes)', config_parameter='saran_otp_auth.otp_ttl_minutes', default=5)
    saran_otp_resend_cooldown_seconds = fields.Integer(string='Resend Cooldown (seconds)', config_parameter='saran_otp_auth.resend_cooldown_seconds', default=60)
    saran_otp_max_attempts = fields.Integer(string='Max Attempts', config_parameter='saran_otp_auth.max_attempts', default=5)
