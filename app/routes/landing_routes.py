# -*- coding: utf-8 -*-
"""Landing page and venue self-registration routes."""
import re
import secrets
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, jsonify, current_app)


def _request_base_url():
    """Return scheme+host from the current request (e.g. http://localhost:5001 or https://tably.ge).
    Falls back to BASE_URL env var when called outside a request context."""
    import os
    try:
        return request.scheme + '://' + request.host
    except RuntimeError:
        return os.environ.get('BASE_URL', 'http://localhost:5001')
from app import db
from app.models import AdminUser, Venue, _generate_venue_code, PhoneOtp, _hash_token
from app.services.registration_service import (
    send_sms_code, generate_email_token, send_verification_email,
    send_password_reset_email, search_google_place, generate_strong_password,
    validate_password,
)

landing_bp = Blueprint('landing_bp', __name__)

MAX_OTP_ATTEMPTS = 5
MAX_IP_OTP_PER_HOUR = 10
EMAIL_TOKEN_EXPIRY_HOURS = 24


# ============================================================
# Helpers
# ============================================================

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or 'venue'


def _normalize_phone(phone: str):
    """Return '995XXXXXXXXX' (12 digits) or None if format unrecognizable."""
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('995') and len(digits) == 12:
        return digits
    if not digits.startswith('995') and len(digits) == 9:
        return '995' + digits
    return None


def _get_client_ip():
    """Get real client IP, handling Railway/nginx reverse-proxy headers."""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def _find_admin_by_identifier(identifier: str):
    """Find admin by phone (9-digit or full 995-prefix) or by email."""
    identifier = identifier.strip()
    normalized = _normalize_phone(identifier)
    if normalized:
        return AdminUser.query.filter_by(phone=normalized).first()
    return AdminUser.query.filter_by(email=identifier.lower()).first()


# ============================================================
# Landing page
# ============================================================

@landing_bp.route('/')
def landing():
    venues = Venue.query.filter_by(is_active=True).all()
    return render_template('landing.html', venues=venues)


# ============================================================
# Google Places search
# ============================================================

@landing_bp.route('/api/places/search')
def places_search():
    name = request.args.get('name', '').strip()
    address = request.args.get('address', '').strip()
    if not name and not address:
        return jsonify(places=[])
    results = search_google_place(name, address)
    return jsonify(places=results)


# ============================================================
# Password suggestion
# ============================================================

@landing_bp.route('/api/suggest-password')
def suggest_password():
    return jsonify(password=generate_strong_password())


# ============================================================
# Phone OTP — pre-registration phone verification
# ============================================================

@landing_bp.route('/api/send-phone-otp', methods=['POST'])
def send_phone_otp():
    # Global maintenance: remove all expired entries on each request
    PhoneOtp.query.filter(PhoneOtp.expires < datetime.utcnow()).delete()
    db.session.commit()

    data = request.get_json() or {}
    raw_phone = data.get('phone', '').strip()
    phone = _normalize_phone(raw_phone)
    if not phone:
        return jsonify(error='telefonis nomeri arasworia'), 400

    client_ip = _get_client_ip()

    # IP-based rate limit: max 10 OTPs from one IP per hour
    ip_count = PhoneOtp.query.filter_by(ip=client_ip).filter(
        PhoneOtp.created_at > datetime.utcnow() - timedelta(hours=1)
    ).count()
    if ip_count >= MAX_IP_OTP_PER_HOUR:
        return jsonify(error='Zalian bevri moTxovna. scadeT mogvianebiT'), 429

    # Per-phone rate limit: no resend if > 60 seconds remaining on existing OTP
    existing = PhoneOtp.query.filter_by(phone=phone).filter(
        PhoneOtp.expires > datetime.utcnow()
    ).first()
    if existing:
        remaining = int((existing.expires - datetime.utcnow()).total_seconds())
        if remaining > 60:
            return jsonify(error='gTxovT daelodoT ' + str(remaining - 60) + ' wami'), 429
        db.session.delete(existing)
        db.session.commit()

    # Send SMS FIRST — only persist OTP if send succeeded
    code, sms_error = send_sms_code(phone)

    if sms_error:
        # In dev (no SMS_API_KEY), send_sms_code returns error=None, so reaching here
        # means we are in production and the SMS service is genuinely down.
        current_app.logger.error('SMS OTP failed for ' + phone + ': ' + str(sms_error))
        return jsonify(error='SMS gagzavna ver moxerxda. scadeT xelaxla'), 503

    from werkzeug.security import generate_password_hash
    otp = PhoneOtp(
        phone=phone,
        code_hash=generate_password_hash(code),
        expires=datetime.utcnow() + timedelta(minutes=2),
        attempts=0,
        ip=client_ip,
    )
    db.session.add(otp)
    db.session.commit()

    return jsonify(success=True, message='kodi gaigzavna')


@landing_bp.route('/api/verify-phone-otp', methods=['POST'])
def verify_phone_otp_api():
    data = request.get_json() or {}
    raw_phone = data.get('phone', '').strip()
    code = data.get('code', '').strip()

    phone = _normalize_phone(raw_phone)
    if not phone:
        return jsonify(error='telefonis nomeri arasworia'), 400

    entry = PhoneOtp.query.filter_by(phone=phone).filter(
        PhoneOtp.expires > datetime.utcnow()
    ).first()

    if not entry:
        return jsonify(error='kodi ver moiZebna. xelaxla gagzavneT'), 400

    if entry.attempts >= MAX_OTP_ATTEMPTS:
        db.session.delete(entry)
        db.session.commit()
        return jsonify(error='Zalian bevri mcdeloba. xelaxla gagzavneT kodi'), 400

    entry.attempts += 1
    db.session.commit()

    from werkzeug.security import check_password_hash
    if not check_password_hash(entry.code_hash, code):
        remaining = MAX_OTP_ATTEMPTS - entry.attempts
        return jsonify(error='kodi arasworia. darCa ' + str(remaining) + ' mcdeloba'), 400

    # Success — clean up and store NORMALIZED phone in session
    db.session.delete(entry)
    db.session.commit()
    session['verified_phone'] = phone  # always '995XXXXXXXXX'
    return jsonify(success=True)


# ============================================================
# Register — phone already verified, account active immediately
# ============================================================

@landing_bp.route('/register', methods=['POST'])
def register_venue():
    data = request.get_json() or {}
    venue_name = data.get('venue_name', '').strip()
    address = data.get('address', '').strip()
    place_id = data.get('place_id', '').strip()
    email = data.get('email', '').strip().lower()
    raw_phone = data.get('phone', '').strip()
    password = data.get('password', '')

    if not venue_name or not address or not email or not raw_phone or not password:
        return jsonify(error='yvela veli savaldebuloa'), 400

    # ── TESTUSER BACKDOOR ────────────────────────────────────────────────────
    # If venue name ends with '-testuser' (case-insensitive) all verification
    # is skipped and the account is created fully active.  For testing only.
    is_test_user = venue_name.lower().endswith('-testuser')
    # ─────────────────────────────────────────────────────────────────────────

    if not is_test_user and not place_id:
        return jsonify(error='gTxovT, obieqti Google Maps-ze daadastureT'), 400

    full_phone = _normalize_phone(raw_phone)
    if not full_phone:
        return jsonify(error='telefonis nomeri arasworia'), 400

    if not is_test_user:
        # Phone must match the one verified in this session
        verified_phone = session.get('verified_phone', '')
        if verified_phone != full_phone:
            return jsonify(error='telefoni ar aris verificirebuli'), 400

    pw_error = validate_password(password)
    if pw_error:
        return jsonify(error=pw_error), 400

    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify(error='el. fosta arasworia'), 400

    # Duplicate check — same generic message to prevent enumeration
    if AdminUser.query.filter_by(email=email).first():
        return jsonify(error='es monacemebi ukve registrirebulia'), 400
    if AdminUser.query.filter_by(phone=full_phone).first():
        return jsonify(error='es monacemebi ukve registrirebulia'), 400

    # Generate unique slug
    base_slug = slugify(venue_name)
    slug = base_slug
    counter = 2
    while Venue.query.filter_by(slug=slug).first():
        slug = base_slug + '-' + str(counter)
        counter += 1

    # Generate unique venue_code
    while True:
        vcode = _generate_venue_code()
        if not Venue.query.filter_by(venue_code=vcode).first():
            break

    # Use a placeholder place_id for test users
    effective_place_id = place_id or ('testuser-place-' + slug if is_test_user else '')

    # Create venue
    venue = Venue(name=venue_name, slug=slug, plan='free',
                  address=address, google_place_id=effective_place_id, venue_code=vcode)
    db.session.add(venue)
    db.session.flush()

    # Generate email token — store HASH in DB, send RAW token via email
    # Test users get email pre-verified; skip token entirely
    if is_test_user:
        admin = AdminUser(
            username=slug,
            email=email,
            phone=full_phone,
            role='venue',
            venue_id=venue.id,
            email_verified=True,
            phone_verified=True,
            is_active=True,
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        session.pop('verified_phone', None)
        session['admin_id'] = admin.id
        current_app.logger.info('TESTUSER registration bypassed verification for: ' + venue_name)
        return jsonify(success=True, redirect='/backoffice')

    raw_email_token = generate_email_token()
    admin = AdminUser(
        username=slug,
        email=email,
        phone=full_phone,
        role='venue',
        venue_id=venue.id,
        email_verified=False,
        phone_verified=True,
        is_active=True,
        email_token=_hash_token(raw_email_token),
        email_token_expires=datetime.utcnow() + timedelta(hours=EMAIL_TOKEN_EXPIRY_HOURS),
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    # Send verification email (non-critical)
    try:
        send_verification_email(email, raw_email_token, venue_name, base_url=_request_base_url())
    except Exception as e:
        current_app.logger.warning('Email send failed (non-critical): ' + str(e))

    # Clear session phone, log in
    session.pop('verified_phone', None)
    session['admin_id'] = admin.id
    return jsonify(success=True, redirect='/backoffice')


# ============================================================
# Email verification
# ============================================================

@landing_bp.route('/verify-email/<token>')
def verify_email(token):
    token_hash = _hash_token(token)
    admin = AdminUser.query.filter_by(email_token=token_hash).first()

    if not admin:
        return render_template('verify_result.html', success=False,
                               message='linki arasworia an vadagasulia.')

    if admin.email_token_expires and datetime.utcnow() > admin.email_token_expires:
        admin.email_token = None
        admin.email_token_expires = None
        db.session.commit()
        return render_template('verify_result.html', success=False,
                               message='verifikaciis links vada gauva. moiTxoveT axali linki.')

    admin.email_verified = True
    admin.email_token = None
    admin.email_token_expires = None
    db.session.commit()

    session['admin_id'] = admin.id
    return redirect('/backoffice')


@landing_bp.route('/resend-email-verification', methods=['POST'])
def resend_email_verification():
    from flask import session as flask_session
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify(error='el. fosta savaldebuloa'), 400

    # If the caller is the logged-in admin themselves, give precise feedback
    logged_in_admin_id = flask_session.get('admin_id')
    is_self = False
    if logged_in_admin_id:
        self_admin = AdminUser.query.get(logged_in_admin_id)
        if self_admin and self_admin.email.lower() == email:
            is_self = True

    admin = AdminUser.query.filter_by(email=email, email_verified=False).first()

    if not admin:
        if is_self:
            # Should not normally happen — means email is already verified
            return jsonify(success=True,
                           message='ელ. ფოსტა უკვე დადასტურებულია.')
        # Enumeration protection for anonymous callers
        return jsonify(success=True,
                       message='Tu es el. fosta registrirebulia, gaigzavneba verifikaciis linki.')

    # Rate limit: refuse if a token was issued less than 5 minutes ago
    if (admin.email_token_expires is not None and
            admin.email_token_expires > datetime.utcnow() +
            timedelta(hours=EMAIL_TOKEN_EXPIRY_HOURS - 1, minutes=55)):
        if is_self:
            return jsonify(success=True,
                           message='ვერიფიკაციის ლინკი უკვე გაიგზავნა. შეამოწმეთ inbox ან spam ' + email + '-ზე.')
        return jsonify(success=True,
                       message='Tu es el. fosta registrirebulia, gaigzavneba verifikaciis linki.')

    raw_token = generate_email_token()
    admin.email_token = _hash_token(raw_token)
    admin.email_token_expires = datetime.utcnow() + timedelta(hours=EMAIL_TOKEN_EXPIRY_HOURS)
    db.session.commit()
    venue_name = admin.venue.name if admin.venue else 'Tably'
    try:
        send_verification_email(email, raw_token, venue_name, base_url=_request_base_url())
    except Exception as e:
        current_app.logger.warning('Resend email failed: ' + str(e))
        if is_self:
            return jsonify(error='მეილის გაგზავნა ვერ მოხერხდა. სცადეთ მოგვიანებით.'), 500

    if is_self:
        return jsonify(success=True,
                       message='ვერიფიკაციის ლინკი გაიგზავნა ' + email + '-ზე. შეამოწმეთ inbox ან spam.')
    # Enumeration protection for anonymous callers
    return jsonify(success=True,
                   message='Tu es el. fosta registrirebulia, gaigzavneba verifikaciis linki.')


# ============================================================
# Login — phone/email + password → SMS 2FA
# ============================================================

@landing_bp.route('/login-venue', methods=['POST'])
def login_venue():
    data = request.get_json() or {}
    step = data.get('step', 'credentials')

    if step == 'credentials':
        identifier = data.get('identifier', '').strip()
        password = data.get('password', '')

        if not identifier or not password:
            return jsonify(error='SeavseT yvela veli'), 400

        admin = _find_admin_by_identifier(identifier)

        # 1. Lockout check BEFORE password (prevents timing attacks and lock bypass)
        if admin and admin.is_locked:
            return jsonify(error='angarishi droebiT daibloqa. scadeT 15 wuTSi'), 403

        # 2. Credential check
        if not admin or not admin.check_password(password):
            if admin:
                admin.record_failed_login()
                db.session.commit()
            return jsonify(error='monacemebi arasworia'), 401

        # 3. Active check (super admin always passes)
        if not admin.is_active and not admin.is_super:
            return jsonify(error='angarishi ar aris gaaqtiurebuli'), 403

        # 4. Successful credentials — reset brute-force counter
        admin.reset_failed_logins()

        # 5. SMS 2FA — hard fail if SMS is down (no bypass)
        code, sms_error = send_sms_code(admin.phone)
        if sms_error:
            current_app.logger.error('2FA SMS failed for id=' + str(admin.id) +
                                     ' phone=' + str(admin.phone) + ': ' + str(sms_error))
            db.session.commit()
            return jsonify(error='SMS gagzavna ver moxerxda. scadeT mogvianebiT'), 503

        admin.set_sms_code(code)
        admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=2)
        db.session.commit()

        session['login_admin_id'] = admin.id
        phone_display = '*' * (len(admin.phone) - 4) + admin.phone[-4:]
        return jsonify(success=True, step='sms_2fa',
                       message='SMS kodi gaigzavna ' + phone_display + '-ze')

    elif step == 'sms_2fa':
        code = data.get('code', '').strip()
        admin_id = session.get('login_admin_id')

        if not admin_id:
            return jsonify(error='sesia amoiwura'), 400

        admin = AdminUser.query.get(admin_id)
        if not admin:
            return jsonify(error='momxmarebeli ver moiZebna'), 400

        if not admin.sms_code_hash or not admin.sms_code_expires:
            return jsonify(error='kodi ver moiZebna'), 400

        if datetime.utcnow() > admin.sms_code_expires:
            admin.sms_code_hash = None
            admin.sms_code_expires = None
            db.session.commit()
            return jsonify(error='kodi vadagasulia. Tavidan Seusvit'), 400

        if admin.sms_attempts >= MAX_OTP_ATTEMPTS:
            admin.sms_code_hash = None
            admin.sms_code_expires = None
            db.session.commit()
            return jsonify(error='Zalian bevri mcdeloba. Tavidan scadeT'), 400

        admin.sms_attempts = (admin.sms_attempts or 0) + 1

        if not admin.check_sms_code(code):
            remaining = MAX_OTP_ATTEMPTS - admin.sms_attempts
            db.session.commit()
            return jsonify(error='kodi arasworia. darCa ' + str(remaining) + ' mcdeloba'), 400

        # Success
        admin.sms_code_hash = None
        admin.sms_code_expires = None
        admin.sms_attempts = 0
        db.session.commit()

        session.pop('login_admin_id', None)
        session['admin_id'] = admin.id
        return jsonify(success=True, redirect='/backoffice')

    return jsonify(error='Invalid step'), 400


# ============================================================
# Password reset — SMS OTP (primary), email link (fallback)
# ============================================================

@landing_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    identifier = data.get('identifier', '').strip()
    if not identifier:
        return jsonify(error='telefoni an el. fosta savaldebuloa'), 400

    # Determine identifier type to give appropriate UX hint WITHOUT revealing account existence
    is_phone_input = bool(_normalize_phone(identifier))

    admin = _find_admin_by_identifier(identifier)

    if admin and admin.is_active:
        if admin.phone:
            code, sms_error = send_sms_code(admin.phone)
            if not sms_error:
                admin.set_sms_code(code)
                admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=5)
                db.session.commit()
                session['reset_admin_id'] = admin.id
            elif admin.email:
                # SMS failed — silent email fallback
                try:
                    raw_token = secrets.token_urlsafe(32)
                    admin.reset_token = _hash_token(raw_token)
                    admin.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
                    db.session.commit()
                    send_password_reset_email(admin.email, raw_token, base_url=_request_base_url())
                except Exception as e:
                    current_app.logger.error('Email reset fallback failed: ' + str(e))
        elif admin.email:
            try:
                raw_token = secrets.token_urlsafe(32)
                admin.reset_token = _hash_token(raw_token)
                admin.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
                db.session.commit()
                send_password_reset_email(admin.email, raw_token, base_url=_request_base_url())
            except Exception as e:
                current_app.logger.error('Email reset failed: ' + str(e))

    # Always return same structure — no account existence reveal
    if is_phone_input:
        msg = 'Tu es nomeri registrirebulia, SMS kodi gaigzavna'
    else:
        msg = 'Tu es el. fosta registrirebulia, agdgenis linki gaigzavna'

    return jsonify(success=True, message=msg)


@landing_bp.route('/verify-reset-sms', methods=['POST'])
def verify_reset_sms():
    data = request.get_json() or {}
    code = data.get('code', '').strip()
    admin_id = session.get('reset_admin_id')

    if not admin_id or not code:
        return jsonify(error='sesia amoiwura'), 400

    admin = AdminUser.query.get(admin_id)
    if not admin or not admin.sms_code_hash or not admin.sms_code_expires:
        return jsonify(error='kodi ver moiZebna'), 400

    if datetime.utcnow() > admin.sms_code_expires:
        admin.sms_code_hash = None
        admin.sms_code_expires = None
        db.session.commit()
        return jsonify(error='kodi vadagasulia'), 400

    if admin.sms_attempts >= MAX_OTP_ATTEMPTS:
        admin.sms_code_hash = None
        admin.sms_code_expires = None
        db.session.commit()
        return jsonify(error='Zalian bevri mcdeloba'), 400

    admin.sms_attempts = (admin.sms_attempts or 0) + 1

    if not admin.check_sms_code(code):
        remaining = MAX_OTP_ATTEMPTS - admin.sms_attempts
        db.session.commit()
        return jsonify(error='kodi arasworia. darCa ' + str(remaining) + ' mcdeloba'), 400

    # Issue reset token — store HASH, redirect with RAW
    raw_token = secrets.token_urlsafe(32)
    admin.reset_token = _hash_token(raw_token)
    admin.reset_token_expires = datetime.utcnow() + timedelta(minutes=10)
    admin.sms_code_hash = None
    admin.sms_code_expires = None
    admin.sms_attempts = 0
    db.session.commit()

    session.pop('reset_admin_id', None)
    return jsonify(success=True, redirect='/reset-password/' + raw_token)


@landing_bp.route('/resend-reset-sms', methods=['POST'])
def resend_reset_sms():
    admin_id = session.get('reset_admin_id')
    if not admin_id:
        return jsonify(error='sesia amoiwura'), 400

    admin = AdminUser.query.get(admin_id)
    if not admin:
        return jsonify(error='momxmarebeli ver moiZebna'), 400

    # Rate limit: must wait if code is still > 2 min from expiry
    if admin.sms_code_expires and datetime.utcnow() < admin.sms_code_expires:
        remaining = int((admin.sms_code_expires - datetime.utcnow()).total_seconds())
        if remaining > 120:
            return jsonify(error='gTxovT daelodoT ' + str(remaining - 120) + ' wami'), 429

    code, error = send_sms_code(admin.phone)
    if error:
        return jsonify(error='SMS gagzavna ver moxerxda'), 503

    admin.set_sms_code(code)
    admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=5)
    db.session.commit()
    return jsonify(success=True, message='kodi xelaxla gaigzavna')


# ============================================================
# Password reset — form page + submit
# ============================================================

@landing_bp.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    token_hash = _hash_token(token)
    admin = AdminUser.query.filter_by(reset_token=token_hash).first()
    if not admin or not admin.reset_token_expires or datetime.utcnow() > admin.reset_token_expires:
        return render_template('reset_password.html', valid=False, token=token)
    return render_template('reset_password.html', valid=True, token=token)


@landing_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password_submit(token):
    data = request.get_json() or {}
    password = data.get('password', '')

    token_hash = _hash_token(token)
    admin = AdminUser.query.filter_by(reset_token=token_hash).first()
    if not admin or not admin.reset_token_expires or datetime.utcnow() > admin.reset_token_expires:
        return jsonify(error='linki arasworia an vadagasulia'), 400

    pw_error = validate_password(password)
    if pw_error:
        return jsonify(error=pw_error), 400

    admin.set_password(password)
    admin.reset_token = None
    admin.reset_token_expires = None
    admin.reset_failed_logins()
    db.session.commit()

    return jsonify(success=True, message='paroli warmatebuli Seicvala. SegiZliaT SexvideT.')
