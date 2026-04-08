"""Customer-facing reservation API routes."""
from functools import wraps
from flask import Blueprint, request, jsonify, session, abort, redirect
from app import db
from app.models import ReservationCustomer, Venue, RestaurantTable, Booking, ReservationSettings
from app.services.reservation_service import ReservationService
from app.services.payment_service import PaymentService
from app.services.notification_service import NotificationService

res_api_bp = Blueprint('res_api_bp', __name__)


def get_venue_or_abort(slug):
    venue = Venue.query.filter_by(slug=slug, is_active=True).first()
    if not venue:
        abort(404)
    if not venue.has_feature('reservations'):
        return jsonify(error='feature_disabled'), 403
    return venue


def customer_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'customer_id' not in session:
            return jsonify(error='authentication_required'), 401
        return f(*args, **kwargs)
    return decorated


# ============================================================
# Customer Auth
# ============================================================

@res_api_bp.route('/api/<slug>/customers/register', methods=['POST'])
def register_customer(slug):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')

    if not name or not email or not phone or not password:
        return jsonify(error='validation_error', message='All fields required'), 400

    if ReservationCustomer.query.filter_by(email=email).first():
        return jsonify(error='email_exists', message='Email already registered'), 400

    customer = ReservationCustomer(name=name, email=email, phone=phone,
                                    preferred_language=data.get('language', 'ka'))
    customer.set_password(password)
    db.session.add(customer)
    db.session.commit()

    session['customer_id'] = customer.id
    session['customer_name'] = customer.name
    session['customer_email'] = customer.email
    session['customer_phone'] = customer.phone
    return jsonify(success=True, customer_id=customer.id, name=customer.name), 201


@res_api_bp.route('/api/<slug>/customers/login', methods=['POST'])
def login_customer(slug):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    # Generic error — don't reveal if email exists
    generic_error = jsonify(error='invalid_credentials', message='Invalid email or password')

    customer = ReservationCustomer.query.filter_by(email=email).first()
    if not customer or not customer.check_password(password):
        return generic_error, 401

    session['customer_id'] = customer.id
    session['customer_name'] = customer.name
    session['customer_email'] = customer.email
    session['customer_phone'] = customer.phone
    return jsonify(success=True, customer_id=customer.id, name=customer.name, email=customer.email, phone=customer.phone)


# ============================================================
# Reservation Endpoints
# ============================================================

@res_api_bp.route('/api/<slug>/reservations/availability')
@customer_login_required
def get_availability(slug):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    date_str = request.args.get('date')
    time_str = request.args.get('time')
    guests = request.args.get('guests', type=int)

    if not date_str or not time_str or not guests:
        return jsonify(error='validation_error', message='date, time, guests required'), 400

    from datetime import datetime, time as dt_time
    try:
        date_val = datetime.strptime(date_str, '%Y-%m-%d').date()
        parts = time_str.split(':')
        time_val = dt_time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return jsonify(error='validation_error', message='Invalid date or time format'), 400

    tables = ReservationService.get_available_tables(venue.id, date_val, time_val, guests)

    # Also get all tables for the map (with availability status)
    all_tables = RestaurantTable.query.filter_by(venue_id=venue.id, is_active=True).all()
    available_ids = {t.id for t in tables}

    result = []
    for t in all_tables:
        result.append({
            'id': t.id, 'label': t.label, 'shape': t.shape,
            'capacity': t.capacity, 'pos_x': t.pos_x, 'pos_y': t.pos_y,
            'width': t.width, 'height': t.height,
            'available': t.id in available_ids,
        })

    # Get time slots from settings
    settings = ReservationSettings.query.filter_by(venue_id=venue.id).first()
    time_slots = settings.time_slots if settings else ["18:00", "19:00", "20:00", "21:00", "22:00"]

    return jsonify(tables=result, time_slots=time_slots)


@res_api_bp.route('/api/<slug>/reservations', methods=['POST'])
@customer_login_required
def create_reservation(slug):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    data = request.get_json() or {}
    data['customer_id'] = session['customer_id']

    try:
        booking = ReservationService.create_booking(venue.id, data)
    except ValueError as e:
        return jsonify(error='booking_error', message=str(e)), 409

    # Process payment
    ps = PaymentService()
    payment_result = ps.process_deposit(booking)

    return jsonify(
        success=True,
        booking_id=booking.id,
        status=booking.status,
        deposit_amount=booking.deposit_amount,
        payment_id=payment_result.payment_id if payment_result.success else None,
    ), 201


@res_api_bp.route('/api/<slug>/reservations/<int:booking_id>/pay', methods=['POST'])
@customer_login_required
def pay_reservation(slug, booking_id):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    booking = Booking.query.filter_by(id=booking_id, venue_id=venue.id).first()
    if not booking or booking.customer_id != session['customer_id']:
        return jsonify(error='not_found'), 404

    if booking.status != 'pending_payment':
        return jsonify(error='invalid_status', message='Booking is not pending payment'), 400

    ps = PaymentService()
    result = ps.confirm_payment(booking)

    if result.success:
        NotificationService.send_booking_confirmation(booking)
        return jsonify(success=True, status='confirmed')
    return jsonify(error='payment_failed', message=result.error), 402


@res_api_bp.route('/api/<slug>/reservations/my')
@customer_login_required
def my_reservations(slug):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    bookings = ReservationService.get_customer_bookings(session['customer_id'])
    result = []
    for b in bookings:
        if b.venue_id != venue.id:
            continue
        result.append({
            'id': b.id, 'date': str(b.booking_date),
            'time_slot': b.time_slot.strftime('%H:%M'),
            'guest_count': b.guest_count, 'status': b.status,
            'table_label': b.table.label if b.table else '',
            'venue_name': b.venue.name if b.venue else '',
            'comment': b.comment,
        })
    return jsonify(bookings=result)


@res_api_bp.route('/api/<slug>/reservations/<int:booking_id>/cancel', methods=['POST'])
@customer_login_required
def cancel_reservation(slug, booking_id):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    booking = Booking.query.filter_by(id=booking_id, venue_id=venue.id).first()
    if not booking or booking.customer_id != session['customer_id']:
        return jsonify(error='not_found'), 404

    try:
        ReservationService.cancel_booking(booking_id, cancelled_by='customer')
        NotificationService.send_booking_cancellation(booking)
        return jsonify(success=True, status='cancelled')
    except ValueError as e:
        return jsonify(error='cancel_error', message=str(e)), 400


@res_api_bp.route('/api/<slug>/reservations/cancel/<token>')
def cancel_by_token(slug, token):
    venue = get_venue_or_abort(slug)
    if isinstance(venue, tuple):
        return venue

    booking_id = NotificationService.verify_cancellation_token(token)
    if not booking_id:
        return jsonify(error='token_invalid'), 410

    try:
        booking = Booking.query.get(booking_id)
        if booking and booking.venue_id == venue.id:
            ReservationService.cancel_booking(booking_id, cancelled_by='customer')
            NotificationService.send_booking_cancellation(booking)
            return jsonify(success=True, status='cancelled', message='Booking cancelled successfully')
        return jsonify(error='not_found'), 404
    except ValueError as e:
        return jsonify(error='cancel_error', message=str(e)), 400


# ============================================================
# Google OAuth
# ============================================================

from authlib.integrations.flask_client import OAuth

_oauth = None

def get_oauth(app=None):
    global _oauth
    if _oauth is None:
        from flask import current_app
        app = app or current_app._get_current_object()
        _oauth = OAuth(app)
        _oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )
    return _oauth


@res_api_bp.route('/auth/google/login')
def google_login():
    """Redirect to Google OAuth. Store venue slug in session for callback."""
    slug = request.args.get('slug', 'demo')
    session['oauth_venue_slug'] = slug
    oauth = get_oauth()
    # Use PREFERRED_URL_SCHEME or detect from headers for Railway (behind proxy)
    base_url = request.url_root.rstrip('/')
    if request.headers.get('X-Forwarded-Proto') == 'https':
        base_url = base_url.replace('http://', 'https://')
    redirect_uri = base_url + '/auth/google/callback'
    return oauth.google.authorize_redirect(redirect_uri)


@res_api_bp.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback. Create or login customer."""
    oauth = get_oauth()
    token = oauth.google.authorize_access_token()
    userinfo = token.get('userinfo') or oauth.google.userinfo()

    email = userinfo.get('email', '').lower()
    name = userinfo.get('name', '')

    if not email:
        return redirect('/')

    # Find or create customer
    customer = ReservationCustomer.query.filter_by(email=email).first()
    if not customer:
        import secrets
        customer = ReservationCustomer(
            name=name, email=email, phone='',
            preferred_language='ka'
        )
        customer.set_password(secrets.token_hex(16))  # Random password for OAuth users
        db.session.add(customer)
        db.session.commit()

    session['customer_id'] = customer.id
    session['customer_name'] = customer.name
    session['customer_email'] = customer.email
    session['customer_phone'] = customer.phone

    slug = session.pop('oauth_venue_slug', 'demo')
    return redirect(f'/{slug}/reservations?auth=google')
