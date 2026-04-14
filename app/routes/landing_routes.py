# -*- coding: utf-8 -*-
"""Landing page and venue self-registration routes."""
import re
import secrets
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, jsonify, current_app)
from app import db
from app.models import AdminUser, Venue, _generate_venue_code, PhoneOtp
from app.services.registration_service import (
    send_sms_code, generate_email_token, send_verification_email,
    send_password_reset_email, search_google_place, generate_strong_password
)

landing_bp = Blueprint('landing_bp', __name__)

MAX_OTP_ATTEMPTS = 5


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or 'venue'


def _find_admin_by_identifier(identifier):
    """Find admin by phone or email."""
    identifier = identifier.strip().lower()
    if identifier.startswith('995') and len(identifier) == 12 and identifier.isdigit():
        return AdminUser.query.filter_by(phone=identifier).first()
    elif identifier.isdigit() and len(identifier) == 9:
        return AdminUser.query.filter_by(phone='995' + identifier).first()
    else:
        return AdminUser.query.filter_by(email=identifier).first()


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
# Inline phone OTP (pre-registration) — stored in DB table
# ============================================================


@landing_bp.route('/api/send-phone-otp', methods=['POST'])
def send_phone_otp():
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    if not phone or len(phone) < 9:
        return jsonify(error='telefonis nomeri arasworia'), 400

    # Rate limit: check existing unexpired OTP
    existing = PhoneOtp.query.filter_by(phone=phone).filter(
        PhoneOtp.expires > datetime.utcnow()
    ).first()
    if existing:
        remaining = int((existing.expires - datetime.utcnow()).total_seconds())
        if remaining > 60:
            return jsonify(error='gTxovT daelodoT ' + str(remaining - 60) + ' wami'), 429

    # Clean old entries for this phone
    PhoneOtp.query.filter_by(phone=phone).delete()
    db.session.commit()

    code, error = send_sms_code(phone)

    from werkzeug.security import generate_password_hash
    otp = PhoneOtp(
        phone=phone,
        code_hash=generate_password_hash(code),
        expires=datetime.utcnow() + timedelta(minutes=2),
        attempts=0
    )
    db.session.add(otp)
    db.session.commit()

    if error:
        current_app.logger.warning("SMS OTP error for " + phone + ": " + str(error))

    return jsonify(success=True, message='kodi gaigzavna')


@landing_bp.route('/api/verify-phone-otp', methods=['POST'])
def verify_phone_otp_api():
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    code = data.get('code', '').strip()

    entry = PhoneOtp.query.filter_by(phone=phone).filter(
        PhoneOtp.expires > datetime.utcnow()
    ).first()

    if not entry:
        return jsonify(error='kodi ver moiZebna. xelaxla gagzavneT'), 400

    if entry.attempts >= MAX_OTP_ATTEMPTS:
        PhoneOtp.query.filter_by(phone=phone).delete()
        db.session.commit()
        return jsonify(error='Zalian bevri mcdeloba. xelaxla gagzavneT kodi'), 400

    from werkzeug.security import check_password_hash
    entry.attempts += 1
    db.session.commit()

    if not check_password_hash(entry.code_hash, code):
        remaining = MAX_OTP_ATTEMPTS - entry.attempts
        return jsonify(error='kodi arasworia. darCa ' + str(remaining) + ' mcdeloba'), 400

    # Success — clean up and store in session
    PhoneOtp.query.filter_by(phone=phone).delete()
    db.session.commit()
    session['verified_phone'] = phone
    return jsonify(success=True)


# ============================================================
# Register — phone verified inline, account active immediately
# ============================================================

@landing_bp.route('/register', methods=['POST'])
def register_venue():
    data = request.get_json() or {}
    venue_name = data.get('venue_name', '').strip()
    address = data.get('address', '').strip()
    place_id = data.get('place_id', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')

    if not venue_name or not address or not email or not phone or not password:
        return jsonify(error='yvela veli savaldebuloa'), 400

    if not place_id:
        return jsonify(error='gTxovT, obieqti Google Maps-ze daadastureT'), 400

    # Normalize phone
    full_phone = ('995' + re.sub(r'\D', '', phone)) if not phone.startswith('995') else re.sub(r'\D', '', phone)

    # Verify phone was pre-verified via inline OTP
    verified_phone = session.get('verified_phone', '')
    if verified_phone != full_phone:
        return jsonify(error='telefoni ar aris verificirebuli'), 400

    if len(password) < 8:
        return jsonify(error='paroli minimum 8 simbolo unda iyos'), 400

    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify(error='el. fosta arasworia'), 400

    # Check duplicates — generic message to prevent enumeration
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
        code = _generate_venue_code()
        if not Venue.query.filter_by(venue_code=code).first():
            break

    # Create venue
    venue = Venue(name=venue_name, slug=slug, plan='free',
                  address=address, google_place_id=place_id, venue_code=code)
    db.session.add(venue)
    db.session.flush()

    # Create admin — ACTIVE immediately (phone verified)
    # email_verified=False until they click the email link
    username = slug
    email_token = generate_email_token()
    admin = AdminUser(
        username=username, email=email, phone=full_phone,
        role='venue', venue_id=venue.id,
        email_verified=False,
        phone_verified=True,
        is_active=True,
        email_token=email_token
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    # Send email verification in background (non-blocking)
    try:
        send_verification_email(email, email_token, venue_name)
    except Exception as e:
        current_app.logger.warning("Email send failed (non-critical): " + str(e))

    # Clear session and log in
    session.pop('verified_phone', None)
    session['admin_id'] = admin.id

    return jsonify(success=True, redirect='/backoffice')


# ============================================================
# Email verification link
# ============================================================

@landing_bp.route('/verify-email/<token>')
def verify_email(token):
    admin = AdminUser.query.filter_by(email_token=token).first()
    if not admin:
        return render_template('verify_result.html', success=False,
                               message='linki arasworia an vadagasulia.')

    admin.email_verified = True
    admin.email_token = None
    db.session.commit()

    session['admin_id'] = admin.id
    return redirect('/backoffice')


@landing_bp.route('/resend-email-verification', methods=['POST'])
def resend_email_verification():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify(error='el. fosta savaldebuloa'), 400

    admin = AdminUser.query.filter_by(email=email, email_verified=False).first()
    if admin:
        token = generate_email_token()
        admin.email_token = token
        db.session.commit()
        venue_name = admin.venue.name if admin.venue else 'Tably'
        try:
            send_verification_email(email, token, venue_name)
        except Exception as e:
            current_app.logger.warning("Resend email failed: " + str(e))

    # Always success (enumeration protection)
    return jsonify(success=True, message='Tu es el. fosta registrirebulia, gaigzavneba verifikaciis linki.')


# ============================================================
# Login — phone or email + password + SMS 2FA
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

        if not admin or not admin.check_password(password):
            # Record failed attempt if admin exists
            if admin:
                admin.record_failed_login()
                db.session.commit()
            return jsonify(error='monacemebi arasworia'), 401

        if admin.is_locked:
            return jsonify(error='angarishi droebiT daibloqa. scadeT 15 wuTSi'), 403

        if not admin.is_active:
            return jsonify(error='angarishi ar aris gaaqtiurebuli'), 403

        # Reset failed attempts on successful password
        admin.reset_failed_logins()

        # Send 2FA SMS
        code, sms_error = send_sms_code(admin.phone)
        if sms_error:
            current_app.logger.error("SMS 2FA failed for " + admin.phone + ": " + str(sms_error))
            # Fallback: allow login without 2FA if SMS service is down
            session['admin_id'] = admin.id
            db.session.commit()
            return jsonify(success=True, redirect='/backoffice',
                          message='Sesvla warmatebuli (SMS ver gaigzavna)')

        admin.set_sms_code(code)
        admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=2)
        db.session.commit()

        session['login_admin_id'] = admin.id

        # Mask phone number for display
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
            return jsonify(error='kodi vadagasulia'), 400

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
# Password reset — SMS OTP primary, email fallback
# ============================================================

@landing_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    identifier = data.get('identifier', '').strip()
    if not identifier:
        return jsonify(error='telefoni an el. fosta savaldebuloa'), 400

    admin = _find_admin_by_identifier(identifier)

    if admin and admin.is_active and admin.phone:
        # SMS-based reset (primary)
        code, sms_error = send_sms_code(admin.phone)
        if not sms_error:
            admin.set_sms_code(code)
            admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=5)
            db.session.commit()
            session['reset_admin_id'] = admin.id
            phone_display = '*' * (len(admin.phone) - 4) + admin.phone[-4:]
            return jsonify(success=True, method='sms',
                          message='SMS kodi gaigzavna ' + phone_display + '-ze')

        # Fallback to email if SMS failed
        if admin.email:
            try:
                token = secrets.token_urlsafe(32)
                admin.reset_token = token
                admin.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
                db.session.commit()
                send_password_reset_email(admin.email, token)
                return jsonify(success=True, method='email',
                              message='parolis agdgenis linki gaigzavna el. fostaze')
            except Exception as e:
                current_app.logger.error("Email reset failed: " + str(e))

    # Always return success (enumeration protection)
    return jsonify(success=True, method='generic',
                   message='Tu es monacemebi registrirebulia, miigebT agdgenis instruqcias.')


@landing_bp.route('/verify-reset-sms', methods=['POST'])
def verify_reset_sms():
    """Verify SMS OTP for password reset."""
    data = request.get_json() or {}
    code = data.get('code', '').strip()
    admin_id = session.get('reset_admin_id')

    if not admin_id or not code:
        return jsonify(error='sesia amoiwura'), 400

    admin = AdminUser.query.get(admin_id)
    if not admin or not admin.sms_code_hash or not admin.sms_code_expires:
        return jsonify(error='kodi ver moiZebna'), 400

    if datetime.utcnow() > admin.sms_code_expires:
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

    # Generate reset token for password change page
    token = secrets.token_urlsafe(32)
    admin.reset_token = token
    admin.reset_token_expires = datetime.utcnow() + timedelta(minutes=10)
    admin.sms_code_hash = None
    admin.sms_code_expires = None
    admin.sms_attempts = 0
    db.session.commit()

    session.pop('reset_admin_id', None)
    return jsonify(success=True, redirect='/reset-password/' + token)


@landing_bp.route('/resend-reset-sms', methods=['POST'])
def resend_reset_sms():
    """Resend SMS OTP for password reset."""
    admin_id = session.get('reset_admin_id')
    if not admin_id:
        return jsonify(error='sesia amoiwura'), 400

    admin = AdminUser.query.get(admin_id)
    if not admin:
        return jsonify(error='momxmarebeli ver moiZebna'), 400

    # Rate limit
    if admin.sms_code_expires and datetime.utcnow() < admin.sms_code_expires:
        remaining = int((admin.sms_code_expires - datetime.utcnow()).total_seconds())
        if remaining > 120:
            return jsonify(error='gTxovT daelodoT'), 429

    code, error = send_sms_code(admin.phone)
    if error:
        return jsonify(error='SMS gagzavna ver moxerxda'), 500

    admin.set_sms_code(code)
    admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=5)
    db.session.commit()

    return jsonify(success=True, message='kodi xelaxla gaigzavna')


# ============================================================
# Password reset — form page + submit
# ============================================================

@landing_bp.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    admin = AdminUser.query.filter_by(reset_token=token).first()
    if not admin or not admin.reset_token_expires or datetime.utcnow() > admin.reset_token_expires:
        return render_template('reset_password.html', valid=False, token=token)
    return render_template('reset_password.html', valid=True, token=token)


@landing_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password_submit(token):
    data = request.get_json() or {}
    password = data.get('password', '')

    admin = AdminUser.query.filter_by(reset_token=token).first()
    if not admin or not admin.reset_token_expires or datetime.utcnow() > admin.reset_token_expires:
        return jsonify(error='linki arasworia an vadagasulia'), 400

    if len(password) < 8:
        return jsonify(error='paroli minimum 8 simbolo unda iyos'), 400

    admin.set_password(password)
    admin.reset_token = None
    admin.reset_token_expires = None
    admin.reset_failed_logins()
    db.session.commit()

    return jsonify(success=True, message='paroli warmatebuli Seicvala. SegiZliaT SexvideT.')
