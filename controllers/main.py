import logging

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

from ..models.otp_code import normalize_mobile

_logger = logging.getLogger(__name__)


class SaranOtpController(http.Controller):

    def _render(self, template, values=None):
        values = values or {}
        values.setdefault('mobile', '')
        values.setdefault('message', '')
        values.setdefault('error', '')
        return request.render(template, values)

    def _login_user_session(self, user):
        # Best-effort session bootstrap for OTP login.
        request.session.uid = user.id
        request.session.login = user.login
        request.session.db = request.db
        request.session.context = dict(request.env.context, uid=user.id, lang=user.lang or request.env.lang, tz=user.tz or request.env.context.get('tz'))
        request.update_env(user=user)

    @http.route('/otp/login', type='http', auth='public', website=True, sitemap=False)
    def otp_login_page(self, **kwargs):
        return self._render('saran_otp_auth.otp_login_template')

    @http.route('/otp/login/send', type='http', auth='public', website=True, methods=['POST'], csrf=True, sitemap=False)
    def otp_login_send(self, mobile=None, **post):
        try:
            request.env['saran.otp.code'].sudo()._validate_enabled('saran_otp_auth.login_enabled')
            mobile = normalize_mobile(mobile, request.env['saran.otp.code'].sudo()._get_default_country_code())
            if not mobile:
                raise ValidationError(_('Enter a valid mobile number.'))
            user = request.env['res.users'].sudo().search([
                ('otp_auth_enabled', '=', True),
                ('partner_id.otp_mobile_normalized', '=', mobile),
                ('share', '=', False),
            ], limit=1)
            if not user:
                raise ValidationError(_('No internal user is linked to this mobile number.'))
            request.env['saran.otp.code'].sudo().create_and_send(
                mobile, 'login', user=user, partner=user.partner_id, request_ip=request.httprequest.remote_addr
            )
            return self._render('saran_otp_auth.otp_login_template', {
                'mobile': mobile,
                'message': _('A verification code has been sent.'),
                'otp_stage': 'verify',
            })
        except Exception as exc:
            return self._render('saran_otp_auth.otp_login_template', {'mobile': mobile or '', 'error': str(exc)})

    @http.route('/otp/login/verify', type='http', auth='public', website=True, methods=['POST'], csrf=True, sitemap=False)
    def otp_login_verify(self, mobile=None, otp_code=None, **post):
        mobile = normalize_mobile(mobile, request.env['saran.otp.code'].sudo()._get_default_country_code())
        otp = request.env['saran.otp.code'].sudo().search([
            ('mobile', '=', mobile),
            ('purpose', '=', 'login'),
            ('state', '=', 'pending'),
        ], order='create_date desc', limit=1)
        try:
            if not otp:
                raise ValidationError(_('No pending verification code was found for this mobile number.'))
            otp.verify_code(otp_code or '')
            user = otp.user_id.sudo()
            if not user:
                raise ValidationError(_('The linked user could not be found.'))
            self._login_user_session(user)
            return request.redirect('/web')
        except Exception as exc:
            return self._render('saran_otp_auth.otp_login_template', {
                'mobile': mobile,
                'error': str(exc),
                'otp_stage': 'verify',
            })

    @http.route('/otp/signup', type='http', auth='public', website=True, sitemap=False)
    def otp_signup_page(self, **kwargs):
        return self._render('saran_otp_auth.otp_signup_template', {'signup_values': kwargs})

    @http.route('/otp/signup/send', type='http', auth='public', website=True, methods=['POST'], csrf=True, sitemap=False)
    def otp_signup_send(self, **post):
        vals = {
            'name': (post.get('name') or '').strip(),
            'login': (post.get('login') or '').strip(),
            'password': post.get('password') or '',
            'confirm_password': post.get('confirm_password') or '',
            'mobile': (post.get('mobile') or '').strip(),
        }
        try:
            request.env['saran.otp.code'].sudo()._validate_enabled('saran_otp_auth.signup_enabled')
            if not vals['name'] or not vals['login'] or not vals['password']:
                raise ValidationError(_('Name, email/login, password, and mobile are required.'))
            if vals['password'] != vals['confirm_password']:
                raise ValidationError(_('Password confirmation does not match.'))
            mobile = normalize_mobile(vals['mobile'], request.env['saran.otp.code'].sudo()._get_default_country_code())
            if not mobile:
                raise ValidationError(_('Enter a valid mobile number.'))
            existing_user = request.env['res.users'].sudo().search([('login', '=', vals['login'])], limit=1)
            if existing_user:
                raise ValidationError(_('A user already exists with this login/email.'))
            existing_mobile = request.env['res.partner'].sudo().search([('otp_mobile_normalized', '=', mobile)], limit=1)
            if existing_mobile:
                raise ValidationError(_('A partner already exists with this mobile number.'))
            payload = {'name': vals['name'], 'login': vals['login'], 'password': vals['password'], 'mobile': mobile}
            request.env['saran.otp.code'].sudo().create_and_send(mobile, 'signup', signup_payload=payload, request_ip=request.httprequest.remote_addr)
            return self._render('saran_otp_auth.otp_signup_template', {
                'signup_values': vals,
                'mobile': mobile,
                'message': _('A verification code has been sent.'),
                'otp_stage': 'verify',
            })
        except Exception as exc:
            return self._render('saran_otp_auth.otp_signup_template', {'signup_values': vals, 'error': str(exc)})

    @http.route('/otp/signup/verify', type='http', auth='public', website=True, methods=['POST'], csrf=True, sitemap=False)
    def otp_signup_verify(self, mobile=None, otp_code=None, **post):
        mobile = normalize_mobile(mobile, request.env['saran.otp.code'].sudo()._get_default_country_code())
        otp = request.env['saran.otp.code'].sudo().search([
            ('mobile', '=', mobile),
            ('purpose', '=', 'signup'),
            ('state', '=', 'pending'),
        ], order='create_date desc', limit=1)
        try:
            if not otp:
                raise ValidationError(_('No pending verification code was found for this mobile number.'))
            otp.verify_code(otp_code or '')
            payload = otp.signup_payload and __import__('json').loads(otp.signup_payload) or {}
            login = payload.get('login')
            password = payload.get('password')
            name = payload.get('name')
            if not login or not password or not name:
                raise ValidationError(_('The pending signup data is incomplete.'))
            partner = request.env['res.partner'].sudo().create({
                'name': name,
                'mobile': mobile,
                'otp_mobile_verified': True,
                'otp_mobile_last_verified_at': otp.used_at,
            })
            user = request.env['res.users'].sudo().create({
                'name': name,
                'login': login,
                'password': password,
                'groups_id': [(6, 0, [request.env.ref('base.group_portal').id])],
                'partner_id': partner.id,
            })
            self._login_user_session(user)
            return request.redirect('/web')
        except Exception as exc:
            return self._render('saran_otp_auth.otp_signup_template', {
                'mobile': mobile,
                'error': str(exc),
                'otp_stage': 'verify',
                'signup_values': post,
            })

    @http.route('/shop/otp/send', type='http', auth='public', website=True, methods=['POST'], csrf=True, sitemap=False)
    def shop_otp_send(self, mobile=None, **post):
        order = request.website.sale_get_order()
        if not order:
            return request.redirect('/shop/cart')
        try:
            request.env['saran.otp.code'].sudo()._validate_enabled('saran_otp_auth.checkout_enabled')
            mobile = normalize_mobile(mobile or order.partner_id.mobile, request.env['saran.otp.code'].sudo()._get_default_country_code())
            if not mobile:
                raise ValidationError(_('Enter a valid mobile number before continuing to payment.'))
            order.partner_id.sudo().write({'mobile': mobile})
            request.env['saran.otp.code'].sudo().create_and_send(
                mobile, 'checkout', partner=order.partner_id, request_ip=request.httprequest.remote_addr
            )
            return request.redirect('/shop/payment?otp_sent=1')
        except Exception as exc:
            return request.redirect('/shop/payment?otp_error=%s' % http.url_quote(str(exc)))

    @http.route('/shop/otp/verify', type='http', auth='public', website=True, methods=['POST'], csrf=True, sitemap=False)
    def shop_otp_verify(self, mobile=None, otp_code=None, **post):
        order = request.website.sale_get_order()
        if not order:
            return request.redirect('/shop/cart')
        mobile = normalize_mobile(mobile or order.partner_id.mobile, request.env['saran.otp.code'].sudo()._get_default_country_code())
        otp = request.env['saran.otp.code'].sudo().search([
            ('mobile', '=', mobile),
            ('purpose', '=', 'checkout'),
            ('state', '=', 'pending'),
            ('partner_id', '=', order.partner_id.id),
        ], order='create_date desc', limit=1)
        try:
            if not otp:
                raise ValidationError(_('No pending verification code was found for this order.'))
            otp.verify_code(otp_code or '')
            return request.redirect('/shop/payment?otp_verified=1')
        except Exception as exc:
            return request.redirect('/shop/payment?otp_error=%s' % http.url_quote(str(exc)))


class SaranOtpWebsiteSale(WebsiteSale):

    @http.route()
    def shop_payment(self, **post):
        order = request.website.sale_get_order()
        if not order:
            return super().shop_payment(**post)
        icp = request.env['ir.config_parameter'].sudo()
        enabled = icp.get_param('saran_otp_auth.enabled', default='False') == 'True'
        checkout_enabled = icp.get_param('saran_otp_auth.checkout_enabled', default='False') == 'True'
        if enabled and checkout_enabled and not order.partner_id.otp_mobile_verified:
            values = {
                'order': order,
                'mobile': order.partner_id.mobile or '',
                'otp_sent': request.httprequest.args.get('otp_sent'),
                'otp_verified': request.httprequest.args.get('otp_verified'),
                'otp_error': request.httprequest.args.get('otp_error'),
            }
            return request.render('saran_otp_auth.shop_checkout_otp_template', values)
        return super().shop_payment(**post)
