import hashlib
import logging
import uuid
from datetime import timedelta

import requests

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Datetime

_logger = logging.getLogger(__name__)


class SaranOtpMixin(models.AbstractModel):
    _name = 'saran.otp.mixin'
    _description = 'Shared OTP helpers'

    @api.model
    def _icp(self):
        return self.env['ir.config_parameter'].sudo()

    @api.model
    def _get_param(self, key, default=None):
        return self._icp().get_param(key, default)

    @api.model
    def _get_int_param(self, key, default=0):
        value = self._get_param(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @api.model
    def _get_float_param(self, key, default=0.0):
        value = self._get_param(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @api.model
    def _otp_settings(self):
        return {
            'gateway_username': (self._get_param('saran_otp_oth.gateway_username') or '').strip(),
            'gateway_password': self._get_param('saran_otp_oth.gateway_password') or '',
            'sender_name': (self._get_param('saran_otp_oth.sender_name') or '').strip(),
            'send_url': (self._get_param('saran_otp_oth.send_url') or '').strip(),
            'credit_url': (self._get_param('saran_otp_oth.credit_url') or '').strip(),
            'default_country_code': (self._get_param('saran_otp_oth.default_country_code', '20') or '20').strip(),
            'otp_length': self._get_int_param('saran_otp_oth.otp_length', 6),
            'otp_validity_minutes': self._get_int_param('saran_otp_oth.otp_validity_minutes', 5),
            'resend_cooldown_seconds': self._get_int_param('saran_otp_oth.resend_cooldown_seconds', 60),
            'max_attempts': self._get_int_param('saran_otp_oth.max_attempts', 5),
            'http_timeout': self._get_float_param('saran_otp_oth.http_timeout', 20.0),
            'message_template': self._get_param(
                'saran_otp_oth.message_template',
                'Your OTP code is %(code)s. It expires in %(minutes)s minutes.'
            ) or 'Your OTP code is %(code)s. It expires in %(minutes)s minutes.',
            'enable_login': self._get_param('saran_otp_oth.enable_login', 'True') == 'True',
            'enable_signup': self._get_param('saran_otp_oth.enable_signup', 'True') == 'True',
            'enable_checkout': self._get_param('saran_otp_oth.enable_checkout', 'True') == 'True',
        }

    @api.model
    def _validate_gateway_settings(self):
        settings = self._otp_settings()
        missing = []
        for key in ('gateway_username', 'gateway_password', 'sender_name', 'send_url'):
            if not settings.get(key):
                missing.append(key)
        if missing:
            raise UserError(_('Missing OTP gateway settings: %s') % ', '.join(missing))
        return settings

    @api.model
    def _normalize_mobile(self, mobile):
        if not mobile:
            raise ValidationError(_('Mobile number is required.'))
        settings = self._otp_settings()
        digits = ''.join(ch for ch in str(mobile) if ch.isdigit())
        if not digits:
            raise ValidationError(_('The mobile number must contain digits.'))
        country_code = settings['default_country_code'].lstrip('+').strip() or '20'
        if digits.startswith('00'):
            digits = digits[2:]
        if digits.startswith(country_code):
            normalized = digits
        elif digits.startswith('0'):
            normalized = '%s%s' % (country_code, digits[1:])
        else:
            normalized = '%s%s' % (country_code, digits)
        if len(normalized) < len(country_code) + 8:
            raise ValidationError(_('The mobile number looks too short.'))
        return normalized

    @api.model
    def _hash_code(self, code):
        return hashlib.sha256((code or '').encode('utf-8')).hexdigest()

    @api.model
    def _generate_code(self, length=None):
        otp_length = length or self._otp_settings()['otp_length'] or 6
        otp_length = max(4, min(8, int(otp_length)))
        raw = str(uuid.uuid4().int)
        return raw[:otp_length]

    @api.model
    def _build_message(self, code):
        settings = self._otp_settings()
        template = settings['message_template']
        minutes = settings['otp_validity_minutes']
        try:
            return template % {'code': code, 'minutes': minutes}
        except Exception:
            return _('Your OTP code is %s. It expires in %s minutes.') % (code, minutes)

    @api.model
    def _mask_mobile(self, mobile):
        if not mobile or len(mobile) < 4:
            return mobile
        return '%s%s' % ('*' * max(len(mobile) - 4, 0), mobile[-4:])

    @api.model
    def _send_sms_victory_link(self, mobile, message, sms_lang='E'):
        settings = self._validate_gateway_settings()
        payload = {
            'UserName': settings['gateway_username'],
            'Password': settings['gateway_password'],
            'SMSText': message,
            'SMSLang': (sms_lang or 'E').upper(),
            'SMSSender': settings['sender_name'],
            'SMSReceiver': mobile,
            'SMSID': str(uuid.uuid4()),
        }
        try:
            response = requests.post(settings['send_url'], json=payload, timeout=settings['http_timeout'])
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.exception('OTP SMS HTTP request failed')
            raise UserError(_('OTP SMS request failed: %s') % exc) from exc

        body = (response.text or '').strip()
        if not body:
            raise UserError(_('OTP SMS gateway returned an empty response.'))
        try:
            status_code = int(body)
        except ValueError as exc:
            _logger.error('Unexpected OTP SMS gateway response: %s', body)
            raise UserError(_('Unexpected OTP SMS gateway response: %s') % body) from exc

        if status_code != 0:
            raise UserError(self._vl_status_message(status_code))
        return {
            'status_code': status_code,
            'sms_id': payload['SMSID'],
            'request_payload': payload,
        }

    @api.model
    def _check_credit_victory_link(self):
        settings = self._validate_gateway_settings()
        if not settings['credit_url']:
            raise UserError(_('Check Credit URL is not configured.'))
        payload = {
            'UserName': settings['gateway_username'],
            'Password': settings['gateway_password'],
        }
        try:
            response = requests.post(settings['credit_url'], json=payload, timeout=settings['http_timeout'])
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_('Credit check request failed: %s') % exc) from exc
        body = (response.text or '').strip()
        try:
            return int(body)
        except ValueError as exc:
            raise UserError(_('Unexpected credit check response: %s') % body) from exc

    @api.model
    def _vl_status_message(self, status_code):
        messages = {
            0: _('SMS accepted by the gateway.'),
            -1: _('An unknown SMS gateway error occurred.'),
            -2: _('Invalid destination mobile number.'),
            -3: _('The message text is empty.'),
            -5: _('Invalid SMS language.'),
            -7: _('Insufficient SMS credit.'),
            -8: _('The SMS sender is empty.'),
            -19: _('Invalid SMS receiver or dial format.'),
            -23: _('Invalid account operator connection.'),
            -26: _('Invalid SMSID. It must be a valid GUID.'),
            -29: _('Username or password is empty.'),
            -30: _('Invalid SMS sender name.'),
        }
        return messages.get(status_code, _('SMS gateway returned error code %s.') % status_code)

    @api.model
    def _otp_expires_at(self):
        return Datetime.now() + timedelta(minutes=self._otp_settings()['otp_validity_minutes'])
