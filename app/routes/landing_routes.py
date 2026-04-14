"""Landing page and venue self-registration routes — multi-step flow."""
import re
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, current_app
from app import db
from app.models import AdminUser, Venue, _generate_venue_code
from app.services.registration_service import (
    send_sms_code, generate_email_token, send_verification_email,
    send_password_reset_email,
    search_google_place, generate_strong_password
)

landing_bp = Blueprint('landing_bp', __name__)


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text or 'venue'


# ============================================================
# Landing page
# ============================================================

@landing_bp.route('/')
def landing():
    venues = Venue.query.filter_by(is_active=True).all()
    return render_template('landing.html', venues=venues)


# ============================================================
# Step 1: Search Google Places (venue name + address autocomplete)
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
# Step 2: Register — create pending account, send SMS
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

    # Validation
    if not venue_name or not address or not email or not phone or not password:
        return jsonify(error='ყველა ველი სავალდებულოა'), 400

    if not place_id:
        return jsonify(error='გთხოვთ, ობიექტი Google Maps-ზე დაადასტურეთ'), 400

    # Verify phone was pre-verified via inline OTP
    full_phone = ('995' + re.sub(r'\D', '', phone)) if not phone.startswith('995') else re.sub(r'\D', '', phone)
    verified_phone = session.get('verified_phone', '')
    if verified_phone != full_phone:
        return jsonify(error='ტელეფონი არ არის ვერიფიცირებული. გთხოვთ კოდი დაადასტურეთ'), 400

    if len(password) < 8:
        return jsonify(error='პაროლი მინიმუმ 8 სიმბოლო უნდა იყოს'), 400

    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify(error='ელ. ფოსტა არასწორია'), 400

    if AdminUser.query.filter_by(email=email).first():
        return jsonify(error='ეს ელ. ფოსტა უკვე რეგისტრირებულია'), 400

    # Generate unique slug
    base_slug = slugify(venue_name)
    slug = base_slug
    counter = 2
    while Venue.query.filter_by(slug=slug).first():
        slug = f'{base_slug}-{counter}'
        counter += 1

    # Create venue
    # Generate unique venue_code
    while True:
        code = _generate_venue_code()
        if not Venue.query.filter_by(venue_code=code).first():
            break
    venue = Venue(name=venue_name, slug=slug, plan='free',
                  address=address, google_place_id=place_id, venue_code=code)
    db.session.add(venue)
    db.session.flush()

    # Create admin (inactive until verified)
    username = slug  # use slug as internal username
    email_token = generate_email_token()
    admin = AdminUser(
        username=username, email=email, phone=phone,
        role='venue', venue_id=venue.id,
        email_verified=False, phone_verified=False,
        is_active=False, email_token=email_token
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    # Phone already verified inline — mark as verified
    admin.phone_verified = True
    db.session.commit()

    # Send email verification
    send_verification_email(email, email_token, venue_name)

    # Clear verified phone from session
    session.pop('verified_phone', None)
    session['pending_admin_id'] = admin.id

    return jsonify(success=True, step='verify_email',
                   message='ვერიფიკაციის ლინკი გაიგზავნა ' + email + '-ზე. შეამოწმეთ inbox.')


# ============================================================
# Step 3: Verify phone OTP
# ============================================================

@landing_bp.route('/verify-phone', methods=['POST'])
def verify_phone():
    data = request.get_json() or {}
    code = data.get('code', '').strip()
    admin_id = session.get('pending_admin_id')

    if not admin_id:
        return jsonify(error='სესია ამოიწურა'), 400

    admin = AdminUser.query.get(admin_id)
    if not admin:
        return jsonify(error='მომხმარებელი ვერ მოიძებნა'), 400

    if not admin.sms_code or not admin.sms_code_expires:
        return jsonify(error='კოდი ვერ მოიძებნა'), 400

    if datetime.utcnow() > admin.sms_code_expires:
        return jsonify(error='კოდი ვადაგასულია. ხელახლა გაგზავნეთ'), 400

    if admin.sms_code != code:
        return jsonify(error='კოდი არასწორია'), 400

    admin.phone_verified = True
    admin.sms_code = None
    admin.sms_code_expires = None

    # If email also verified, activate
    if admin.email_verified:
        admin.is_active = True
        db.session.commit()
        session.pop('pending_admin_id', None)
        session['admin_id'] = admin.id
        return jsonify(success=True, redirect='/backoffice', fully_verified=True)

    db.session.commit()
    return jsonify(success=True, step='verify_email',
                   message='ტელეფონი დადასტურდა. შეამოწმეთ ელ. ფოსტა.')


# ============================================================
# Step 4: Resend SMS (rate-limited: 1 per minute)
# ============================================================

@landing_bp.route('/resend-sms', methods=['POST'])
def resend_sms():
    admin_id = session.get('pending_admin_id')
    if not admin_id:
        return jsonify(error='სესია ამოიწურა'), 400

    admin = AdminUser.query.get(admin_id)
    if not admin:
        return jsonify(error='მომხმარებელი ვერ მოიძებნა'), 400

    # Rate limit: 1 minute
    if admin.sms_code_expires and datetime.utcnow() < admin.sms_code_expires:
        remaining = int((admin.sms_code_expires - datetime.utcnow()).total_seconds())
        return jsonify(error=f'გთხოვთ დაელოდოთ {remaining} წამი'), 429

    code, error = send_sms_code(admin.phone)
    admin.sms_code = code
    admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=1)
    db.session.commit()

    return jsonify(success=True, message='კოდი ხელახლა გაიგზავნა')


# ============================================================
# Email verification link
# ============================================================

@landing_bp.route('/verify-email/<token>')
def verify_email(token):
    admin = AdminUser.query.filter_by(email_token=token).first()
    if not admin:
        return render_template('verify_result.html', success=False,
                               message='ლინკი არასწორია ან ვადაგასულია.')

    admin.email_verified = True
    admin.email_token = None

    if admin.phone_verified:
        admin.is_active = True
        db.session.commit()
        session['admin_id'] = admin.id
        return redirect('/backoffice')

    db.session.commit()
    return render_template('verify_result.html', success=True,
                           message='ელ. ფოსტა დადასტურდა! ახლა ტელეფონი დაადასტურეთ.')


@landing_bp.route('/resend-email-verification', methods=['POST'])
def resend_email_verification():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify(error='ელ. ფოსტა სავალდებულოა'), 400

    admin = AdminUser.query.filter_by(email=email, email_verified=False).first()
    if admin:
        token = generate_email_token()
        admin.email_token = token
        db.session.commit()
        venue_name = admin.venue.name if admin.venue else 'Tably'
        send_verification_email(email, token, venue_name)
        current_app.logger.info(f"[RESEND EMAIL] {email}")

    # Always return success (email enumeration protection)
    return jsonify(success=True, message='თუ ეს ელ. ფოსტა რეგისტრირებულია, გაიგზავნება ვერიფიკაციის ლინკი.')


# ============================================================
# Login — email + password + SMS 2FA
# ============================================================

@landing_bp.route('/login-venue', methods=['POST'])
def login_venue():
    data = request.get_json() or {}
    step = data.get('step', 'credentials')

    if step == 'credentials':
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        admin = AdminUser.query.filter_by(email=email).first()
        if not admin or not admin.check_password(password):
            return jsonify(error='ელ. ფოსტა ან პაროლი არასწორია'), 401

        if not admin.is_active:
            if not admin.email_verified:
                return jsonify(error='ელ. ფოსტა არ არის დადასტურებული. შეამოწმეთ inbox.'), 403
            return jsonify(error='ანგარიში ჯერ არ არის გააქტიურებული.'), 403

        # Send 2FA SMS
        code, sms_error = send_sms_code(admin.phone)
        admin.sms_code = code
        admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=1)
        db.session.commit()

        session['login_admin_id'] = admin.id
        return jsonify(success=True, step='sms_2fa',
                       message='SMS კოდი გაიგზავნა ' + admin.phone[-4:].rjust(len(admin.phone), '*'))

    elif step == 'sms_2fa':
        code = data.get('code', '').strip()
        admin_id = session.get('login_admin_id')

        if not admin_id:
            return jsonify(error='სესია ამოიწურა'), 400

        admin = AdminUser.query.get(admin_id)
        if not admin:
            return jsonify(error='მომხმარებელი ვერ მოიძებნა'), 400

        if not admin.sms_code or datetime.utcnow() > admin.sms_code_expires:
            return jsonify(error='კოდი ვადაგასულია'), 400

        if admin.sms_code != code:
            return jsonify(error='კოდი არასწორია'), 400

        admin.sms_code = None
        admin.sms_code_expires = None
        db.session.commit()

        session.pop('login_admin_id', None)
        session['admin_id'] = admin.id
        return jsonify(success=True, redirect='/backoffice')

    return jsonify(error='Invalid step'), 400


# ============================================================
# Password suggestion
# ============================================================

@landing_bp.route('/api/suggest-password')
def suggest_password():
    return jsonify(password=generate_strong_password())


# ============================================================
# Inline phone OTP (before registration)
# ============================================================

# In-memory store for pre-registration OTPs: {phone: {code, expires}}
_phone_otps = {}


@landing_bp.route('/api/send-phone-otp', methods=['POST'])
def send_phone_otp():
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    if not phone or len(phone) < 9:
        return jsonify(error='ტელეფონის ნომერი არასწორია'), 400

    # Rate limit: 1 per minute
    existing = _phone_otps.get(phone)
    if existing and datetime.utcnow() < existing['expires']:
        remaining = int((existing['expires'] - datetime.utcnow()).total_seconds())
        return jsonify(error=f'გთხოვთ დაელოდოთ {remaining} წამი'), 429

    code, error = send_sms_code(phone)
    _phone_otps[phone] = {
        'code': code,
        'expires': datetime.utcnow() + timedelta(minutes=1)
    }

    if error:
        current_app.logger.warning(f"SMS OTP error for {phone}: {error}")

    return jsonify(success=True, message='კოდი გაიგზავნა')


@landing_bp.route('/api/verify-phone-otp', methods=['POST'])
def verify_phone_otp_api():
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    code = data.get('code', '').strip()

    entry = _phone_otps.get(phone)
    if not entry:
        return jsonify(error='კოდი ვერ მოიძებნა. ხელახლა გაგზავნეთ'), 400

    if datetime.utcnow() > entry['expires']:
        del _phone_otps[phone]
        return jsonify(error='კოდი ვადაგასულია'), 400

    if entry['code'] != code:
        return jsonify(error='კოდი არასწორია'), 400

    del _phone_otps[phone]
    # Store verified phone in session
    session['verified_phone'] = phone
    return jsonify(success=True)


# ============================================================
# Password reset — request
# ============================================================

@landing_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify(error='ელ. ფოსტა სავალდებულოა'), 400

    admin = AdminUser.query.filter_by(email=email).first()
    current_app.logger.info(f"[FORGOT] email={email} found={admin is not None} active={admin.is_active if admin else 'N/A'}")

    if admin and admin.is_active:
        token = secrets.token_urlsafe(32)
        admin.reset_token = token
        admin.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        result = send_password_reset_email(email, token)
        current_app.logger.info(f"[FORGOT] email send result={result}")

    return jsonify(success=True, message='თუ ეს ელ. ფოსტა რეგისტრირებულია, გაიგზავნება პაროლის აღდგენის ლინკი.')


# ============================================================
# Password reset — form page
# ============================================================

@landing_bp.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    admin = AdminUser.query.filter_by(reset_token=token).first()
    if not admin or not admin.reset_token_expires or datetime.utcnow() > admin.reset_token_expires:
        return render_template('reset_password.html', valid=False, token=token)
    return render_template('reset_password.html', valid=True, token=token)


# ============================================================
# Password reset — submit new password
# ============================================================

@landing_bp.route('/reset-password/<token>', methods=['POST'])
def reset_password_submit(token):
    data = request.get_json() or {}
    password = data.get('password', '')

    admin = AdminUser.query.filter_by(reset_token=token).first()
    if not admin or not admin.reset_token_expires or datetime.utcnow() > admin.reset_token_expires:
        return jsonify(error='ლინკი არასწორია ან ვადაგასულია.'), 400

    if len(password) < 8:
        return jsonify(error='პაროლი მინიმუმ 8 სიმბოლო უნდა იყოს'), 400

    admin.set_password(password)
    admin.reset_token = None
    admin.reset_token_expires = None
    db.session.commit()

    return jsonify(success=True, message='პაროლი წარმატებით შეიცვალა. შეგიძლიათ შეხვიდეთ.')
