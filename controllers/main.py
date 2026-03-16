import logging
import secrets

from odoo import _, fields, http
from odoo.exceptions import ValidationError
from odoo.http import request

try:
    from odoo.addons.website_sale.controllers.main import WebsiteSale
except Exception:  # pragma: no cover
    WebsiteSale = object

_logger = logging.getLogger(__name__)


class SaranOtpController(http.Controller):

    def _otp_model(self):
        return request.env['saran.otp.code'].sudo()

    def _settings(self):
        return self._otp_model()._otp_settings()

    def _session_set(self, key, value):
        request.session[key] = value

    def _session_get(self, key, default=None):
        return request.session.get(key, default)

    def _clear_flow(self, flow_name):
        keys = [
            flow_name,
            '%s_mobile' % flow_name,
            '%s_mobile_masked' % flow_name,
            '%s_user_id' % flow_name,
            '%s_partner_id' % flow_name,
            '%s_order_id' % flow_name,
            '%s_otp_id' % flow_name,
            '%s_payload' % flow_name,
        ]
        for key in keys:
            request.session.pop(key, None)

    def _login_user_without_password(self, user):
        if not user:
            return
        try:
            request.session.logout(keep_db=True)
        except Exception:
            pass
        request.session.db = request.db
        request.session.uid = user.id
        request.session.login = user.login
        if hasattr(user, '_compute_session_token'):
            try:
                request.session.session_token = user._compute_session_token(request.session.sid)
            except Exception:
                _logger.debug('Unable to compute session token for OTP login', exc_info=True)
        try:
            request.update_env(user=user)
        except Exception:
            _logger.debug('Unable to update request env during OTP login', exc_info=True)
        try:
            http.root.session_store.rotate(request.session, request.env)
            request.future_response.set_cookie(
                'session_id',
                request.session.sid,
                max_age=getattr(http, 'SESSION_LIFETIME', None),
                httponly=True,
            )
        except Exception:
            _logger.debug('Unable to rotate session during OTP login', exc_info=True)

    def _find_user_by_mobile(self, mobile):
        normalized = self._otp_model()._normalize_mobile(mobile)
        partners = request.env['res.partner'].sudo().search([
            '|', ('mobile', '=', normalized), ('phone', '=', normalized)
        ])
        if not partners:
            alt = (mobile or '').strip()
            partners = request.env['res.partner'].sudo().search([
                '|', ('mobile', '=', alt), ('phone', '=', alt)
            ])
        users = request.env['res.users'].sudo().search([
            ('partner_id', 'in', partners.ids),
            ('active', '=', True),
            ('saran_otp_enabled', '=', True),
        ], order='id asc')
        return users[:1], normalized

    def _mark_partner_mobile_verified(self, partner):
        if partner:
            partner.sudo().write({
                'saran_otp_mobile_verified': True,
                'saran_otp_mobile_verified_at': fields.Datetime.now(),
            })

    def _render(self, template, values=None):
        values = values or {}
        values.setdefault('settings', self._settings())
        return request.render(template, values)

    @http.route('/otp/login', type='http', auth='public', website=True, sitemap=False)
    def otp_login_page(self, **kw):
        return self._render('saran_otp_oth.otp_login_page', {
            'mobile': kw.get('mobile', ''),
            'error': kw.get('error'),
            'success': kw.get('success'),
            'masked_mobile': self._session_get('otp_login_mobile_masked'),
            'otp_sent': bool(self._session_get('otp_login_otp_id')),
        })

    @http.route('/otp/login/send', type='http', auth='public', methods=['POST'], website=True, csrf=True, sitemap=False)
    def otp_login_send(self, mobile=None, **post):
        settings = self._settings()
        if not settings['enable_login']:
            return request.redirect('/web/login')
        try:
            user, normalized = self._find_user_by_mobile(mobile)
            if not user:
                raise ValidationError(_('No OTP-enabled user is linked to this mobile number.'))
            otp = self._otp_model().issue_otp(
                purpose='login',
                mobile=normalized,
                user=user,
                partner=user.partner_id,
                reference='login:%s' % user.id,
            )
            self._session_set('otp_login', True)
            self._session_set('otp_login_mobile', normalized)
            self._session_set('otp_login_mobile_masked', self._otp_model()._mask_mobile(normalized))
            self._session_set('otp_login_user_id', user.id)
            self._session_set('otp_login_partner_id', user.partner_id.id)
            self._session_set('otp_login_otp_id', otp.id)
            return self._render('saran_otp_oth.otp_login_page', {
                'mobile': normalized,
                'masked_mobile': self._otp_model()._mask_mobile(normalized),
                'otp_sent': True,
                'success': _('OTP code sent successfully.'),
            })
        except Exception as exc:
            return self._render('saran_otp_oth.otp_login_page', {
                'mobile': mobile or '',
                'error': str(exc),
                'otp_sent': False,
            })

    @http.route('/otp/login/verify', type='http', auth='public', methods=['POST'], website=True, csrf=True, sitemap=False)
    def otp_login_verify(self, code=None, redirect='/web', **post):
        otp_id = self._session_get('otp_login_otp_id')
        user_id = self._session_get('otp_login_user_id')
        if not otp_id or not user_id:
            return request.redirect('/otp/login')
        try:
            otp = self._otp_model().browse(int(otp_id)).exists()
            user = request.env['res.users'].sudo().browse(int(user_id)).exists()
            if not otp or not user:
                raise ValidationError(_('OTP session is invalid.'))
            otp.verify_code((code or '').strip())
            self._mark_partner_mobile_verified(user.partner_id)
            self._login_user_without_password(user)
            self._clear_flow('otp_login')
            return request.redirect(redirect or '/web')
        except Exception as exc:
            return self._render('saran_otp_oth.otp_login_page', {
                'mobile': self._session_get('otp_login_mobile'),
                'masked_mobile': self._session_get('otp_login_mobile_masked'),
                'otp_sent': True,
                'error': str(exc),
            })

    @http.route('/otp/signup', type='http', auth='public', website=True, sitemap=False)
    def otp_signup_page(self, **kw):
        return self._render('saran_otp_oth.otp_signup_page', {
            'error': kw.get('error'),
            'success': kw.get('success'),
            'otp_sent': bool(self._session_get('otp_signup_otp_id')),
            'payload': self._session_get('otp_signup_payload', {}),
            'masked_mobile': self._session_get('otp_signup_mobile_masked'),
        })

    @http.route('/otp/signup/send', type='http', auth='public', methods=['POST'], website=True, csrf=True, sitemap=False)
    def otp_signup_send(self, name=None, login=None, email=None, mobile=None, **post):
        settings = self._settings()
        if not settings['enable_signup']:
            return request.redirect('/web/login')
        payload = {
            'name': (name or '').strip(),
            'login': (login or email or '').strip(),
            'email': (email or login or '').strip(),
            'mobile': (mobile or '').strip(),
        }
        try:
            if not payload['name']:
                raise ValidationError(_('Name is required.'))
            if not payload['login']:
                raise ValidationError(_('Login or email is required.'))
            normalized = self._otp_model()._normalize_mobile(payload['mobile'])
            payload['mobile'] = normalized
            existing_user = request.env['res.users'].sudo().search([('login', '=', payload['login'])], limit=1)
            if existing_user:
                raise ValidationError(_('This login already exists.'))
            existing_partner = request.env['res.partner'].sudo().search(['|', ('mobile', '=', normalized), ('phone', '=', normalized)], limit=1)
            if existing_partner.user_ids:
                raise ValidationError(_('This mobile number is already linked to a user.'))
            otp = self._otp_model().issue_otp(
                purpose='signup',
                mobile=normalized,
                reference='signup:%s' % normalized,
            )
            self._session_set('otp_signup', True)
            self._session_set('otp_signup_mobile', normalized)
            self._session_set('otp_signup_mobile_masked', self._otp_model()._mask_mobile(normalized))
            self._session_set('otp_signup_payload', payload)
            self._session_set('otp_signup_otp_id', otp.id)
            return self._render('saran_otp_oth.otp_signup_page', {
                'otp_sent': True,
                'masked_mobile': self._otp_model()._mask_mobile(normalized),
                'payload': payload,
                'success': _('OTP code sent successfully.'),
            })
        except Exception as exc:
            return self._render('saran_otp_oth.otp_signup_page', {
                'error': str(exc),
                'payload': payload,
            })

    @http.route('/otp/signup/verify', type='http', auth='public', methods=['POST'], website=True, csrf=True, sitemap=False)
    def otp_signup_verify(self, code=None, redirect='/web', **post):
        otp_id = self._session_get('otp_signup_otp_id')
        payload = self._session_get('otp_signup_payload', {})
        if not otp_id or not payload:
            return request.redirect('/otp/signup')
        try:
            otp = self._otp_model().browse(int(otp_id)).exists()
            if not otp:
                raise ValidationError(_('OTP session is invalid.'))
            otp.verify_code((code or '').strip())
            portal_group = request.env.ref('base.group_portal')
            password = secrets.token_urlsafe(24)
            partner = request.env['res.partner'].sudo().create({
                'name': payload['name'],
                'email': payload['email'] or False,
                'mobile': payload['mobile'],
                'saran_otp_mobile_verified': True,
                'saran_otp_mobile_verified_at': fields.Datetime.now(),
            })
            user = request.env['res.users'].sudo().with_context(no_reset_password=True).create({
                'name': payload['name'],
                'login': payload['login'],
                'email': payload['email'] or False,
                'partner_id': partner.id,
                'password': password,
                'groups_id': [(6, 0, [portal_group.id])],
                'saran_otp_enabled': True,
            })
            self._login_user_without_password(user)
            self._clear_flow('otp_signup')
            return request.redirect(redirect or '/web')
        except Exception as exc:
            return self._render('saran_otp_oth.otp_signup_page', {
                'error': str(exc),
                'payload': payload,
                'otp_sent': True,
                'masked_mobile': self._session_get('otp_signup_mobile_masked'),
            })

    @http.route('/otp/checkout', type='http', auth='public', website=True, sitemap=False)
    def otp_checkout_page(self, **kw):
        order_id = self._session_get('otp_checkout_order_id')
        order = request.env['sale.order'].sudo().browse(order_id).exists() if order_id else False
        return self._render('saran_otp_oth.otp_checkout_page', {
            'error': kw.get('error'),
            'success': kw.get('success'),
            'otp_sent': bool(self._session_get('otp_checkout_otp_id')),
            'masked_mobile': self._session_get('otp_checkout_mobile_masked'),
            'sale_order': order,
        })

    @http.route('/otp/checkout/send', type='http', auth='public', methods=['POST'], website=True, csrf=True, sitemap=False)
    def otp_checkout_send(self, mobile=None, **post):
        order_id = self._session_get('otp_checkout_order_id')
        order = request.env['sale.order'].sudo().browse(order_id).exists() if order_id else False
        if not order:
            return request.redirect('/shop/payment')
        try:
            normalized = self._otp_model()._normalize_mobile(mobile or order.partner_id.mobile or order.partner_id.phone)
            if order.partner_id:
                order.partner_id.sudo().write({'mobile': normalized})
            otp = self._otp_model().issue_otp(
                purpose='checkout',
                mobile=normalized,
                partner=order.partner_id,
                sale_order=order,
                reference='checkout:%s' % order.id,
            )
            self._session_set('otp_checkout_mobile', normalized)
            self._session_set('otp_checkout_mobile_masked', self._otp_model()._mask_mobile(normalized))
            self._session_set('otp_checkout_otp_id', otp.id)
            return self._render('saran_otp_oth.otp_checkout_page', {
                'otp_sent': True,
                'masked_mobile': self._otp_model()._mask_mobile(normalized),
                'sale_order': order,
                'success': _('OTP code sent successfully.'),
            })
        except Exception as exc:
            return self._render('saran_otp_oth.otp_checkout_page', {
                'error': str(exc),
                'sale_order': order,
                'otp_sent': False,
            })

    @http.route('/otp/checkout/verify', type='http', auth='public', methods=['POST'], website=True, csrf=True, sitemap=False)
    def otp_checkout_verify(self, code=None, **post):
        otp_id = self._session_get('otp_checkout_otp_id')
        order_id = self._session_get('otp_checkout_order_id')
        order = request.env['sale.order'].sudo().browse(order_id).exists() if order_id else False
        if not otp_id or not order:
            return request.redirect('/shop/payment')
        try:
            otp = self._otp_model().browse(int(otp_id)).exists()
            if not otp:
                raise ValidationError(_('OTP session is invalid.'))
            otp.verify_code((code or '').strip())
            order.sudo().write({
                'saran_otp_checkout_verified': True,
                'saran_otp_checkout_verified_at': fields.Datetime.now(),
            })
            self._mark_partner_mobile_verified(order.partner_id)
            self._clear_flow('otp_checkout')
            return request.redirect('/shop/payment')
        except Exception as exc:
            return self._render('saran_otp_oth.otp_checkout_page', {
                'error': str(exc),
                'sale_order': order,
                'otp_sent': True,
                'masked_mobile': self._session_get('otp_checkout_mobile_masked'),
            })


class SaranOtpWebsiteSale(WebsiteSale):

    @http.route()
    def shop_payment(self, **post):
        settings = request.env['saran.otp.code'].sudo()._otp_settings()
        if settings.get('enable_checkout'):
            order = request.website.sale_get_order()
            if order and order.order_line and not order.saran_otp_checkout_verified:
                request.session['otp_checkout_order_id'] = order.id
                return request.redirect('/otp/checkout')
        return super().shop_payment(**post)
