# -*- coding: utf-8 -*-
"""Registration services: SMS OTP, email verification, Google Places validation."""
import os
import secrets
import string
import random
import requests
from datetime import datetime, timedelta
from flask import current_app

# ============================================================
# SMS - smsoffice.ge
# ============================================================

SMS_URL = "http://smsoffice.ge/api/v2/send"


def send_sms_code(phone):
    """Generate 6-digit OTP and send via smsoffice.ge.
    Returns (code, error_message). error_message is None on success.
    """
    code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    message = "Tably: " + code + " - verifikaciis kodi. moqmedebs 2 wuti."

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


def _build_email_html(title, body, btn_text, btn_url, footer):
    return (
        '<div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px;">'
        '<h2 style="color:#FF6B35;">Tably</h2>'
        '<h3>' + title + '</h3>'
        '<p>' + body + '</p>'
        '<a href="' + btn_url + '" style="display:inline-block;padding:12px 24px;'
        'background:#FF6B35;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">'
        + btn_text + '</a>'
        '<p style="color:#888;font-size:12px;margin-top:24px;">' + footer + '</p>'
        '</div>'
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


def _send_email_smtp(to, subject, html, fallback_label, fallback_url):
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


def send_verification_email(email, token, venue_name, base_url=None):
    """Send email verification link. Returns True on success."""
    if not base_url:
        base_url = os.environ.get('BASE_URL', 'http://localhost:5001')
    url = base_url + "/verify-email/" + token
    return _send_email_smtp(
        to=email,
        subject="Tably - el. fostis dadastureba",
        html=_build_email_html(
            title="el. fostis dadastureba",
            body="gamarjoba! <strong>" + venue_name + "</strong>-is registracia titqmis dasrulda.<br>daadastureT el. fosta:",
            btn_text="el. fostis dadastureba",
            btn_url=url,
            footer="linki moqmedebs 24 saaTi.",
        ),
        fallback_label="Verification link",
        fallback_url=url,
    )


def send_password_reset_email(email, token, base_url=None):
    """Send password reset link. Returns True on success."""
    if not base_url:
        base_url = os.environ.get('BASE_URL', 'http://localhost:5001')
    url = base_url + "/reset-password/" + token
    return _send_email_smtp(
        to=email,
        subject="Tably - parolis agdgena",
        html=_build_email_html(
            title="parolis agdgena",
            body="moTxovnilia parolis agdgena Tqveni Tably angarishisTvis.",
            btn_text="parolis Secvla",
            btn_url=url,
            footer="linki moqmedebs 1 saaTi. Tu es moTxovna ar gagigzavniaT, ugulebelyaviT.",
        ),
        fallback_label="Password reset link",
        fallback_url=url,
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
