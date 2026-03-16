from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    saran_otp_enable_login = fields.Boolean(
        string='Enable OTP Login',
        config_parameter='saran_otp_oth.enable_login',
        default=True,
    )
    saran_otp_enable_signup = fields.Boolean(
        string='Enable OTP Signup',
        config_parameter='saran_otp_oth.enable_signup',
        default=True,
    )
    saran_otp_enable_checkout = fields.Boolean(
        string='Require OTP Before Payment',
        config_parameter='saran_otp_oth.enable_checkout',
        default=True,
    )
    saran_otp_gateway_username = fields.Char(
        string='Gateway Username',
        config_parameter='saran_otp_oth.gateway_username',
    )
    saran_otp_gateway_password = fields.Char(
        string='Gateway Password',
        config_parameter='saran_otp_oth.gateway_password',
    )
    saran_otp_sender_name = fields.Char(
        string='Sender Name',
        config_parameter='saran_otp_oth.sender_name',
    )
    saran_otp_send_url = fields.Char(
        string='Send URL',
        config_parameter='saran_otp_oth.send_url',
        default='https://smsvas.vlserv.com/VLSMSPlatformResellerAPI/NewSendingAPI/api/SMSSender/SendSMS',
    )
    saran_otp_credit_url = fields.Char(
        string='Check Credit URL',
        config_parameter='saran_otp_oth.credit_url',
        default='https://smsvas.vlserv.com/VLSMSPlatformResellerAPI/CheckCreditApi/api/CheckCredit',
    )
    saran_otp_default_country_code = fields.Char(
        string='Default Country Code',
        config_parameter='saran_otp_oth.default_country_code',
        default='20',
    )
    saran_otp_length = fields.Integer(
        string='OTP Length',
        config_parameter='saran_otp_oth.otp_length',
        default=6,
    )
    saran_otp_validity_minutes = fields.Integer(
        string='Validity (Minutes)',
        config_parameter='saran_otp_oth.otp_validity_minutes',
        default=5,
    )
    saran_otp_resend_cooldown_seconds = fields.Integer(
        string='Resend Cooldown (Seconds)',
        config_parameter='saran_otp_oth.resend_cooldown_seconds',
        default=60,
    )
    saran_otp_max_attempts = fields.Integer(
        string='Max Attempts',
        config_parameter='saran_otp_oth.max_attempts',
        default=5,
    )
    saran_otp_http_timeout = fields.Float(
        string='HTTP Timeout (Seconds)',
        config_parameter='saran_otp_oth.http_timeout',
        default=20.0,
    )
    saran_otp_message_template = fields.Char(
        string='SMS Template',
        config_parameter='saran_otp_oth.message_template',
        default='Your OTP code is %(code)s. It expires in %(minutes)s minutes.',
    )
    saran_otp_credit_balance = fields.Integer(string='Credit Balance', readonly=True)

    def action_saran_otp_check_credit(self):
        self.ensure_one()
        credit = self.env['saran.otp.code']._check_credit_victory_link()
        self.saran_otp_credit_balance = credit
        raise UserError(_('Current SMS credit: %s') % credit)
