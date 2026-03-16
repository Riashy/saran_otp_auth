# Saran OTP OTH

Odoo module for OTP-based authentication with Victory Link SMS API.

## Features
- OTP login from a dedicated page linked from `/web/login`
- OTP signup for website users
- OTP verification before website payment
- Victory Link gateway settings in General Settings
- Internal OTP audit log
- Scheduled cleanup of expired OTP codes

## Supported Odoo versions
Designed for Odoo 17, 18, and 19 with conservative patterns:
- controller extension with `@route()` re-decoration
- QWeb inheritance via XPath
- configuration through `res.config.settings`
- no custom frontend asset bundle
