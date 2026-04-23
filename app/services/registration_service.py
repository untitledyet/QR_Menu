# -*- coding: utf-8 -*-
"""Registration services: SMS OTP, email verification, Google Places validation."""
import os
import secrets
import string
import requests
from datetime import datetime, timedelta
from flask import current_app

# ============================================================
# SMS - smsoffice.ge
# ============================================================

SMS_URL = "http://smsoffice.ge/api/v2/send"


def _sms_text(code, lang='ka', purpose='otp'):
    """Return professional SMS text in the user's language."""
    if lang == 'en':
        if purpose == 'reset':
            return f"Tably: Your password reset code is {code}. Valid for 5 minutes."
        return f"Tably: Your verification code is {code}. Valid for 2 minutes."
    # Georgian (default)
    if purpose == 'reset':
        return f"Tably: პაროლის აღდგენის კოდი: {code}. მოქმედებს 5 წუთი."
    return f"Tably: დამადასტურებელი კოდი: {code}. მოქმედებს 2 წუთი."


def _generate_otp_code(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def send_sms_code(phone, lang='ka', purpose='otp'):
    """Generate 6-digit OTP and send via smsoffice.ge.
    Returns (code, error_message). error_message is None on success.
    """
    code = _generate_otp_code()
    message = _sms_text(code, lang=lang, purpose=purpose)

    api_key = os.environ.get('SMS_API_KEY', '')
    sender = os.environ.get('SMS_SENDER', 'Tably')

    if not api_key:
        current_app.logger.warning("SMS_API_KEY not set, OTP: " + code)
        return code, None

    try:
        resp = requests.get(SMS_URL, params={
            "key": api_key,
            "destination": phone,
            "sender": sender,
            "content": message,
        }, timeout=10)
        data = resp.json()
        if data.get("Success"):
            return code, None
        return code, data.get("Message", "SMS send failed")
    except Exception as e:
        current_app.logger.error("SMS error: " + str(e))
        return code, str(e)


# ============================================================
# Email verification
# ============================================================

def generate_email_token():
    return secrets.token_urlsafe(32)


def _build_email_html(title, body_html, btn_text=None, btn_url=None, footer='', code=None):
    """Professional Tably email template. Supports link button or OTP code display."""
    btn_block = ''
    if btn_url and btn_text:
        btn_block = (
            '<a href="' + btn_url + '" style="display:inline-block;margin:24px 0 8px;'
            'padding:14px 32px;background:#FF6B35;color:#ffffff;border-radius:8px;'
            'text-decoration:none;font-weight:600;font-size:15px;letter-spacing:.01em;">'
            + btn_text + '</a>'
        )
    if code:
        btn_block = (
            '<div style="margin:28px 0 8px;text-align:center;">'
            '<span style="display:inline-block;padding:16px 40px;background:#f5f5f5;'
            'border-radius:10px;font-size:32px;font-weight:700;letter-spacing:.25em;'
            'color:#111827;font-family:monospace;">' + code + '</span></div>'
        )
    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Georgian:wght@400;600&'
        'family=Inter:wght@400;600&display=swap" rel="stylesheet"></head>'
        '<body style="margin:0;padding:0;background:#f9f9f9;">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f9f9f9;padding:40px 16px;">'
        '<tr><td align="center">'
        '<table width="100%" style="max-width:500px;background:#ffffff;border-radius:12px;'
        'box-shadow:0 2px 12px rgba(0,0,0,.06);overflow:hidden;" cellpadding="0" cellspacing="0">'
        '<tr><td style="background:#FF6B35;padding:20px 32px;">'
        '<span style="font-family:Inter,sans-serif;font-size:22px;font-weight:700;color:#fff;'
        'letter-spacing:-.02em;">tab<span style="opacity:.75;">ly</span></span></td></tr>'
        '<tr><td style="padding:32px 32px 28px;font-family:\'Noto Sans Georgian\',Inter,Arial,sans-serif;'
        'color:#111827;font-size:15px;line-height:1.6;">'
        '<h2 style="margin:0 0 16px;font-size:20px;font-weight:600;color:#111827;">' + title + '</h2>'
        '<div style="color:#374151;">' + body_html + '</div>'
        + btn_block +
        '</td></tr>'
        '<tr><td style="padding:16px 32px 24px;border-top:1px solid #f0f0f0;'
        'font-family:\'Noto Sans Georgian\',Inter,Arial,sans-serif;font-size:12px;color:#9ca3af;">'
        + footer + '</td></tr>'
        '</table></td></tr></table>'
        '</body></html>'
    )


def _send_via_resend(to, subject, html, api_key, app):
    """Send email via Resend HTTP API. Returns True on success."""
    try:
        resp = requests.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': 'Bearer ' + api_key,
                'Content-Type': 'application/json',
            },
            json={
                'from': 'Tably <info@tably.ge>',
                'to': [to],
                'subject': subject,
                'html': html,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            with app.app_context():
                app.logger.info('[EMAIL OK] Resend sent to ' + to + ': ' + subject)
            return True
        with app.app_context():
            app.logger.error('[EMAIL ERROR] Resend ' + str(resp.status_code) + ': ' + resp.text)
        return False
    except Exception as e:
        with app.app_context():
            app.logger.error('[EMAIL ERROR] Resend exception: ' + str(e))
        return False


def _do_send_smtp(to, subject, html, fallback_label, fallback_url, app):
    """Actual SMTP send — runs in a background thread to avoid blocking gunicorn."""
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.environ.get('SMTP_HOST', '')
    smtp_port = int(os.environ.get('SMTP_PORT', '465'))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    from_email = os.environ.get('SMTP_FROM', smtp_user)

    if not smtp_host or not smtp_user:
        with app.app_context():
            app.logger.info("[EMAIL DEV] " + fallback_label + " for " + to + ": " + fallback_url)
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = "Tably <" + from_email + ">"
    msg['To'] = to
    msg.attach(MIMEText(html, 'html'))

    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()

    # Try primary port, then fallback to the other port
    ports_to_try = [(smtp_port, smtp_port == 465)]
    fallback_port = 587 if smtp_port == 465 else 465
    ports_to_try.append((fallback_port, fallback_port == 465))

    last_err = None
    for port, use_ssl in ports_to_try:
        try:
            if use_ssl:
                with smtplib.SMTP_SSL(smtp_host, port, context=ctx, timeout=25) as server:
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(from_email, to, msg.as_string())
            else:
                with smtplib.SMTP(smtp_host, port, timeout=25) as server:
                    server.ehlo()
                    server.starttls(context=ctx)
                    server.ehlo()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(from_email, to, msg.as_string())
            with app.app_context():
                app.logger.info("[EMAIL OK] Sent to " + to + " via port " + str(port) + ": " + subject)
            return
        except Exception as e:
            last_err = e
            with app.app_context():
                app.logger.warning("[EMAIL] Port " + str(port) + " failed: " + str(e))

    with app.app_context():
        app.logger.error("[EMAIL ERROR] All ports failed. Last: " + str(last_err))
        app.logger.info("[EMAIL FALLBACK] " + fallback_label + ": " + fallback_url)


def _send_email_smtp(to, subject, html, fallback_label='', fallback_url=None):
    """Fire-and-forget email send in a background thread. Returns True immediately.
    Uses Resend API if RESEND_API_KEY is set, otherwise falls back to SMTP."""
    import threading
    app = current_app._get_current_object()
    resend_key = os.environ.get('RESEND_API_KEY', '')

    if resend_key:
        t = threading.Thread(
            target=_send_via_resend,
            args=(to, subject, html, resend_key, app),
            daemon=True,
        )
    else:
        t = threading.Thread(
            target=_do_send_smtp,
            args=(to, subject, html, fallback_label, fallback_url, app),
            daemon=True,
        )
    t.start()
    return True


def send_verification_email(email, token, venue_name, base_url=None, lang='ka'):
    """Send email verification link. Returns True on success."""
    if not base_url:
        base_url = os.environ.get('BASE_URL', 'http://localhost:5001')
    url = base_url + "/verify-email/" + token
    if lang == 'en':
        subject = "Tably — Verify your email"
        title = "Email Verification"
        body = (f"Hello! Registration for <strong>{venue_name}</strong> is almost complete.<br>"
                "Please verify your email address to activate your account.")
        btn_text = "Verify Email"
        footer = "This link expires in 24 hours. If you didn't register, please ignore this email."
    else:
        subject = "Tably — ელ. ფოსტის დადასტურება"
        title = "ელ. ფოსტის დადასტურება"
        body = (f"გამარჯობა! <strong>{venue_name}</strong>-ის რეგისტრაცია თითქმის დასრულდა.<br>"
                "გთხოვთ, დაადასტუროთ ელ. ფოსტა ანგარიშის გასააქტიურებლად.")
        btn_text = "ელ. ფოსტის დადასტურება"
        footer = "ბმული მოქმედებს 24 საათი. თუ ეს მოთხოვნა არ გაგიგზავნიათ, უგულებელყავით."
    return _send_email_smtp(
        to=email, subject=subject,
        html=_build_email_html(title=title, body_html=body, btn_text=btn_text, btn_url=url, footer=footer),
        fallback_label="Verification link", fallback_url=url,
    )


def send_password_reset_email(email, token, base_url=None, lang='ka'):
    """Send password reset link. Returns True on success."""
    if not base_url:
        base_url = os.environ.get('BASE_URL', 'http://localhost:5001')
    url = base_url + "/reset-password/" + token
    if lang == 'en':
        subject = "Tably — Password Reset"
        title = "Password Reset"
        body = "A password reset was requested for your Tably account. Click the button below to set a new password."
        btn_text = "Reset Password"
        footer = "This link expires in 1 hour. If you did not request a reset, please ignore this email."
    else:
        subject = "Tably — პაროლის აღდგენა"
        title = "პაროლის აღდგენა"
        body = "მოთხოვნილია პაროლის აღდგენა თქვენი Tably ანგარიშისთვის. დააჭირეთ ღილაკს ახალი პაროლის დასაყენებლად."
        btn_text = "პაროლის შეცვლა"
        footer = "ბმული მოქმედებს 1 საათი. თუ ეს მოთხოვნა არ გაგიგზავნიათ, უგულებელყავით."
    return _send_email_smtp(
        to=email, subject=subject,
        html=_build_email_html(title=title, body_html=body, btn_text=btn_text, btn_url=url, footer=footer),
        fallback_label="Password reset link", fallback_url=url,
    )


def send_2fa_email(email, code, lang='ka'):
    """Send 2FA OTP code to email. Returns True on success."""
    if lang == 'en':
        subject = "Tably — Login Verification Code"
        title = "Login Verification"
        body = "Use the code below to complete your sign-in. It expires in 2 minutes."
        footer = "If you did not attempt to sign in, please secure your account immediately."
    else:
        subject = "Tably — შესვლის დამადასტურებელი კოდი"
        title = "შესვლის დადასტურება"
        body = "გამოიყენეთ ქვემოთ მოცემული კოდი შესვლის დასასრულებლად. მოქმედებს 2 წუთი."
        footer = "თუ შესვლა არ გაქვთ სცადებული, დაუყოვნებლივ უზრუნველყავით ანგარიშის დაცვა."
    return _send_email_smtp(
        to=email, subject=subject,
        html=_build_email_html(title=title, body_html=body, code=code, footer=footer),
        fallback_label="2FA code", fallback_url=None,
    )


def search_google_place(venue_name, address):
    """Search Google Places API for matching venues."""
    api_key = os.environ.get('GOOGLE_PLACES_API_KEY', '')
    if not api_key:
        return []

    if venue_name and address:
        query = venue_name + " " + address
    elif venue_name:
        query = venue_name
    else:
        query = address

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.id",
    }
    data = {
        "textQuery": query,
        "locationBias": {
            "circle": {
                "center": {"latitude": 41.7151, "longitude": 44.8271},
                "radius": 50000
            }
        }
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.status_code != 200:
            return []
        places = resp.json().get("places", [])
        results = []
        for p in places[:5]:
            results.append({
                "name": p["displayName"]["text"],
                "address": p.get("formattedAddress", ""),
                "place_id": p["id"],
                "maps_url": "https://www.google.com/maps/place/?q=place_id:" + p["id"],
            })
        return results
    except Exception as e:
        current_app.logger.error("Places API error: " + str(e))
        return []


# ============================================================
# Password validation
# ============================================================

def validate_password(password: str):
    """Return Georgian error message string, or None if password is valid.
    Rules: >= 8 chars, at least one uppercase, one lowercase, one digit.
    """
    if len(password) < 8:
        return 'paroli minimum 8 simbolo unda iyos'
    if not any(c.isupper() for c in password):
        return 'paroli unda Seicavdes minimum erT didi aso'
    if not any(c.islower() for c in password):
        return 'paroli unda Seicavdes minimum erT pataras aso'
    if not any(c.isdigit() for c in password):
        return 'paroli unda Seicavdes minimum erT cifrs'
    return None


# ============================================================
# Password generation
# ============================================================

def generate_strong_password(length=16):
    """Generate a strong random password."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        if (any(c.isupper() for c in pwd) and
                any(c.islower() for c in pwd) and
                any(c.isdigit() for c in pwd) and
                any(c in "!@#$%^&*" for c in pwd)):
            return pwd
