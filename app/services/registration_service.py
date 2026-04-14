"""Registration services: SMS OTP, email verification, Google Places validation."""
import os
import secrets
import string
import random
import requests
from datetime import datetime, timedelta
from flask import current_app

# ============================================================
# SMS — smsoffice.ge
# ============================================================

SMS_API_KEY = "2621e8700a9e4e699a9cf888088ca358"
SMS_URL = "http://smsoffice.ge/api/v2/send"
SMS_SENDER = "Auto Finder"


def send_sms_code(phone: str) -> tuple[str, str | None]:
    """Generate 6-digit OTP and send via smsoffice.ge.
    Returns (code, error_message). error_message is None on success.
    """
    code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    message = f"Tably: {code} - ვერიფიკაციის კოდი. მოქმედებს 1 წუთი."

    try:
        resp = requests.get(SMS_URL, params={
            "key": SMS_API_KEY,
            "destination": phone,
            "sender": SMS_SENDER,
            "content": message,
        }, timeout=10)
        data = resp.json()
        if data.get("Success"):
            return code, None
        return code, data.get("Message", "SMS send failed")
    except Exception as e:
        current_app.logger.error(f"SMS error: {e}")
        return code, str(e)


# ============================================================
# Email verification
# ============================================================

def generate_email_token() -> str:
    return secrets.token_urlsafe(32)


def _build_email_html(title: str, body: str, btn_text: str, btn_url: str, footer: str) -> str:
    return f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px;">
        <h2 style="color:#FF6B35;">Tably</h2>
        <h3>{title}</h3>
        <p>{body}</p>
        <a href="{btn_url}" style="display:inline-block;padding:12px 24px;background:#FF6B35;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">
            {btn_text}
        </a>
        <p style="color:#888;font-size:12px;margin-top:24px;">{footer}</p>
    </div>
    """


def _send_email_smtp(to: str, subject: str, html: str, fallback_label: str, fallback_url: str) -> bool:
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = os.environ.get('SMTP_HOST', '')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_pass = os.environ.get('SMTP_PASS', '')
        from_email = os.environ.get('SMTP_FROM', smtp_user)

        if not smtp_host or not smtp_user:
            print(f"\n[EMAIL DEV] {fallback_label} for {to}:\n  {fallback_url}\n")
            return True

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"Tably <{from_email}>"
        msg['To'] = to
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, to, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        print(f"[EMAIL FALLBACK] {fallback_label}: {fallback_url}")
        return False


def send_verification_email(email: str, token: str, venue_name: str) -> bool:
    """Send email verification link. Returns True on success."""
    base_url = os.environ.get('BASE_URL', 'http://localhost:5001')
    url = f"{base_url}/verify-email/{token}"
    return _send_email_smtp(
        to=email,
        subject="Tably — ელ. ფოსტის დადასტურება",
        html=_build_email_html(
            title="ელ. ფოსტის დადასტურება",
            body=f"გამარჯობა! <strong>{venue_name}</strong>-ის რეგისტრაცია თითქმის დასრულდა.<br>დაადასტურეთ ელ. ფოსტა:",
            btn_text="ელ. ფოსტის დადასტურება",
            btn_url=url,
            footer="ლინკი მოქმედებს 24 საათი.",
        ),
        fallback_label="Verification link",
        fallback_url=url,
    )


def send_password_reset_email(email: str, token: str) -> bool:
    """Send password reset link. Returns True on success."""
    base_url = os.environ.get('BASE_URL', 'http://localhost:5001')
    url = f"{base_url}/reset-password/{token}"
    return _send_email_smtp(
        to=email,
        subject="Tably — პაროლის აღდგენა",
        html=_build_email_html(
            title="პაროლის აღდგენა",
            body="მოთხოვნილია პაროლის აღდგენა თქვენი Tably ანგარიშისთვის.",
            btn_text="პაროლის შეცვლა",
            btn_url=url,
            footer="ლინკი მოქმედებს 1 საათი. თუ ეს მოთხოვნა არ გაგიგზავნიათ, უგულებელყავით.",
        ),
        fallback_label="Password reset link",
        fallback_url=url,
    )

GOOGLE_API_KEY = "AIzaSyA8_OFiiawkzqSWX68IdVC_790yZ1MaZcg"


def search_google_place(venue_name: str, address: str) -> list[dict]:
    """Search Google Places API for matching venues.
    Returns list of {name, address, place_id, maps_url}.
    """
    # Combine name + address for best results
    if venue_name and address:
        query = f"{venue_name} {address}"
    elif venue_name:
        query = venue_name
    else:
        query = address
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
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
        return [{
            "name": p["displayName"]["text"],
            "address": p.get("formattedAddress", ""),
            "place_id": p["id"],
            "maps_url": f"https://www.google.com/maps/place/?q=place_id:{p['id']}",
        } for p in places[:5]]
    except Exception as e:
        current_app.logger.error(f"Places API error: {e}")
        return []


# ============================================================
# Password generation
# ============================================================

def generate_strong_password(length: int = 16) -> str:
    """Generate a strong random password."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        if (any(c.isupper() for c in pwd) and
                any(c.islower() for c in pwd) and
                any(c.isdigit() for c in pwd) and
                any(c in "!@#$%^&*" for c in pwd)):
            return pwd
