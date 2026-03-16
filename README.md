# Saran OTP Auth for Odoo 19

GitHub-ready Odoo 19 module for OTP-based backend login, website signup, and checkout verification using Victory Link SMS.

## Features
- OTP login page linked from `/web/login`
- OTP signup page linked from website signup
- Optional OTP enforcement before `/shop/payment`
- Victory Link gateway settings in General Settings
- OTP audit log model and cleanup cron

## Module details
- Technical name: `saran_otp_auth`
- Display name: `Saran OTP Auth`
- Target version: `19.0.1.0.0`
- License: `LGPL-3`

## GitHub structure
The repository root should be the module root, so this file sits beside `__manifest__.py`.

## Server update workflow
1. Pull the latest code into your custom addons path.
2. Ensure `/opt/odoo/custom_addons` is present in `addons_path`.
3. Update the base module list.
4. Install or upgrade `saran_otp_auth`.

Example commands:

```bash
cd /opt/odoo/custom_addons/saran_otp_auth
git pull origin main
sudo -u odoo /usr/bin/odoo -c /etc/odoo/odoo.conf -d riashy -u base --stop-after-init
sudo -u odoo /usr/bin/odoo -c /etc/odoo/odoo.conf -d riashy -u saran_otp_auth --stop-after-init
sudo systemctl restart odoo
```

## Initial install
```bash
cd /opt/odoo/custom_addons
git clone https://github.com/YOUR_ORG/saran_otp_auth.git
sudo chown -R odoo:odoo /opt/odoo/custom_addons/saran_otp_auth
sudo -u odoo /usr/bin/odoo -c /etc/odoo/odoo.conf -d riashy -u base --stop-after-init
sudo -u odoo /usr/bin/odoo -c /etc/odoo/odoo.conf -d riashy -i saran_otp_auth --stop-after-init
sudo systemctl restart odoo
```
