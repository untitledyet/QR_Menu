import os
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app import db
from app.models import (AdminUser, Venue, VenueFeatureOverride, Category, Subcategory,
                         FoodItem, Promotion, Order, PLAN_FEATURES, FEATURE_LIST,
                         MAX_ITEMS_PER_VENUE)

bo_bp = Blueprint('bo_bp', __name__, url_prefix='/backoffice')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('bo_bp.login'))
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


# ============================================================
# Auth
# ============================================================

@bo_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        admin = AdminUser.query.filter_by(username=request.form.get('username', '').strip()).first()
        if admin and admin.check_password(request.form.get('password', '')):
            session['admin_id'] = admin.id
            return redirect(url_for('bo_bp.dashboard'))
        flash('Invalid credentials')
    return render_template('backoffice/login.html')

@bo_bp.route('/logout')
def logout():
    session.pop('admin_id', None)
    return redirect(url_for('bo_bp.login'))


# ============================================================
# Dashboard
# ============================================================

@bo_bp.route('/')
@login_required
def dashboard():
    admin = get_current_admin()
    if admin.is_super:
        venues = Venue.query.all()
        total_items = FoodItem.query.count()
        total_orders = Order.query.count()
        return render_template('backoffice/super_dashboard.html', admin=admin,
                               venues=venues, total_items=total_items, total_orders=total_orders)
    else:
        venue = admin.venue
        features = venue.get_all_features() if venue else {}
        return render_template('backoffice/dashboard.html', admin=admin, venue=venue, features=features)


# ============================================================
# Super Admin — Venue Management
# ============================================================

@bo_bp.route('/venues')
@login_required
@super_required
def venues_list():
    admin = get_current_admin()
    venues = Venue.query.all()
    return render_template('backoffice/super_venues.html', admin=admin, venues=venues)


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
                           feature_list=FEATURE_LIST, plans=list(PLAN_FEATURES.keys()))


@bo_bp.route('/venues/<int:venue_id>/toggle-active', methods=['POST'])
@login_required
@super_required
def toggle_venue_active(venue_id):
    venue = Venue.query.get_or_404(venue_id)
    venue.is_active = not venue.is_active
    db.session.commit()
    return jsonify(success=True, is_active=venue.is_active)


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
    else:
        categories = Category.query.all()
        cat_id = request.args.get('category', type=int)
        items = FoodItem.query.filter_by(CategoryID=cat_id).all() if cat_id else FoodItem.query.all()

    features = venue.get_all_features() if venue else {}
    return render_template('backoffice/menu.html', admin=admin, categories=categories,
                           items=items, selected_cat=cat_id, features=features)


@bo_bp.route('/menu/toggle-customization/<int:item_id>', methods=['POST'])
@login_required
def toggle_customization(item_id):
    item = FoodItem.query.get_or_404(item_id)
    item.allow_customization = not item.allow_customization
    db.session.commit()
    return jsonify(success=True, allow_customization=item.allow_customization)


@bo_bp.route('/menu/toggle-active/<int:item_id>', methods=['POST'])
@login_required
def toggle_item_active(item_id):
    item = FoodItem.query.get_or_404(item_id)
    item.is_active = not item.is_active
    db.session.commit()
    return jsonify(success=True, is_active=item.is_active)


@bo_bp.route('/menu/add', methods=['GET', 'POST'])
@login_required
def add_item():
    admin = get_current_admin()
    venue = admin.venue
    categories = Category.query.filter_by(venue_id=venue.id).all() if venue else Category.query.all()
    subcategories = Subcategory.query.all()
    features = venue.get_all_features() if venue else {}

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        ingredients = request.form.get('ingredients', '').strip()
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

        item = FoodItem(FoodName=name, Description=description or name, Ingredients=ingredients,
                        Price=price, ImageFilename=image_filename, CategoryID=cat_id,
                        SubcategoryID=sub_id, allow_customization=allow_custom, is_active=True)
        db.session.add(item)
        db.session.commit()
        flash(f'"{name}" added')
        return redirect(url_for('bo_bp.menu_list'))

    return render_template('backoffice/item_form.html', admin=admin, categories=categories,
                           subcategories=subcategories, item=None, title='Add Item', features=features)


@bo_bp.route('/menu/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    admin = get_current_admin()
    venue = admin.venue
    item = FoodItem.query.get_or_404(item_id)
    categories = Category.query.filter_by(venue_id=venue.id).all() if venue else Category.query.all()
    subcategories = Subcategory.query.all()
    features = venue.get_all_features() if venue else {}

    if request.method == 'POST':
        item.FoodName = request.form.get('name', '').strip() or item.FoodName
        item.Description = request.form.get('description', '').strip() or item.Description
        item.Ingredients = request.form.get('ingredients', '').strip()
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

        db.session.commit()
        flash(f'"{item.FoodName}" updated')
        return redirect(url_for('bo_bp.menu_list'))

    return render_template('backoffice/item_form.html', admin=admin, categories=categories,
                           subcategories=subcategories, item=item, title='Edit Item', features=features)


@bo_bp.route('/menu/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    item = FoodItem.query.get_or_404(item_id)
    name = item.FoodName
    db.session.delete(item)
    db.session.commit()
    flash(f'"{name}" deleted')
    return redirect(url_for('bo_bp.menu_list'))


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
    promo = Promotion.query.get_or_404(promo_id)
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
    subs = Subcategory.query.filter_by(CategoryID=category_id).all()
    return jsonify([{'id': s.SubcategoryID, 'name': s.SubcategoryName} for s in subs])
