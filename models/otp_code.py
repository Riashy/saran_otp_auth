import hashlib
import json
import logging
import random
import uuid
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def normalize_mobile(raw_mobile, default_country_code='20'):
    mobile = ''.join(ch for ch in (raw_mobile or '') if ch.isdigit())
    if not mobile:
        return ''
    if mobile.startswith('00'):
        mobile = mobile[2:]
    if mobile.startswith(default_country_code):
        return mobile
    if mobile.startswith('0'):
        return f"{default_country_code}{mobile[1:]}"
    return mobile


class SaranOtpCode(models.Model):
    _name = 'saran.otp.code'
    _description = 'Saran OTP Code'
    _order = 'create_date desc'
    _rec_name = 'mobile'

    mobile = fields.Char(required=True, index=True)
    purpose = fields.Selection([
        ('login', 'Login'),
        ('signup', 'Signup'),
        ('checkout', 'Checkout'),
    ], required=True, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, index=True)
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True, index=True)
    used_at = fields.Datetime()
    attempts = fields.Integer(default=0)
    request_ip = fields.Char()
    sms_uuid = fields.Char(index=True)
    gateway_status = fields.Char()
    message = fields.Char()
    user_id = fields.Many2one('res.users', ondelete='set null')
    partner_id = fields.Many2one('res.partner', ondelete='set null')
    signup_payload = fields.Text()

    @api.model
    def _icp(self):
        return self.env['ir.config_parameter'].sudo()

    @api.model
    def _get_int_param(self, key, default):
        value = self._icp().get_param(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @api.model
    def _get_default_country_code(self):
        return (self._icp().get_param('saran_otp_auth.default_country_code') or '20').strip()

    @api.model
    def _gateway_urls(self):
        send_url = self._icp().get_param(
            'saran_otp_auth.send_url',
            default='https://smsvas.vlserv.com/VLSMSPlatformResellerAPI/NewSendingAPI/api/SMSSender/SendSMS',
        )
        credit_url = self._icp().get_param(
            'saran_otp_auth.check_credit_url',
            default='https://smsvas.vlserv.com//VLSMSPlatformResellerAPI/CheckCreditApi/api/CheckCredit',
        )
        return send_url, credit_url

    @api.model
    def _gateway_credentials(self):
        icp = self._icp()
        return {
            'UserName': icp.get_param('saran_otp_auth.gateway_username') or '',
            'Password': icp.get_param('saran_otp_auth.gateway_password') or '',
            'SMSSender': icp.get_param('saran_otp_auth.gateway_sender') or '',
        }

    @api.model
    def _otp_length(self):
        length = self._get_int_param('saran_otp_auth.otp_length', 6)
        return min(max(length, 4), 8)

    @api.model
    def _ttl_minutes(self):
        ttl = self._get_int_param('saran_otp_auth.otp_ttl_minutes', 5)
        return min(max(ttl, 1), 30)

    @api.model
    def _resend_cooldown_seconds(self):
        value = self._get_int_param('saran_otp_auth.resend_cooldown_seconds', 60)
        return min(max(value, 0), 3600)

    @api.model
    def _max_attempts(self):
        value = self._get_int_param('saran_otp_auth.max_attempts', 5)
        return min(max(value, 1), 20)

    @api.model
    def _hash_code(self, code):
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret', default='')
        return hashlib.sha256(f'{secret}:{code}'.encode('utf-8')).hexdigest()

    @api.model
    def _generate_code(self):
        low = 10 ** (self._otp_length() - 1)
        high = (10 ** self._otp_length()) - 1
        return str(random.randint(low, high))

    @api.model
    def _get_gateway_error_message(self, status_code):
        return {
            0: _('Sent successfully.'),
            -1: _('Invalid username or password.'),
            -5: _('Invalid sender name.'),
            -19: _('Message text is invalid or empty.'),
            -26: _('The destination mobile number is invalid.'),
            -30: _('Insufficient SMS credit.'),
        }.get(status_code, _('Gateway returned status code %s.') % status_code)

    @api.model
    def _send_sms(self, mobile, message, sms_uuid=None, language='E'):
        send_url, _credit_url = self._gateway_urls()
        creds = self._gateway_credentials()
        if not creds['UserName'] or not creds['Password'] or not creds['SMSSender']:
            raise UserError(_('Please configure the OTP gateway credentials in Settings first.'))
        payload = {
            'UserName': creds['UserName'],
            'Password': creds['Password'],
            'SMSText': message,
            'SMSLang': (language or 'E').upper(),
            'SMSSender': creds['SMSSender'],
            'SMSReceiver': mobile,
            'SMSID': sms_uuid or str(uuid.uuid4()),
        }
        try:
            response = requests.post(send_url, json=payload, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.exception('OTP SMS request failed')
            raise UserError(_('SMS gateway connection failed: %s') % exc) from exc

        raw_body = response.text.strip()
        try:
            status_code = int(raw_body)
        except ValueError:
            try:
                status_code = int(response.json())
            except Exception:
                raise UserError(_('Unexpected SMS gateway response: %s') % raw_body)
        if status_code != 0:
            raise UserError(self._get_gateway_error_message(status_code))
        return status_code, payload['SMSID']

    @api.model
    def check_credit(self):
        _send_url, credit_url = self._gateway_urls()
        creds = self._gateway_credentials()
        payload = {
            'UserName': creds['UserName'],
            'Password': creds['Password'],
        }
        response = requests.post(credit_url, json=payload, timeout=20)
        response.raise_for_status()
        try:
            return int(response.text.strip())
        except ValueError:
            return response.text.strip()

    @api.model
    def _validate_enabled(self, feature_key):
        enabled = self._icp().get_param('saran_otp_auth.enabled', default='False') == 'True'
        feature = self._icp().get_param(feature_key, default='False') == 'True'
        if not enabled or not feature:
            raise UserError(_('OTP authentication is disabled for this flow.'))

    @api.model
    def _check_resend_window(self, mobile, purpose):
        cooldown = self._resend_cooldown_seconds()
        if not cooldown:
            return
        latest = self.search([
            ('mobile', '=', mobile),
            ('purpose', '=', purpose),
            ('state', '=', 'pending'),
        ], order='create_date desc', limit=1)
        if latest and latest.create_date:
            wait_until = fields.Datetime.to_datetime(latest.create_date) + timedelta(seconds=cooldown)
            if fields.Datetime.now() < wait_until:
                raise UserError(_('Please wait a moment before requesting another OTP.'))

    @api.model
    def create_and_send(self, mobile, purpose, user=None, partner=None, signup_payload=None, request_ip=None):
        mobile = normalize_mobile(mobile, self._get_default_country_code())
        if not mobile:
            raise ValidationError(_('A valid mobile number is required.'))
        self._check_resend_window(mobile, purpose)
        self.search([
            ('mobile', '=', mobile),
            ('purpose', '=', purpose),
            ('state', '=', 'pending'),
        ]).write({'state': 'cancelled'})

        code = self._generate_code()
        expires_at = fields.Datetime.now() + timedelta(minutes=self._ttl_minutes())
        otp = self.create({
            'mobile': mobile,
            'purpose': purpose,
            'code_hash': self._hash_code(code),
            'expires_at': expires_at,
            'request_ip': request_ip,
            'user_id': user.id if user else False,
            'partner_id': partner.id if partner else False,
            'signup_payload': json.dumps(signup_payload or {}),
            'sms_uuid': str(uuid.uuid4()),
        })
        sms_text = _('Your verification code is: %s') % code
        status_code, sms_uuid = self._send_sms(mobile, sms_text, sms_uuid=otp.sms_uuid)
        otp.write({
            'gateway_status': str(status_code),
            'sms_uuid': sms_uuid,
            'message': self._get_gateway_error_message(status_code),
        })
        return otp

    def verify_code(self, code):
        self.ensure_one()
        if self.state != 'pending':
            raise ValidationError(_('This OTP is no longer valid.'))
        if fields.Datetime.now() > self.expires_at:
            self.state = 'expired'
            raise ValidationError(_('This OTP has expired.'))
        if self.attempts >= self._max_attempts():
            self.state = 'cancelled'
            raise ValidationError(_('Maximum verification attempts exceeded.'))
        if self.code_hash != self._hash_code(code):
            self.attempts += 1
            if self.attempts >= self._max_attempts():
                self.state = 'cancelled'
            raise ValidationError(_('Invalid verification code.'))
        self.write({
            'state': 'used',
            'used_at': fields.Datetime.now(),
            'attempts': self.attempts + 1,
        })
        if self.partner_id:
            self.partner_id.sudo().write({
                'otp_mobile_verified': True,
                'otp_mobile_last_verified_at': fields.Datetime.now(),
            })
        return True

    @api.model
    def cron_expire_old_otps(self):
        records = self.search([
            ('state', '=', 'pending'),
            ('expires_at', '<', fields.Datetime.now()),
        ])
        records.write({'state': 'expired'})
