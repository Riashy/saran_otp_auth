from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaranOtpCode(models.Model):
    _name = 'saran.otp.code'
    _description = 'OTP Code'
    _order = 'create_date desc'
    _inherit = ['saran.otp.mixin']

    name = fields.Char(required=True, default='OTP')
    purpose = fields.Selection([
        ('login', 'Login'),
        ('signup', 'Signup'),
        ('checkout', 'Checkout'),
    ], required=True, index=True)
    mobile = fields.Char(required=True, index=True)
    state = fields.Selection([
        ('sent', 'Sent'),
        ('verified', 'Verified'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
    ], default='sent', required=True, index=True)
    user_id = fields.Many2one('res.users', ondelete='set null')
    partner_id = fields.Many2one('res.partner', ondelete='set null')
    sale_order_id = fields.Many2one('sale.order', ondelete='set null')
    code_hash = fields.Char(required=True)
    expires_at = fields.Datetime(required=True, index=True)
    verified_at = fields.Datetime()
    attempts_count = fields.Integer(default=0)
    max_attempts = fields.Integer(default=5)
    reference = fields.Char(index=True)
    last_error = fields.Text()
    metadata_json = fields.Text()

    _sql_constraints = [
        ('mobile_reference_unique_sent', 'unique(mobile, reference, state)', 'An active OTP already exists for this mobile and flow.'),
    ]

    @api.constrains('mobile')
    def _check_mobile(self):
        for rec in self:
            if not rec.mobile or not rec.mobile.isdigit():
                raise ValidationError(_('OTP mobile number must contain digits only.'))

    def _is_expired(self):
        self.ensure_one()
        return fields.Datetime.now() >= self.expires_at

    def action_mark_expired(self):
        self.filtered(lambda r: r.state == 'sent').write({'state': 'expired'})

    def action_cancel(self):
        self.filtered(lambda r: r.state == 'sent').write({'state': 'cancelled'})

    def verify_code(self, code):
        self.ensure_one()
        if self.state != 'sent':
            raise ValidationError(_('This OTP is no longer active.'))
        if self._is_expired():
            self.write({'state': 'expired'})
            raise ValidationError(_('This OTP has expired.'))
        if self.attempts_count >= self.max_attempts:
            self.write({'state': 'failed', 'last_error': _('Maximum attempts reached.')})
            raise ValidationError(_('Maximum OTP attempts reached.'))

        next_attempts = self.attempts_count + 1
        self.write({'attempts_count': next_attempts})
        if self.code_hash != self._hash_code(code):
            if next_attempts >= self.max_attempts:
                self.write({'state': 'failed', 'last_error': _('Maximum attempts reached.')})
            raise ValidationError(_('Invalid OTP code.'))

        self.write({
            'state': 'verified',
            'verified_at': fields.Datetime.now(),
        })
        return True

    @api.model
    def issue_otp(self, purpose, mobile, user=None, partner=None, sale_order=None, reference=None, sms_lang='E'):
        settings = self._otp_settings()
        mobile = self._normalize_mobile(mobile)
        reference = reference or '%s:%s' % (purpose, mobile)
        active_otps = self.search([
            ('mobile', '=', mobile),
            ('reference', '=', reference),
            ('purpose', '=', purpose),
            ('state', '=', 'sent'),
        ], order='create_date desc')
        if active_otps:
            latest = active_otps[0]
            seconds_since_latest = 0
            if latest.create_date:
                seconds_since_latest = (fields.Datetime.now() - latest.create_date).total_seconds()
            if seconds_since_latest < settings['resend_cooldown_seconds']:
                raise ValidationError(_('Please wait before requesting a new OTP.'))
            active_otps.action_cancel()

        code = self._generate_code(settings['otp_length'])
        message = self._build_message(code)
        sms_response = self._send_sms_victory_link(mobile, message, sms_lang=sms_lang)
        vals = {
            'name': _('OTP for %s') % purpose,
            'purpose': purpose,
            'mobile': mobile,
            'user_id': user.id if user else False,
            'partner_id': partner.id if partner else False,
            'sale_order_id': sale_order.id if sale_order else False,
            'code_hash': self._hash_code(code),
            'expires_at': self._otp_expires_at(),
            'max_attempts': settings['max_attempts'],
            'reference': reference,
            'metadata_json': str(sms_response),
        }
        return self.create(vals)

    @api.model
    def cron_expire_old_otps(self):
        expired = self.search([
            ('state', '=', 'sent'),
            ('expires_at', '<=', fields.Datetime.now()),
        ])
        expired.action_mark_expired()
