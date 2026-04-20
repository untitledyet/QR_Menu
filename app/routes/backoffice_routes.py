import os
import json
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app import db
from app.models import (AdminUser, Venue, VenueFeatureOverride, Category, Subcategory,
                         FoodItem, Promotion, Order, PLAN_FEATURES, FEATURE_LIST,
                         MAX_ITEMS_PER_VENUE, ScraperJob, GlobalItem, GlobalCategory)
from app.services.registration_service import validate_password, send_sms_code, send_2fa_email
from app.services.translation_service import (
    translate_item_async, translate_category_async, needs_translation
)

bo_bp = Blueprint('bo_bp', __name__, url_prefix='/backoffice')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _trigger_item_translation(item, name_ka, name_en, desc_ka, desc_en, ing_ka, ing_en):
    """Fire Gemini translation for whichever language is missing."""
    app = current_app._get_current_object()
    if needs_translation(name_ka, name_en):
        # KA filled, EN missing → translate KA→EN
        translate_item_async(item.FoodItemID,
                             {'name': name_ka or '', 'description': desc_ka or '',
                              'ingredients': ing_ka or ''},
                             'ka', 'en', app)
    elif needs_translation(name_en, name_ka):
        # EN filled, KA missing → translate EN→KA
        translate_item_async(item.FoodItemID,
                             {'name': name_en or '', 'description': desc_en or '',
                              'ingredients': ing_en or ''},
                             'en', 'ka', app)
def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def email_verified_required(f):
    """Block access if venue admin has not verified email."""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        if admin and not admin.is_super and not admin.email_verified:
            flash('el. fostis verifikacia saWiroa. Seamowmet inbox.')
            return redirect(url_for('bo_bp.dashboard'))
        return f(*args, **kwargs)
    return decorated

def super_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        if not admin or not admin.is_super:
            flash('Access denied')
            return redirect(url_for('bo_bp.dashboard'))
        return f(*args, **kwargs)
    return decorated

def get_current_admin():
    return AdminUser.query.get(session['admin_id']) if 'admin_id' in session else None


def verify_item_ownership(item_id):
    """Verify that the item belongs to the current admin's venue."""
    admin = get_current_admin()
    item = FoodItem.query.get_or_404(item_id)
    if admin and admin.venue:
        cat = Category.query.get(item.CategoryID)
        if not cat or cat.venue_id != admin.venue.id:
            return None
    return item


def verify_category_ownership(cat_id):
    admin = get_current_admin()
    cat = Category.query.get_or_404(cat_id)
    if admin and admin.venue and cat.venue_id != admin.venue.id:
        return None
    return cat


def verify_promo_ownership(promo_id):
    admin = get_current_admin()
    promo = Promotion.query.get_or_404(promo_id)
    if admin and admin.venue and promo.venue_id != admin.venue.id:
        return None
    return promo


# ============================================================
# Auth
# ============================================================

@bo_bp.route('/login', methods=['POST'])
def login():
    """Backoffice login — POST only, handles AJAX auth."""

    data = request.get_json() or {}
    step = data.get('step', 'credentials')

    if step == 'credentials':
        username = data.get('username', '').strip()
        password = data.get('password', '')

        if not username or not password:
            return jsonify(error='SeavseT yvela veli'), 400

        # Lookup: username (super admin) → email fallback
        admin = AdminUser.query.filter_by(username=username).first()
        if not admin:
            admin = AdminUser.query.filter_by(email=username).first()

        # 1. Lockout check FIRST
        if admin and admin.is_locked:
            return jsonify(error='angarishi droebiT daibloqa. scadeT 15 wuTSi'), 403

        # 2. Password check
        if not admin or not admin.check_password(password):
            if admin:
                admin.record_failed_login()
                db.session.commit()
            return jsonify(error='Invalid credentials'), 401

        # 3. Active check
        if not admin.is_active and not admin.is_super:
            return jsonify(error='angarishi ar aris gaaqtiurebuli'), 403

        admin.reset_failed_logins()
        lang = getattr(admin, 'lang', 'ka') or 'ka'

        # 4. 2FA by method
        if admin.two_fa_method == 'sms' and admin.phone:
            code, sms_error = send_sms_code(admin.phone, lang=lang)
            if sms_error:
                current_app.logger.error(
                    'Backoffice 2FA SMS failed for admin id=' + str(admin.id) + ': ' + str(sms_error)
                )
                db.session.commit()
                return jsonify(error='SMS gagzavna ver moxerxda. scadeT mogvianebiT'), 503
            admin.set_sms_code(code)
            admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=2)
            db.session.commit()
            session['bo_pending_admin_id'] = admin.id
            phone_display = '*' * (len(admin.phone) - 4) + admin.phone[-4:]
            return jsonify(success=True, step='sms_2fa',
                           message='SMS kodi gaigzavna ' + phone_display + '-ze')

        if admin.two_fa_method == 'email' and admin.email:
            import random as _rnd
            code = ''.join([str(_rnd.randint(0, 9)) for _ in range(6)])
            admin.set_sms_code(code)
            admin.sms_code_expires = datetime.utcnow() + timedelta(minutes=2)
            db.session.commit()
            session['bo_pending_admin_id'] = admin.id
            try:
                send_2fa_email(admin.email, code, lang=lang)
            except Exception as e:
                current_app.logger.error('2FA email failed: ' + str(e))
                return jsonify(error='Email gagzavna ver moxerxda. scadeT mogvianebiT'), 503
            email_display = admin.email[:3] + '***@' + admin.email.split('@')[-1]
            return jsonify(success=True, step='sms_2fa',
                           message='kodi gaigzavna ' + email_display + '-ze')

        # No 2FA configured
        db.session.commit()
        session['admin_id'] = admin.id
        return jsonify(success=True, redirect='/backoffice')

    elif step == 'sms_2fa':
        code = data.get('code', '').strip()
        admin_id = session.get('bo_pending_admin_id')

        if not admin_id:
            return jsonify(error='sesia amoiwura'), 400

        admin = AdminUser.query.get(admin_id)
        if not admin or not admin.sms_code_hash or not admin.sms_code_expires:
            return jsonify(error='kodi ver moiZebna'), 400

        if datetime.utcnow() > admin.sms_code_expires:
            admin.sms_code_hash = None
            admin.sms_code_expires = None
            db.session.commit()
            return jsonify(error='kodi vadagasulia. Tavidan scadeT'), 400

        if admin.sms_attempts >= 5:
            admin.sms_code_hash = None
            admin.sms_code_expires = None
            db.session.commit()
            return jsonify(error='Zalian bevri mcdeloba. Tavidan scadeT'), 400

        admin.sms_attempts = (admin.sms_attempts or 0) + 1

        if not admin.check_sms_code(code):
            remaining = 5 - admin.sms_attempts
            db.session.commit()
            return jsonify(error='kodi arasworia. darCa ' + str(remaining) + ' mcdeloba'), 400

        # Success
        admin.sms_code_hash = None
        admin.sms_code_expires = None
        admin.sms_attempts = 0
        db.session.commit()

        session.pop('bo_pending_admin_id', None)
        session['admin_id'] = admin.id
        return jsonify(success=True, redirect='/backoffice')

    return jsonify(error='Invalid step'), 400


@bo_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    admin = get_current_admin()
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if not admin.check_password(current):
            flash('მიმდინარე პაროლი არასწორია')
        elif new_pw != confirm:
            flash('პაროლები არ ემთხვევა')
        else:
            pw_error = validate_password(new_pw)
            if pw_error:
                flash(pw_error)
            else:
                admin.set_password(new_pw)
                db.session.commit()
                flash('პაროლი წარმატებით შეიცვალა')
                return redirect(url_for('bo_bp.dashboard'))
    return render_template('backoffice/change_password.html', admin=admin)

@bo_bp.route('/logout')
def logout():
    session.pop('admin_id', None)
    return redirect('/login')


@bo_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    admin = get_current_admin()
    if request.method == 'POST':
        method = request.form.get('two_fa_method')
        if method in ('sms', 'email'):
            admin.two_fa_method = method
            admin.two_fa_enabled = True
        else:
            admin.two_fa_method = None
            admin.two_fa_enabled = False
        db.session.commit()
        flash('პარამეტრები შენახულია')
        return redirect(url_for('bo_bp.profile'))
    return render_template('backoffice/profile.html', admin=admin)


# ============================================================
# Dashboard
# ============================================================

@bo_bp.route('/')
@login_required
def dashboard():
    admin = get_current_admin()
    if admin.is_super:
        venues = Venue.query.order_by(Venue.created_at.desc()).all()
        total_items = FoodItem.query.count()
        total_orders = Order.query.count()

        # Plan distribution
        plan_counts = {p: 0 for p in PLAN_FEATURES.keys()}
        active_count = 0
        for v in venues:
            plan_counts[v.plan] = plan_counts.get(v.plan, 0) + 1
            if v.is_active:
                active_count += 1

        # Per-venue stats (item + admin count) — keep cheap
        venue_stats = {}
        for v in venues:
            venue_stats[v.id] = {
                'item_count': FoodItem.query.join(Category).filter(Category.venue_id == v.id).count(),
                'admins': AdminUser.query.filter_by(venue_id=v.id).count(),
            }

        # Recent (last 7 days) venue signups
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_venues = sum(1 for v in venues if v.created_at and v.created_at >= week_ago)

        return render_template('backoffice/super_dashboard.html', admin=admin,
                               venues=venues, total_items=total_items, total_orders=total_orders,
                               plan_counts=plan_counts, active_count=active_count,
                               inactive_count=len(venues) - active_count,
                               recent_venues=recent_venues, venue_stats=venue_stats,
                               feature_list=FEATURE_LIST)
    else:
        venue = admin.venue
        features = venue.get_all_features() if venue else {}
        # Server-side stats (avoid '—' flash)
        stats = {
            'item_count': 0, 'categories': 0, 'promotions': 0,
            'tables': venue.total_tables if venue else 0,
            'bookings': 0, 'max_items': MAX_ITEMS_PER_VENUE,
        }
        if venue:
            stats['item_count'] = venue.item_count()
            stats['categories'] = Category.query.filter_by(venue_id=venue.id).count()
            stats['promotions'] = Promotion.query.filter_by(venue_id=venue.id).count()
            if features.get('reservations'):
                stats['bookings'] = Booking.query.filter_by(venue_id=venue.id).count()
        return render_template('backoffice/dashboard.html', admin=admin, venue=venue,
                               features=features, stats=stats, feature_list=FEATURE_LIST)


# ============================================================
# Super Admin — Scraper test panel
# ============================================================

@bo_bp.route('/super/scraper-test')
@login_required
@super_required
def super_scraper_panel():
    admin = get_current_admin()
    venues = Venue.query.order_by(Venue.name).all()
    venue_id = request.args.get('venue_id', type=int)
    place_id_param = request.args.get('place_id', '')
    selected_venue = Venue.query.get(venue_id) if venue_id else None
    job = ScraperJob.query.filter_by(venue_id=selected_venue.id).first() if selected_venue else None
    return render_template('backoffice/super_scraper.html', admin=admin,
                           venues=venues, selected_venue=selected_venue,
                           place_id_param=place_id_param, job=job)


@bo_bp.route('/super/scraper-test/trigger', methods=['POST'])
@login_required
@super_required
def super_scraper_trigger():
    data = request.get_json() or {}
    venue_id = data.get('venue_id')
    place_id = (data.get('place_id') or '').strip()
    if not venue_id or not place_id:
        return jsonify(error='venue_id and place_id required'), 400
    venue = Venue.query.get_or_404(venue_id)
    try:
        job = ScraperJob.query.filter_by(venue_id=venue.id).first()
        if not job:
            job = ScraperJob(venue_id=venue.id, status='pending')
            db.session.add(job)
        else:
            job.status = 'pending'
            job.result_json = None
            job.error_message = None
            job.sources_found = None
            job.finished_at = None
        db.session.commit()
        from app.scraper.job_runner import trigger_scraper_job
        trigger_scraper_job(current_app._get_current_object(), venue.id, place_id, venue.name)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(error=str(e)), 500


@bo_bp.route('/super/scraper-test/reset', methods=['POST'])
@login_required
@super_required
def super_scraper_reset():
    data = request.get_json() or {}
    venue_id = data.get('venue_id')
    if not venue_id:
        return jsonify(error='venue_id required'), 400
    job = ScraperJob.query.filter_by(venue_id=venue_id).first()
    if job:
        job.status = 'pending'
        job.result_json = None
        job.error_message = None
        job.sources_found = None
        job.finished_at = None
        db.session.commit()
    return jsonify(success=True)


@bo_bp.route('/super/scraper-test/status')
@login_required
@super_required
def super_scraper_status():
    venue_id = request.args.get('venue_id', type=int)
    if not venue_id:
        return jsonify(status='none')
    job = ScraperJob.query.filter_by(venue_id=venue_id).first()
    if not job:
        return jsonify(status='none')
    resp = {'status': job.status, 'error': job.error_message}
    if job.result_json:
        resp['stats'] = job.result_json.get('_stats', {})
        resp['sources'] = job.sources_found or {}
        if job.status == 'done':
            resp['categories'] = {k: len(v) for k, v in job.result_json.get('categories', {}).items()}
    return jsonify(resp)


@bo_bp.route('/super/scraper-test/test-r2', methods=['POST'])
@login_required
@super_required
def super_test_r2():
    try:
        from app.services.r2_storage import _upload_bytes, R2_ENDPOINT, R2_BUCKET, R2_PUBLIC_URL
        pixel = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
            b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        url = _upload_bytes(pixel, 'dev/test_pixel.png', 'image/png')
        return jsonify(success=bool(url), url=url,
                       endpoint=R2_ENDPOINT, bucket=R2_BUCKET, public_url=R2_PUBLIC_URL)
    except Exception as e:
        return jsonify(success=False, error=str(e))


@bo_bp.route('/super/scraper-test/test-openai', methods=['POST'])
@login_required
@super_required
def super_test_openai():
    try:
        import httpx
        from openai import OpenAI
        from app.scraper import config as sc
        key = sc.OPENAI_API_KEY
        if not key:
            return jsonify(success=False, error='OPENAI_API_KEY not set')
        client = OpenAI(api_key=key, http_client=httpx.Client(timeout=30.0))
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': 'Reply with just: OK'}],
            max_tokens=5,
        )
        return jsonify(success=True, response=resp.choices[0].message.content,
                       key_prefix=key[:8] + '...')
    except Exception as e:
        return jsonify(success=False, error=str(e))


@bo_bp.route('/super/scraper-test/detail')
@login_required
@super_required
def super_scraper_detail():
    venue_id = request.args.get('venue_id', type=int)
    if not venue_id:
        return jsonify(error='venue_id required'), 400
    job = ScraperJob.query.filter_by(venue_id=venue_id).first()
    if not job or not job.result_json:
        return jsonify(status='none')
    categories = job.result_json.get('categories', {})
    flat = []
    for cat, items in categories.items():
        for it in items:
            flat.append({
                'category': cat,
                'name': it.get('name', ''),
                'price': it.get('price', ''),
                'description': it.get('description', ''),
                'ingredients': it.get('ingredients', ''),
                'source': it.get('source', ''),
                'image': it.get('image', ''),
                'library_photo': it.get('library_photo', ''),
            })
    return jsonify(
        status=job.status,
        log=job.result_json.get('_log', []),
        stats=job.result_json.get('_stats', {}),
        sources=job.sources_found or {},
        items=flat,
    )


# ============================================================
# Super Admin — Venue Management
# ============================================================

@bo_bp.route('/venues')
@login_required
@super_required
def venues_list():
    admin = get_current_admin()
    venues = Venue.query.order_by(Venue.created_at.desc()).all()
    venue_stats = {}
    for v in venues:
        venue_stats[v.id] = {
            'item_count': FoodItem.query.join(Category).filter(Category.venue_id == v.id).count(),
            'admins': AdminUser.query.filter_by(venue_id=v.id).count(),
            'categories': Category.query.filter_by(venue_id=v.id).count(),
        }
    return render_template('backoffice/super_venues.html', admin=admin, venues=venues,
                           venue_stats=venue_stats, plans=list(PLAN_FEATURES.keys()))


@bo_bp.route('/venues/<int:venue_id>/features', methods=['GET', 'POST'])
@login_required
@super_required
def venue_features(venue_id):
    admin = get_current_admin()
    venue = Venue.query.get_or_404(venue_id)

    if request.method == 'POST':
        # Update plan
        new_plan = request.form.get('plan', 'free')
        if new_plan in PLAN_FEATURES:
            venue.plan = new_plan

        # Update individual overrides
        plan_defaults = PLAN_FEATURES.get(venue.plan, PLAN_FEATURES['free'])
        for key, _, _, _ in FEATURE_LIST:
            form_val = key in request.form
            plan_default = plan_defaults.get(key, False)

            # Only create override if different from plan default
            existing = VenueFeatureOverride.query.filter_by(venue_id=venue.id, feature_key=key).first()
            if form_val != plan_default:
                if existing:
                    existing.enabled = form_val
                else:
                    db.session.add(VenueFeatureOverride(venue_id=venue.id, feature_key=key, enabled=form_val))
            else:
                # Remove override if matches plan default
                if existing:
                    db.session.delete(existing)

        db.session.commit()
        flash(f'{venue.name} features updated')
        return redirect(url_for('bo_bp.venue_features', venue_id=venue.id))

    features = venue.get_all_features()
    plan_defaults = PLAN_FEATURES.get(venue.plan, PLAN_FEATURES['free'])
    overrides = {o.feature_key: o.enabled for o in venue.feature_overrides}

    return render_template('backoffice/super_venue_features.html', admin=admin, venue=venue,
                           features=features, plan_defaults=plan_defaults, overrides=overrides,
                           feature_list=FEATURE_LIST, plans=list(PLAN_FEATURES.keys()),
                           plan_features_json=json.dumps(PLAN_FEATURES))


@bo_bp.route('/venues/<int:venue_id>/toggle-active', methods=['POST'])
@login_required
@super_required
def toggle_venue_active(venue_id):
    venue = Venue.query.get_or_404(venue_id)
    venue.is_active = not venue.is_active
    db.session.commit()
    return jsonify(success=True, is_active=venue.is_active)


@bo_bp.route('/venues/<int:venue_id>/delete', methods=['POST'])
@login_required
@super_required
def delete_venue(venue_id):
    venue = Venue.query.get_or_404(venue_id)
    name = venue.name
    from app.models import (RestaurantTable, Booking, ReservationSettings,
                             VenueGroup, VenueGroupInvite, VenueItemPriceOverride)

    # ── 1. Group cleanup ───────────────────────────────────────────────────
    # If this venue OWNS a group: delete invites, detach branches, delete group
    owned_group = VenueGroup.query.filter_by(owner_venue_id=venue_id).first()
    if owned_group:
        VenueGroupInvite.query.filter_by(group_id=owned_group.id).delete()
        # Detach all branches (set group_id = NULL)
        db.session.execute(
            db.text('UPDATE "Venues" SET group_id = NULL WHERE group_id = :gid'),
            {'gid': owned_group.id}
        )
        db.session.flush()
        db.session.delete(owned_group)
        db.session.flush()

    # If this venue is a MEMBER of another group: just detach it
    if venue.group_id:
        venue.group_id = None
        db.session.flush()

    # ── 2. Delete invites created BY this venue's admin users ──────────────
    admin_ids = [a.id for a in AdminUser.query.filter_by(venue_id=venue_id).all()]
    if admin_ids:
        VenueGroupInvite.query.filter(
            VenueGroupInvite.invited_by.in_(admin_ids)
        ).delete(synchronize_session='fetch')

    # ── 3. Price overrides for this venue ──────────────────────────────────
    VenueItemPriceOverride.query.filter_by(venue_id=venue_id).delete()

    # ── 4. Reservations & tables ───────────────────────────────────────────
    Booking.query.filter_by(venue_id=venue_id).delete()
    RestaurantTable.query.filter_by(venue_id=venue_id).delete()
    ReservationSettings.query.filter_by(venue_id=venue_id).delete()

    # ── 5. Menu content ────────────────────────────────────────────────────
    Promotion.query.filter_by(venue_id=venue_id).delete()
    cats = Category.query.filter_by(venue_id=venue_id).all()
    for cat in cats:
        FoodItem.query.filter_by(CategoryID=cat.CategoryID).update({'SubcategoryID': None})
        FoodItem.query.filter_by(CategoryID=cat.CategoryID).delete()
        Subcategory.query.filter_by(CategoryID=cat.CategoryID).delete()
    Category.query.filter_by(venue_id=venue_id).delete()

    # ── 6. Orders / overrides / admin users ───────────────────────────────
    Order.query.filter_by(venue_id=venue_id).delete()
    VenueFeatureOverride.query.filter_by(venue_id=venue_id).delete()
    AdminUser.query.filter_by(venue_id=venue_id).delete()

    # ── 7. Venue itself ────────────────────────────────────────────────────
    db.session.delete(venue)
    db.session.commit()
    return jsonify(success=True, message=f'"{name}" და მისი ყველა მონაცემი წაიშალა')


@bo_bp.route('/venues/add', methods=['GET', 'POST'])
@login_required
@super_required
def add_venue():
    admin = get_current_admin()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        plan = request.form.get('plan', 'free')
        admin_username = request.form.get('admin_username', '').strip()
        admin_password = request.form.get('admin_password', '').strip()

        if not name or not slug:
            flash('Name and slug are required')
            return redirect(url_for('bo_bp.add_venue'))

        if Venue.query.filter_by(slug=slug).first():
            flash('Slug already exists')
            return redirect(url_for('bo_bp.add_venue'))

        venue = Venue(name=name, slug=slug, plan=plan)
        db.session.add(venue)
        db.session.commit()

        if admin_username and admin_password:
            venue_admin = AdminUser(username=admin_username, role='venue', venue_id=venue.id)
            venue_admin.set_password(admin_password)
            db.session.add(venue_admin)
            db.session.commit()

        flash(f'Venue "{name}" created')
        return redirect(url_for('bo_bp.venues_list'))

    return render_template('backoffice/super_add_venue.html', admin=admin, plans=list(PLAN_FEATURES.keys()))


# ============================================================
# Venue Admin — Menu, Promotions, Settings (feature-gated)
# ============================================================

def venue_has_feature(feature_key):
    """Decorator: block access if venue doesn't have the feature."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            admin = get_current_admin()
            if admin and admin.venue and not admin.venue.has_feature(feature_key):
                flash('This feature is not available on your plan')
                return redirect(url_for('bo_bp.dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator


@bo_bp.route('/menu')
@login_required
@email_verified_required
def menu_list():
    admin = get_current_admin()
    venue = admin.venue
    if venue:
        categories = Category.query.filter_by(venue_id=venue.id).all()
        cat_ids = [c.CategoryID for c in categories]
        cat_id = request.args.get('category', type=int)
        if cat_id and cat_id in cat_ids:
            items = FoodItem.query.filter_by(CategoryID=cat_id).all()
        else:
            items = FoodItem.query.filter(FoodItem.CategoryID.in_(cat_ids)).all() if cat_ids else []
            cat_id = None
        item_counts = {cid: FoodItem.query.filter_by(CategoryID=cid).count() for cid in cat_ids}
        subs_raw = Subcategory.query.filter(Subcategory.CategoryID.in_(cat_ids)).all() if cat_ids else []
        subs_by_cat = {}
        for s in subs_raw:
            subs_by_cat.setdefault(s.CategoryID, []).append(s)
    else:
        categories = Category.query.all()
        cat_id = request.args.get('category', type=int)
        items = FoodItem.query.filter_by(CategoryID=cat_id).all() if cat_id else FoodItem.query.all()
        item_counts = {}
        subs_by_cat = {}

    features = venue.get_all_features() if venue else {}
    return render_template('backoffice/menu.html', admin=admin, categories=categories,
                           items=items, selected_cat=cat_id, features=features,
                           item_counts=item_counts, subs_by_cat=subs_by_cat)


@bo_bp.route('/menu/import-photos', methods=['GET'])
@login_required
@email_verified_required
def photo_import_page():
    admin = get_current_admin()
    return render_template('backoffice/photo_import.html', admin=admin, venue=admin.venue)


@bo_bp.route('/menu/analyze-photos', methods=['POST'])
@login_required
@email_verified_required
def analyze_photos():
    import tempfile, os, shutil
    admin = get_current_admin()
    if not admin.venue:
        return jsonify(error='no venue'), 400

    files = request.files.getlist('photos')
    if not files or len(files) == 0:
        return jsonify(error='ფოტოები არ არის'), 400
    if len(files) > 15:
        return jsonify(error='მაქსიმუმ 15 ფოტო'), 400

    tmpdir = tempfile.mkdtemp(prefix='photo_import_')
    try:
        from app.scraper.ai_analyzer import (
            analyze_menu_photo_structured, enrich_missing_ingredients,
            assign_global_categories, translate_items_bilingual
        )
        from app.models import GlobalItem, GlobalCategory, GlobalSubcategory
        from sqlalchemy import func

        all_items = []
        for f in files:
            if not f or not f.filename:
                continue
            ext = f.filename.rsplit('.', 1)[-1].lower()
            if ext not in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
                continue
            path = os.path.join(tmpdir, secure_filename(f.filename))
            f.save(path)
            items = analyze_menu_photo_structured(path)
            all_items.extend(items)

        if not all_items:
            return jsonify(error='AI-მ კერძები ვერ ამოიღო. სცადეთ სხვა ფოტო.')

        # Deduplicate by name (case-insensitive)
        seen = {}
        deduped = []
        for it in all_items:
            k = it['name'].lower().strip()
            if k not in seen:
                seen[k] = it
                deduped.append(it)
            else:
                existing = seen[k]
                if not existing.get('price') and it.get('price'):
                    existing['price'] = it['price']
                if not existing.get('ingredients') and it.get('ingredients'):
                    existing['ingredients'] = it['ingredients']
                if not existing.get('subcategory') and it.get('subcategory'):
                    existing['subcategory'] = it['subcategory']

        # Step 1: Assign categories/subcategories from GlobalLibrary
        global_cats = [{'id': c.id, 'name': c.name} for c in GlobalCategory.query.filter_by(is_active=True).all()]
        global_subcats = [{'id': s.id, 'name': s.name, 'category_id': s.category_id}
                          for s in GlobalSubcategory.query.filter_by(is_active=True).all()]
        if global_cats:
            assign_global_categories(deduped, global_cats, global_subcats)

        # Step 2: Enrich missing ingredients via AI
        enrich_missing_ingredients(deduped)

        # Step 3: Translate to both Georgian and English
        translate_items_bilingual(deduped)

        # Step 4: Match library photos by item name
        for it in deduped:
            name = it['name'].strip()
            lib = (GlobalItem.query
                   .filter(func.lower(GlobalItem.name) == name.lower())
                   .filter(GlobalItem.image_filename.isnot(None))
                   .first())
            if not lib:
                lib = (GlobalItem.query
                       .filter(GlobalItem.name.ilike(f'%{name}%'))
                       .filter(GlobalItem.image_filename.isnot(None))
                       .first())
            it['library_photo'] = lib.image_filename if lib else None

        # Category icon from GlobalCategory (already matched above)
        cat_icons = {}
        for c in global_cats:
            gc = GlobalCategory.query.get(c['id'])
            if gc:
                cat_icons[gc.name] = gc.icon

        # Organise: {category: {subcategory: [items]}}
        organised = {}
        cats_en = {}
        for it in deduped:
            cat = it.get('category') or 'სხვა'
            sub = it.get('subcategory') or ''
            organised.setdefault(cat, {}).setdefault(sub, []).append(it)
            if cat not in cats_en and it.get('category_en'):
                cats_en[cat] = it['category_en']

        return jsonify(
            success=True,
            total=len(deduped),
            categories=organised,
            cat_icons=cat_icons,
            cats_en=cats_en,
        )
    except Exception as e:
        current_app.logger.exception('analyze_photos error')
        return jsonify(error=str(e)), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@bo_bp.route('/menu/import-analyzed', methods=['POST'])
@login_required
@email_verified_required
def import_analyzed():
    admin = get_current_admin()
    if not admin.venue:
        return jsonify(error='no venue'), 400
    venue_id = admin.venue.id
    data = request.get_json() or {}
    categories_data = data.get('categories', {})
    cats_en = data.get('cats_en', {})

    imported_cats = 0
    imported_subs = 0
    imported_items = 0

    for cat_name, subcats in categories_data.items():
        cat_name = (cat_name or '').strip()
        if not cat_name:
            continue
        cat = Category.query.filter_by(venue_id=venue_id, CategoryName=cat_name).first()
        if not cat:
            cat_name_en = (cats_en.get(cat_name) or '').strip() or None
            cat = Category(CategoryName=cat_name, CategoryName_en=cat_name_en, venue_id=venue_id)
            db.session.add(cat)
            db.session.flush()
            imported_cats += 1

        for sub_name, items in subcats.items():
            sub_name = (sub_name or '').strip()
            sub = None
            if sub_name:
                sub = Subcategory.query.filter_by(CategoryID=cat.CategoryID, SubcategoryName=sub_name).first()
                if not sub:
                    sub = Subcategory(SubcategoryName=sub_name, CategoryID=cat.CategoryID)
                    db.session.add(sub)
                    db.session.flush()
                    imported_subs += 1

            for item_data in items:
                if item_data.get('excluded'):
                    continue
                name = (item_data.get('name_ka') or item_data.get('name') or '').strip()
                if not name:
                    continue
                if FoodItem.query.filter_by(CategoryID=cat.CategoryID, FoodName=name).first():
                    continue
                name_en = (item_data.get('name_en') or name).strip()
                try:
                    price = float(item_data.get('price') or 0)
                except (ValueError, TypeError):
                    price = 0.0
                photo = item_data.get('library_photo') or None
                food = FoodItem(
                    FoodName=name,
                    FoodName_en=name_en,
                    Description='',
                    Ingredients=(item_data.get('ingredients_ka') or item_data.get('ingredients') or '').strip(),
                    Ingredients_en=(item_data.get('ingredients_en') or '').strip(),
                    Price=price,
                    ImageFilename=photo,
                    CategoryID=cat.CategoryID,
                    SubcategoryID=sub.SubcategoryID if sub else None,
                )
                db.session.add(food)
                imported_items += 1

    db.session.commit()
    return jsonify(
        success=True,
        imported_items=imported_items,
        imported_categories=imported_cats,
        imported_subcategories=imported_subs,
    )


@bo_bp.route('/menu/toggle-customization/<int:item_id>', methods=['POST'])
@login_required
@email_verified_required
def toggle_customization(item_id):
    item = verify_item_ownership(item_id)
    if not item:
        return jsonify(success=False, error='Access denied'), 403
    item.allow_customization = not item.allow_customization
    db.session.commit()
    return jsonify(success=True, allow_customization=item.allow_customization)


@bo_bp.route('/menu/toggle-active/<int:item_id>', methods=['POST'])
@login_required
@email_verified_required
def toggle_item_active(item_id):
    item = verify_item_ownership(item_id)
    if not item:
        return jsonify(success=False, error='Access denied'), 403
    item.is_active = not item.is_active
    db.session.commit()
    return jsonify(success=True, is_active=item.is_active)


@bo_bp.route('/menu/add', methods=['GET', 'POST'])
@login_required
@email_verified_required
def add_item():
    admin = get_current_admin()
    venue = admin.venue
    categories = Category.query.filter_by(venue_id=venue.id).all() if venue else Category.query.all()
    subcategories = Subcategory.query.all()
    features = venue.get_all_features() if venue else {}
    preselect_cat = request.args.get('cat', type=int)

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip()
        description = request.form.get('description', '').strip()
        description_en = request.form.get('description_en', '').strip()
        ingredients = request.form.get('ingredients', '').strip()
        ingredients_en = request.form.get('ingredients_en', '').strip()
        price = request.form.get('price', type=float)
        cat_id = request.form.get('category_id', type=int)
        sub_id = request.form.get('subcategory_id', type=int) or None
        allow_custom = 'allow_customization' in request.form

        if not name or not price or not cat_id:
            flash('Name, price and category are required')
            return redirect(url_for('bo_bp.add_item'))

        # Check item limit
        if venue and venue.item_count() >= MAX_ITEMS_PER_VENUE:
            flash(f'Item limit reached ({MAX_ITEMS_PER_VENUE}). Cannot add more items.')
            return redirect(url_for('bo_bp.menu_list'))

        image_filename = 'default-image.png'
        file = request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'images')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            image_filename = filename

        item = FoodItem(FoodName=name, FoodName_en=name_en or None,
                        Description=description or name, Description_en=description_en or None,
                        Ingredients=ingredients, Ingredients_en=ingredients_en or None,
                        Price=price, ImageFilename=image_filename, CategoryID=cat_id,
                        SubcategoryID=sub_id, allow_customization=allow_custom, is_active=True)
        db.session.add(item)
        db.session.commit()

        # Auto-translate missing language field via Gemini
        _trigger_item_translation(item, name, name_en, description, description_en,
                                   ingredients, ingredients_en)

        flash(f'"{name}" დაემატა')
        if request.form.get('add_another'):
            return redirect(url_for('bo_bp.add_item', cat=cat_id))
        return redirect(url_for('bo_bp.menu_list', category=cat_id))

    return render_template('backoffice/item_form.html', admin=admin, categories=categories,
                           subcategories=subcategories, item=None, title='Add Item',
                           features=features, preselect_cat=preselect_cat)


@bo_bp.route('/menu/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@email_verified_required
def edit_item(item_id):
    admin = get_current_admin()
    venue = admin.venue
    item = verify_item_ownership(item_id)
    if not item:
        flash('Access denied')
        return redirect(url_for('bo_bp.menu_list'))
    categories = Category.query.filter_by(venue_id=venue.id).all() if venue else Category.query.all()
    subcategories = Subcategory.query.all()
    features = venue.get_all_features() if venue else {}

    if request.method == 'POST':
        item.FoodName = request.form.get('name', '').strip() or item.FoodName
        item.FoodName_en = request.form.get('name_en', '').strip() or None
        item.Description = request.form.get('description', '').strip() or item.Description
        item.Description_en = request.form.get('description_en', '').strip() or None
        item.Ingredients = request.form.get('ingredients', '').strip()
        item.Ingredients_en = request.form.get('ingredients_en', '').strip() or None
        item.Price = request.form.get('price', type=float) or item.Price
        item.CategoryID = request.form.get('category_id', type=int) or item.CategoryID
        item.SubcategoryID = request.form.get('subcategory_id', type=int) or None
        item.allow_customization = 'allow_customization' in request.form

        file = request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'images')
            file.save(os.path.join(upload_dir, filename))
            item.ImageFilename = filename
        elif request.form.get('remove_image') == '1':
            item.ImageFilename = 'default-image.png'

        db.session.commit()

        # Auto-translate missing language field via Gemini
        _trigger_item_translation(item, item.FoodName, item.FoodName_en,
                                   item.Description, item.Description_en,
                                   item.Ingredients, item.Ingredients_en)

        flash(f'"{item.FoodName}" განახლდა')
        return redirect(url_for('bo_bp.menu_list', category=item.CategoryID))

    return render_template('backoffice/item_form.html', admin=admin, categories=categories,
                           subcategories=subcategories, item=item, title='Edit Item',
                           features=features, preselect_cat=None)


@bo_bp.route('/menu/delete/<int:item_id>', methods=['POST'])
@login_required
@email_verified_required
def delete_item(item_id):
    item = verify_item_ownership(item_id)
    if not item:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, error='Access denied'), 403
        flash('Access denied')
        return redirect(url_for('bo_bp.menu_list'))
    name = item.FoodName
    db.session.delete(item)
    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=True)
    flash(f'"{name}" deleted')
    return redirect(url_for('bo_bp.menu_list'))


@bo_bp.route('/menu/delete-category-items/<int:cat_id>', methods=['POST'])
@login_required
@email_verified_required
def delete_category_items(cat_id):
    cat = verify_category_ownership(cat_id)
    if not cat:
        return jsonify(success=False, error='Access denied'), 403
    deleted = FoodItem.query.filter_by(CategoryID=cat_id).delete()
    db.session.commit()
    return jsonify(success=True, deleted=deleted)


@bo_bp.route('/menu/delete-all-items', methods=['POST'])
@login_required
@email_verified_required
def delete_all_items():
    admin = get_current_admin()
    venue = admin.venue
    if not venue:
        return jsonify(success=False, error='Access denied'), 403
    cats = Category.query.filter_by(venue_id=venue.id).all()
    cat_ids = [c.CategoryID for c in cats]
    deleted = FoodItem.query.filter(FoodItem.CategoryID.in_(cat_ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify(success=True, deleted=deleted)


@bo_bp.route('/promotions')
@login_required
@venue_has_feature('promotions')
def promotions_list():
    admin = get_current_admin()
    venue = admin.venue
    promos = Promotion.query.filter_by(venue_id=venue.id).all() if venue else Promotion.query.all()
    return render_template('backoffice/promotions.html', admin=admin, promotions=promos)


@bo_bp.route('/promotions/toggle/<int:promo_id>', methods=['POST'])
@login_required
def toggle_promotion(promo_id):
    promo = verify_promo_ownership(promo_id)
    if not promo:
        return jsonify(success=False, error='Access denied'), 403
    promo.is_active = not promo.is_active
    db.session.commit()
    return jsonify(success=True, is_active=promo.is_active)


@bo_bp.route('/api/stats')
@login_required
def api_stats():
    admin = get_current_admin()
    venue = admin.venue
    if venue:
        items = FoodItem.query.join(Category).filter(Category.venue_id == venue.id).count()
        promos = Promotion.query.filter_by(venue_id=venue.id).count()
        cats = Category.query.filter_by(venue_id=venue.id).count()
    else:
        items = FoodItem.query.count()
        promos = Promotion.query.count()
        cats = Category.query.count()
    return jsonify(items=items, promos=promos, categories=cats)


@bo_bp.route('/api/subcategories/<int:category_id>')
@login_required
def api_subcategories(category_id):
    admin = get_current_admin()
    if admin and admin.venue:
        cat = Category.query.filter_by(CategoryID=category_id, venue_id=admin.venue.id).first()
        if not cat:
            return jsonify([])
    subs = Subcategory.query.filter_by(CategoryID=category_id).all()
    return jsonify([{'id': s.SubcategoryID, 'name': s.SubcategoryName} for s in subs])


# ============================================================
# Category & Subcategory CRUD
# ============================================================

@bo_bp.route('/categories')
@login_required
@email_verified_required
def categories_list():
    admin = get_current_admin()
    venue = admin.venue
    categories = Category.query.filter_by(venue_id=venue.id).all() if venue else Category.query.all()
    return render_template('backoffice/categories.html', admin=admin, categories=categories)


@bo_bp.route('/categories/add', methods=['GET', 'POST'])
@login_required
@email_verified_required
def add_category():
    admin = get_current_admin()
    venue = admin.venue

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        name_en = request.form.get('name_en', '').strip()
        description = request.form.get('description', '').strip()
        description_en = request.form.get('description_en', '').strip()

        if not name:
            flash('Category name is required')
            return redirect(url_for('bo_bp.add_category'))

        icon_filename = None
        file = request.files.get('icon')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'categories')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            icon_filename = filename

        cat = Category(CategoryName=name, CategoryName_en=name_en or None,
                       Description=description, Description_en=description_en or None,
                       CategoryIcon=icon_filename, venue_id=venue.id if venue else None)
        db.session.add(cat)
        db.session.commit()

        if needs_translation(name, name_en):
            translate_category_async(cat.CategoryID,
                                     {'name': name, 'description': description},
                                     'ka', 'en', current_app._get_current_object())
        elif needs_translation(name_en, name):
            translate_category_async(cat.CategoryID,
                                     {'name': name_en, 'description': description_en},
                                     'en', 'ka', current_app._get_current_object())

        flash(f'Category "{name}" created')
        return redirect(url_for('bo_bp.categories_list'))

    return render_template('backoffice/category_form.html', admin=admin, category=None, title='Add Category')


@bo_bp.route('/categories/edit/<int:cat_id>', methods=['GET', 'POST'])
@login_required
@email_verified_required
def edit_category(cat_id):
    admin = get_current_admin()
    cat = verify_category_ownership(cat_id)
    if not cat:
        flash('Access denied')
        return redirect(url_for('bo_bp.categories_list'))

    if request.method == 'POST':
        cat.CategoryName = request.form.get('name', '').strip() or cat.CategoryName
        cat.CategoryName_en = request.form.get('name_en', '').strip() or None
        cat.Description = request.form.get('description', '').strip()
        cat.Description_en = request.form.get('description_en', '').strip() or None

        file = request.files.get('icon')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'categories')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            cat.CategoryIcon = filename

        db.session.commit()

        if needs_translation(cat.CategoryName, cat.CategoryName_en):
            translate_category_async(cat.CategoryID,
                                     {'name': cat.CategoryName, 'description': cat.Description or ''},
                                     'ka', 'en', current_app._get_current_object())
        elif needs_translation(cat.CategoryName_en, cat.CategoryName):
            translate_category_async(cat.CategoryID,
                                     {'name': cat.CategoryName_en, 'description': cat.Description_en or ''},
                                     'en', 'ka', current_app._get_current_object())

        flash(f'Category "{cat.CategoryName}" updated')
        return redirect(url_for('bo_bp.categories_list'))

    return render_template('backoffice/category_form.html', admin=admin, category=cat, title='Edit Category')


@bo_bp.route('/categories/delete/<int:cat_id>', methods=['POST'])
@login_required
@email_verified_required
def delete_category(cat_id):
    cat = verify_category_ownership(cat_id)
    if not cat:
        flash('Access denied')
        return redirect(url_for('bo_bp.categories_list'))
    # Check if category has items
    items_count = FoodItem.query.filter_by(CategoryID=cat.CategoryID).count()
    if items_count > 0:
        flash(f'Cannot delete "{cat.CategoryName}" — it has {items_count} items. Remove items first.')
        return redirect(url_for('bo_bp.categories_list'))

    name = cat.CategoryName
    # Unlink items from subcategories, then delete subcategories
    FoodItem.query.filter_by(CategoryID=cat.CategoryID).update({'SubcategoryID': None})
    Subcategory.query.filter_by(CategoryID=cat.CategoryID).delete()
    db.session.delete(cat)
    db.session.commit()
    flash(f'Category "{name}" deleted')
    return redirect(url_for('bo_bp.categories_list'))


@bo_bp.route('/categories/<int:cat_id>/subcategories/add', methods=['POST'])
@login_required
@email_verified_required
def add_subcategory(cat_id):
    cat = verify_category_ownership(cat_id)
    if not cat:
        flash('Access denied')
        return redirect(url_for('bo_bp.categories_list'))
    name = request.form.get('name', '').strip()
    if name:
        sub = Subcategory(SubcategoryName=name, CategoryID=cat.CategoryID)
        db.session.add(sub)
        db.session.commit()
        flash(f'Subcategory "{name}" added')
    return redirect(url_for('bo_bp.categories_list'))


@bo_bp.route('/subcategories/delete/<int:sub_id>', methods=['POST'])
@login_required
@email_verified_required
def delete_subcategory(sub_id):
    sub = Subcategory.query.get_or_404(sub_id)
    # Verify ownership via parent category
    cat = verify_category_ownership(sub.CategoryID)
    if not cat:
        flash('Access denied')
        return redirect(url_for('bo_bp.categories_list'))
    # Unlink items from this subcategory
    FoodItem.query.filter_by(SubcategoryID=sub.SubcategoryID).update({'SubcategoryID': None})
    name = sub.SubcategoryName
    db.session.delete(sub)
    db.session.commit()
    flash(f'Subcategory "{name}" deleted')
    return redirect(url_for('bo_bp.categories_list'))


# ── JSON endpoints for unified menu management ──────────────

@bo_bp.route('/categories/add-json', methods=['POST'])
@login_required
@email_verified_required
def add_category_json():
    admin = get_current_admin()
    venue = admin.venue
    data = request.get_json() or request.form
    name = (data.get('name') or '').strip()
    name_en = (data.get('name_en') or '').strip()
    if not name:
        return jsonify(success=False, error='სახელი სავალდებულოა'), 400
    cat = Category(CategoryName=name, CategoryName_en=name_en or None,
                   venue_id=venue.id if venue else None)
    db.session.add(cat)
    db.session.commit()
    if needs_translation(name, name_en):
        translate_category_async(cat.CategoryID, {'name': name, 'description': ''},
                                 'ka', 'en', current_app._get_current_object())
    elif needs_translation(name_en, name):
        translate_category_async(cat.CategoryID, {'name': name_en, 'description': ''},
                                 'en', 'ka', current_app._get_current_object())
    return jsonify(success=True, id=cat.CategoryID, name=cat.CategoryName,
                   name_en=cat.CategoryName_en or '')


@bo_bp.route('/categories/edit-json/<int:cat_id>', methods=['POST'])
@login_required
@email_verified_required
def edit_category_json(cat_id):
    cat = verify_category_ownership(cat_id)
    if not cat:
        return jsonify(success=False, error='Access denied'), 403
    data = request.get_json() or request.form
    name = (data.get('name') or '').strip()
    name_en = (data.get('name_en') or '').strip()
    if not name:
        return jsonify(success=False, error='სახელი სავალდებულოა'), 400
    cat.CategoryName = name
    cat.CategoryName_en = name_en or None
    db.session.commit()
    return jsonify(success=True, id=cat.CategoryID, name=cat.CategoryName,
                   name_en=cat.CategoryName_en or '')


@bo_bp.route('/categories/delete-json/<int:cat_id>', methods=['POST'])
@login_required
@email_verified_required
def delete_category_json(cat_id):
    cat = verify_category_ownership(cat_id)
    if not cat:
        return jsonify(success=False, error='Access denied'), 403
    count = FoodItem.query.filter_by(CategoryID=cat.CategoryID).count()
    if count > 0:
        return jsonify(success=False,
                       error=f'კატეგორიაში {count} ნივთია. წაშლამდე ამოიღეთ ნივთები.'), 400
    Subcategory.query.filter_by(CategoryID=cat.CategoryID).delete()
    db.session.delete(cat)
    db.session.commit()
    return jsonify(success=True)


@bo_bp.route('/categories/<int:cat_id>/subcategories/add-json', methods=['POST'])
@login_required
@email_verified_required
def add_subcategory_json(cat_id):
    cat = verify_category_ownership(cat_id)
    if not cat:
        return jsonify(success=False, error='Access denied'), 403
    data = request.get_json() or request.form
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(success=False, error='სახელი სავალდებულოა'), 400
    sub = Subcategory(SubcategoryName=name, CategoryID=cat.CategoryID)
    db.session.add(sub)
    db.session.commit()
    return jsonify(success=True, id=sub.SubcategoryID, name=sub.SubcategoryName)


@bo_bp.route('/subcategories/delete-json/<int:sub_id>', methods=['POST'])
@login_required
@email_verified_required
def delete_subcategory_json(sub_id):
    sub = Subcategory.query.get_or_404(sub_id)
    cat = verify_category_ownership(sub.CategoryID)
    if not cat:
        return jsonify(success=False, error='Access denied'), 403
    FoodItem.query.filter_by(SubcategoryID=sub.SubcategoryID).update({'SubcategoryID': None})
    db.session.delete(sub)
    db.session.commit()
    return jsonify(success=True)


@bo_bp.route('/menu/copy/<int:item_id>', methods=['POST'])
@login_required
@email_verified_required
def copy_item(item_id):
    item = verify_item_ownership(item_id)
    if not item:
        return jsonify(success=False, error='Access denied'), 403
    admin = get_current_admin()
    venue = admin.venue
    if venue and venue.item_count() >= MAX_ITEMS_PER_VENUE:
        return jsonify(success=False, error=f'ლიმიტი ({MAX_ITEMS_PER_VENUE}) ამოიწურა'), 400
    new_item = FoodItem(
        FoodName=item.FoodName + ' (ასლი)',
        FoodName_en=(item.FoodName_en + ' (copy)') if item.FoodName_en else None,
        Description=item.Description,
        Description_en=item.Description_en,
        Ingredients=item.Ingredients,
        Ingredients_en=item.Ingredients_en,
        Price=item.Price,
        CategoryID=item.CategoryID,
        SubcategoryID=item.SubcategoryID,
        ImageFilename=item.ImageFilename,
        is_active=False,
        allow_customization=item.allow_customization,
    )
    db.session.add(new_item)
    db.session.commit()
    return jsonify(success=True,
                   redirect=url_for('bo_bp.menu_list', category=item.CategoryID))


# ============================================================
# Reservation Management (Admin)
# ============================================================

from app.models import RestaurantTable, Booking, ReservationSettings, BOOKING_STATUSES
from app.services.reservation_service import ReservationService


@bo_bp.route('/reservations')
@login_required
@venue_has_feature('reservations')
def reservations_list():
    admin = get_current_admin()
    venue = admin.venue
    filters = {
        'date': request.args.get('date'),
        'status': request.args.get('status'),
        'table_id': request.args.get('table_id', type=int),
    }
    bookings = ReservationService.get_bookings_for_venue(venue.id, filters)
    tables = RestaurantTable.query.filter_by(venue_id=venue.id, is_active=True).all()
    return render_template('backoffice/reservation_bookings.html', admin=admin,
                           bookings=bookings, tables=tables, filters=filters, statuses=BOOKING_STATUSES)


@bo_bp.route('/reservations/<int:booking_id>/cancel', methods=['POST'])
@login_required
@venue_has_feature('reservations')
def admin_cancel_booking(booking_id):
    admin = get_current_admin()
    booking = Booking.query.filter_by(id=booking_id, venue_id=admin.venue.id).first_or_404()
    try:
        ReservationService.cancel_booking(booking_id, cancelled_by='admin')
        flash(f'Booking #{booking_id} cancelled')
    except ValueError as e:
        flash(str(e))
    return redirect(url_for('bo_bp.reservations_list'))


@bo_bp.route('/reservations/layout')
@login_required
@venue_has_feature('reservations')
def reservation_layout():
    admin = get_current_admin()
    return render_template('backoffice/reservation_layout.html', admin=admin)


@bo_bp.route('/api/reservations/layout', methods=['GET'])
@login_required
@venue_has_feature('reservations')
def get_layout():
    admin = get_current_admin()
    venue = admin.venue
    settings = ReservationSettings.query.filter_by(venue_id=venue.id).first()
    layout = settings.floor_layout if settings else None
    tables = RestaurantTable.query.filter_by(venue_id=venue.id, is_active=True).all()
    return jsonify(
        layout=layout,
        tables=[{
            'id': t.id, 'label': t.label, 'shape': t.shape, 'capacity': t.capacity,
            'pos_x': t.pos_x, 'pos_y': t.pos_y, 'width': t.width, 'height': t.height,
            'is_active': t.is_active,
        } for t in tables]
    )


@bo_bp.route('/api/reservations/layout', methods=['PUT'])
@login_required
@venue_has_feature('reservations')
def save_layout():
    admin = get_current_admin()
    venue = admin.venue
    data = request.get_json() or {}
    tables_data = data.get('tables', [])

    # Get existing table IDs for this venue
    existing_tables = {t.id: t for t in RestaurantTable.query.filter_by(venue_id=venue.id).all()}
    incoming_ids = set()

    for td in tables_data:
        tid = td.get('id')
        # Try to match as integer ID from DB
        try:
            tid_int = int(tid) if tid and not str(tid).startswith('new_') else None
        except (ValueError, TypeError):
            tid_int = None

        if tid_int and tid_int in existing_tables:
            table = existing_tables[tid_int]
            table.label = td.get('label', table.label)
            table.shape = td.get('shape', table.shape)
            table.capacity = td.get('capacity', table.capacity)
            table.pos_x = td.get('pos_x', table.pos_x)
            table.pos_y = td.get('pos_y', table.pos_y)
            table.width = td.get('width', table.width)
            table.height = td.get('height', table.height)
            incoming_ids.add(tid_int)
        else:
            table = RestaurantTable(
                venue_id=venue.id, label=td.get('label', 'T'),
                shape=td.get('shape', 'circle'), capacity=td.get('capacity', 4),
                pos_x=td.get('pos_x', 0), pos_y=td.get('pos_y', 0),
                width=td.get('width', 60), height=td.get('height', 60),
            )
            db.session.add(table)

    # Delete tables that were removed from layout
    for tid, table in existing_tables.items():
        if tid not in incoming_ids:
            # Check for ANY bookings (Postgres FK constraint)
            booking_count = Booking.query.filter_by(table_id=tid).count()
            if booking_count == 0:
                db.session.delete(table)
            else:
                # Deactivate instead of delete
                table.is_active = False

    # Save layout JSON to settings
    settings = ReservationSettings.query.filter_by(venue_id=venue.id).first()
    if not settings:
        settings = ReservationSettings(venue_id=venue.id)
        db.session.add(settings)
    settings.floor_layout = data.get('layout')

    db.session.commit()
    return jsonify(success=True)


@bo_bp.route('/reservations/settings', methods=['GET', 'POST'])
@login_required
@venue_has_feature('reservations')
def reservation_settings():
    admin = get_current_admin()
    venue = admin.venue
    settings = ReservationSettings.query.filter_by(venue_id=venue.id).first()
    if not settings:
        settings = ReservationSettings(venue_id=venue.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        settings.deposit_amount = request.form.get('deposit_amount', type=float) or 0.0
        slots_str = request.form.get('time_slots', '')
        settings.time_slots = [s.strip() for s in slots_str.split(',') if s.strip()]
        settings.max_advance_days = request.form.get('max_advance_days', type=int) or 30
        db.session.commit()
        flash('Reservation settings saved')
        return redirect(url_for('bo_bp.reservation_settings'))

    return render_template('backoffice/reservation_settings.html', admin=admin, settings=settings)


# ============================================================
# Venue Settings (general)
# ============================================================

@bo_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@email_verified_required
def venue_settings():
    admin = get_current_admin()
    venue = admin.venue
    if not venue:
        flash('No venue assigned')
        return redirect(url_for('bo_bp.dashboard'))

    if request.method == 'POST':
        total_tables = request.form.get('total_tables', type=int)
        if total_tables is not None and total_tables >= 0:
            venue.total_tables = total_tables
            db.session.commit()
            flash(f'Settings saved — {total_tables} tables configured')
        else:
            flash('Invalid value')
        return redirect(url_for('bo_bp.venue_settings'))

    return render_template('backoffice/venue_settings.html', admin=admin, venue=venue)
