# -*- coding: utf-8 -*-
"""Chain / Group management routes.

Roles:
  - Standalone Admin : no group yet → can create or join
  - Group Owner      : admin whose venue == group.owner_venue → full management
  - Branch Admin     : admin whose venue has group_id set but is not owner → limited view
"""
import os
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import (Blueprint, render_template, request, redirect,
                   url_for, session, flash, jsonify, current_app, abort)
from app import db
from app.models import (AdminUser, Venue, Category, Subcategory, FoodItem,
                        VenueGroup, VenueGroupInvite, VenueItemPriceOverride,
                        _generate_invite_code, _generate_venue_code)
from app.routes.landing_routes import slugify, _normalize_phone
from app.routes.backoffice_routes import get_current_admin, login_required

group_bp = Blueprint('group_bp', __name__, url_prefix='/backoffice/group')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_group_context(admin):
    """Return (group, role) for current admin.

    role is 'owner', 'branch', or None.
    group is VenueGroup instance or None.
    """
    if not admin or not admin.venue or not admin.venue.group_id:
        return None, None
    group = VenueGroup.query.get(admin.venue.group_id)
    if not group:
        return None, None
    role = 'owner' if group.owner_venue_id == admin.venue.id else 'branch'
    return group, role


def owner_required(f):
    """Decorator: only the group owner may access this route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = get_current_admin()
        group, role = get_group_context(admin)
        if role != 'owner':
            flash('mxolod jaWvis mflobeli SeiZleba.')
            return redirect(url_for('group_bp.group_dashboard'))
        return f(*args, **kwargs)
    return decorated


def _expire_old_invites(group_id):
    """Mark expired pending invites as 'expired'."""
    VenueGroupInvite.query.filter_by(
        group_id=group_id, status='pending'
    ).filter(VenueGroupInvite.expires_at < datetime.utcnow()).update({'status': 'expired'})
    db.session.commit()


# ── Dashboard (entry point) ───────────────────────────────────────────────────

@group_bp.route('/')
@login_required
def group_dashboard():
    admin = get_current_admin()
    group, role = get_group_context(admin)

    if not group:
        # Standalone admin — show create / join options
        return render_template('backoffice/group_create_or_join.html', admin=admin)

    _expire_old_invites(group.id)

    if role == 'owner':
        branches = group.branch_list
        active_invites = VenueGroupInvite.query.filter_by(
            group_id=group.id, status='pending'
        ).all()
        group_cats = Category.query.filter_by(group_id=group.id, venue_id=None).all()
        return render_template('backoffice/group_dashboard.html',
                               admin=admin, group=group, role=role,
                               branches=branches, active_invites=active_invites,
                               group_cats=group_cats)
    else:
        # Branch admin
        group_cats = Category.query.filter_by(group_id=group.id, venue_id=None).all()
        return render_template('backoffice/group_branch_view.html',
                               admin=admin, group=group, role=role,
                               group_cats=group_cats)


# ── Create Group ──────────────────────────────────────────────────────────────

@group_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_group():
    admin = get_current_admin()
    group, role = get_group_context(admin)
    if group:
        flash('ukve jaWvis wevri xarT.')
        return redirect(url_for('group_bp.group_dashboard'))

    if request.method == 'POST':
        name = (request.form.get('group_name') or '').strip()
        if not name:
            flash('jaWvis saxeli savaldebuloa.')
            return redirect(url_for('group_bp.create_group'))

        venue = admin.venue
        new_group = VenueGroup(
            name=name,
            owner_venue_id=venue.id,
            allow_price_override=False,
        )
        db.session.add(new_group)
        db.session.flush()

        venue.group_id = new_group.id
        db.session.commit()

        flash(f'jaWvi "{name}" warmatebulad Seiqmna.')
        return redirect(url_for('group_bp.group_dashboard'))

    return render_template('backoffice/group_create.html', admin=admin)


# ── Join Group via Invite Code ────────────────────────────────────────────────

@group_bp.route('/join', methods=['GET', 'POST'])
@login_required
def join_group():
    admin = get_current_admin()
    group, role = get_group_context(admin)
    if group:
        flash('ukve jaWvis wevri xarT.')
        return redirect(url_for('group_bp.group_dashboard'))

    preview = None
    code = ''

    if request.method == 'POST':
        action = request.form.get('action', 'preview')
        code = (request.form.get('invite_code') or '').strip().upper()

        if not code:
            flash('invite kodi savaldebuloa.')
            return redirect(url_for('group_bp.join_group'))

        invite = VenueGroupInvite.query.filter_by(invite_code=code, status='pending').first()
        if not invite or invite.is_expired:
            flash('invite kodi arasworia an vadagasulia.')
            return redirect(url_for('group_bp.join_group'))

        if action == 'preview':
            grp = VenueGroup.query.get(invite.group_id)
            cat_count = Category.query.filter_by(group_id=grp.id, venue_id=None).count()
            item_count = FoodItem.query.join(Category).filter(
                Category.group_id == grp.id, Category.venue_id.is_(None)
            ).count()
            preview = {
                'group': grp,
                'cat_count': cat_count,
                'item_count': item_count,
                'invite': invite,
                'code': code,
            }
            return render_template('backoffice/group_join.html',
                                   admin=admin, preview=preview, code=code)

        elif action == 'confirm':
            # Re-validate
            invite = VenueGroupInvite.query.filter_by(invite_code=code, status='pending').first()
            if not invite or invite.is_expired:
                flash('invite kodi arasworia an vadagasulia.')
                return redirect(url_for('group_bp.join_group'))

            venue = admin.venue
            # Handle existing local menu
            keep_local = request.form.get('keep_local') == '1'
            if not keep_local:
                # Delete venue's own categories/items
                own_cats = Category.query.filter_by(venue_id=venue.id).all()
                for cat in own_cats:
                    Subcategory.query.filter_by(CategoryID=cat.CategoryID).delete()
                    FoodItem.query.filter_by(CategoryID=cat.CategoryID).delete()
                Category.query.filter_by(venue_id=venue.id).delete()

            venue.group_id = invite.group_id
            invite.status = 'accepted'
            db.session.commit()

            grp = VenueGroup.query.get(invite.group_id)
            flash(f'warmatebulad SeuerTdiT jaWvs "{grp.name}".')
            return redirect(url_for('group_bp.group_dashboard'))

    return render_template('backoffice/group_join.html', admin=admin, preview=None, code=code)


# ── Invite Code Management (owner) ───────────────────────────────────────────

@group_bp.route('/invite/generate', methods=['POST'])
@login_required
@owner_required
def generate_invite():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    # Generate unique invite code
    while True:
        code = _generate_invite_code()
        if not VenueGroupInvite.query.filter_by(invite_code=code).first():
            break

    invite = VenueGroupInvite(
        group_id=group.id,
        invite_code=code,
        invited_by=admin.id,
        status='pending',
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(invite)
    db.session.commit()

    return jsonify(success=True, invite_code=code,
                   expires_at=invite.expires_at.strftime('%Y-%m-%d %H:%M UTC'))


@group_bp.route('/invite/<int:invite_id>/expire', methods=['POST'])
@login_required
@owner_required
def expire_invite(invite_id):
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    invite = VenueGroupInvite.query.filter_by(id=invite_id, group_id=group.id).first_or_404()
    invite.status = 'expired'
    db.session.commit()
    return jsonify(success=True)


# ── Add New Branch Directly (owner, Scenario 2 — corporate) ──────────────────

@group_bp.route('/branch/add', methods=['GET', 'POST'])
@login_required
@owner_required
def add_branch():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    if request.method == 'POST':
        branch_name = (request.form.get('branch_name') or '').strip()
        branch_address = (request.form.get('branch_address') or '').strip()
        branch_email = (request.form.get('branch_email') or '').strip().lower()
        branch_phone = (request.form.get('branch_phone') or '').strip()

        if not branch_name or not branch_address or not branch_email:
            flash('saxeli, misamarTi da el. fosta savaldebuloa.')
            return redirect(url_for('group_bp.add_branch'))

        # Generate unique slug
        base_slug = slugify(branch_name)
        slug = base_slug
        counter = 2
        while Venue.query.filter_by(slug=slug).first():
            slug = base_slug + '-' + str(counter)
            counter += 1

        while True:
            vcode = _generate_venue_code()
            if not Venue.query.filter_by(venue_code=vcode).first():
                break

        new_venue = Venue(
            name=branch_name,
            slug=slug,
            plan='free',
            address=branch_address,
            venue_code=vcode,
            group_id=group.id,
        )
        db.session.add(new_venue)
        db.session.flush()

        # Create branch admin with a temp password
        from app.services.registration_service import generate_strong_password
        temp_pw = generate_strong_password()

        norm_phone = _normalize_phone(branch_phone) if branch_phone else None

        branch_admin = AdminUser(
            username=slug,
            email=branch_email,
            phone=norm_phone,
            role='venue',
            venue_id=new_venue.id,
            email_verified=False,
            phone_verified=(norm_phone is not None),
            is_active=True,
        )
        branch_admin.set_password(temp_pw)
        db.session.add(branch_admin)
        db.session.commit()

        flash(
            f'filiali "{branch_name}" Seiqmna. '
            f'droebiTi paroli: {temp_pw}  —  el. fostaze gagzavneT filiCalis admins.'
        )
        return redirect(url_for('group_bp.group_dashboard'))

    return render_template('backoffice/group_branch_add.html', admin=admin, group=group)


# ── Remove Branch (owner) ─────────────────────────────────────────────────────

@group_bp.route('/branch/<int:venue_id>/remove', methods=['POST'])
@login_required
@owner_required
def remove_branch(venue_id):
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    branch = Venue.query.filter_by(id=venue_id, group_id=group.id).first_or_404()
    if branch.id == group.owner_venue_id:
        return jsonify(error='mfloblis filiali ver amogaaqvT'), 400

    # Remove price overrides for this branch
    VenueItemPriceOverride.query.filter_by(venue_id=branch.id).delete()
    branch.group_id = None
    db.session.commit()
    return jsonify(success=True, message=f'"{branch.name}" amogaqviaT jaWvidan.')


# ── Leave Group (branch admin) ────────────────────────────────────────────────

@group_bp.route('/leave', methods=['POST'])
@login_required
def leave_group():
    admin = get_current_admin()
    group, role = get_group_context(admin)

    if not group:
        return jsonify(error='jaWvis wevri ar xarT'), 400
    if role == 'owner':
        return jsonify(error='mflobeli ver datovebs jaWvs. gamoiyeneT "jaWvis dagSla".'), 400

    venue = admin.venue
    VenueItemPriceOverride.query.filter_by(venue_id=venue.id).delete()
    venue.group_id = None
    db.session.commit()
    flash('jaWvi datoveT.')
    return jsonify(success=True, redirect='/backoffice/group/')


# ── Dissolve Group (owner) ────────────────────────────────────────────────────

@group_bp.route('/dissolve', methods=['POST'])
@login_required
@owner_required
def dissolve_group():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    snapshot = request.form.get('snapshot') == '1'

    if snapshot:
        # Copy group categories/items to each branch as local categories
        group_cats = Category.query.filter_by(group_id=group.id, venue_id=None).all()
        branches = group.branch_list
        for branch in branches:
            for gcat in group_cats:
                new_cat = Category(
                    CategoryName=gcat.CategoryName,
                    Description=gcat.Description,
                    CategoryIcon=gcat.CategoryIcon,
                    venue_id=branch.id,
                    group_id=None,
                )
                db.session.add(new_cat)
                db.session.flush()
                for sub in Subcategory.query.filter_by(CategoryID=gcat.CategoryID).all():
                    new_sub = Subcategory(
                        SubcategoryName=sub.SubcategoryName,
                        CategoryID=new_cat.CategoryID,
                    )
                    db.session.add(new_sub)
                db.session.flush()
                for item in FoodItem.query.filter_by(CategoryID=gcat.CategoryID).all():
                    new_item = FoodItem(
                        FoodName=item.FoodName,
                        Description=item.Description,
                        Ingredients=item.Ingredients,
                        Price=item.Price,
                        ImageFilename=item.ImageFilename,
                        CategoryID=new_cat.CategoryID,
                        allow_customization=item.allow_customization,
                        is_active=item.is_active,
                    )
                    db.session.add(new_item)

    # Detach all branches
    Venue.query.filter_by(group_id=group.id).update({'group_id': None})
    # Remove all price overrides for this group's categories
    group_cat_ids = [c.CategoryID for c in Category.query.filter_by(
        group_id=group.id, venue_id=None).all()]
    if group_cat_ids:
        item_ids = [i.FoodItemID for i in FoodItem.query.filter(
            FoodItem.CategoryID.in_(group_cat_ids)).all()]
        if item_ids:
            VenueItemPriceOverride.query.filter(
                VenueItemPriceOverride.food_item_id.in_(item_ids)
            ).delete(synchronize_session=False)
        # Delete group items and categories
        FoodItem.query.filter(FoodItem.CategoryID.in_(group_cat_ids)).delete(
            synchronize_session=False)
        Subcategory.query.filter(Subcategory.CategoryID.in_(group_cat_ids)).delete(
            synchronize_session=False)
        Category.query.filter(Category.CategoryID.in_(group_cat_ids)).delete(
            synchronize_session=False)
    # Delete invites then group
    VenueGroupInvite.query.filter_by(group_id=group.id).delete()
    db.session.delete(group)
    db.session.commit()

    flash('jaWvi dagSalilia. yvela filiali damoukideblad gaagrZelebs muSaobas.')
    return jsonify(success=True, redirect='/backoffice')


# ── Group Settings (owner) ────────────────────────────────────────────────────

@group_bp.route('/settings', methods=['POST'])
@login_required
@owner_required
def update_settings():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    allow = request.form.get('allow_price_override') == '1'
    group.allow_price_override = allow
    db.session.commit()
    return jsonify(success=True,
                   allow_price_override=group.allow_price_override)


# ── Group Menu Management (owner) ─────────────────────────────────────────────

@group_bp.route('/menu')
@login_required
@owner_required
def group_menu():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    cats = Category.query.filter_by(group_id=group.id, venue_id=None).all()
    cat_data = []
    for cat in cats:
        subs = Subcategory.query.filter_by(CategoryID=cat.CategoryID).all()
        items = FoodItem.query.filter_by(CategoryID=cat.CategoryID).all()
        cat_data.append({'cat': cat, 'subs': subs, 'items': items})

    return render_template('backoffice/group_menu.html',
                           admin=admin, group=group, cat_data=cat_data)


@group_bp.route('/menu/category/add', methods=['POST'])
@login_required
@owner_required
def add_group_category():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    name = (request.form.get('name') or '').strip()
    desc = (request.form.get('description') or '').strip()
    icon = (request.form.get('icon') or '').strip()
    if not name:
        return jsonify(error='saxeli savaldebuloa'), 400

    cat = Category(CategoryName=name, Description=desc, CategoryIcon=icon,
                   venue_id=None, group_id=group.id)
    db.session.add(cat)
    db.session.commit()
    return jsonify(success=True, category_id=cat.CategoryID, name=cat.CategoryName)


@group_bp.route('/menu/category/<int:cat_id>/delete', methods=['POST'])
@login_required
@owner_required
def delete_group_category(cat_id):
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    cat = Category.query.filter_by(CategoryID=cat_id, group_id=group.id, venue_id=None).first_or_404()
    item_ids = [i.FoodItemID for i in FoodItem.query.filter_by(CategoryID=cat_id).all()]
    if item_ids:
        VenueItemPriceOverride.query.filter(
            VenueItemPriceOverride.food_item_id.in_(item_ids)
        ).delete(synchronize_session=False)
    FoodItem.query.filter_by(CategoryID=cat_id).delete()
    Subcategory.query.filter_by(CategoryID=cat_id).delete()
    db.session.delete(cat)
    db.session.commit()
    return jsonify(success=True)


@group_bp.route('/menu/item/add', methods=['POST'])
@login_required
@owner_required
def add_group_item():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    cat_id = request.form.get('category_id', type=int)
    name = (request.form.get('name') or '').strip()
    desc = (request.form.get('description') or '').strip()
    ingredients = (request.form.get('ingredients') or '').strip()
    price_raw = request.form.get('price', '0')
    sub_id = request.form.get('subcategory_id', type=int)

    try:
        price = float(price_raw)
    except (ValueError, TypeError):
        return jsonify(error='fasi arasworia'), 400

    if not name or not cat_id:
        return jsonify(error='saxeli da kategoria savaldebuloa'), 400

    cat = Category.query.filter_by(CategoryID=cat_id, group_id=group.id, venue_id=None).first_or_404()

    # Handle image upload
    image_filename = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            image_filename = filename

    item = FoodItem(
        FoodName=name, Description=desc or '', Ingredients=ingredients or '',
        Price=price, CategoryID=cat.CategoryID,
        SubcategoryID=sub_id, ImageFilename=image_filename,
        allow_customization=True, is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(success=True, item_id=item.FoodItemID, name=item.FoodName,
                   price=item.Price)


@group_bp.route('/menu/item/<int:item_id>/edit', methods=['POST'])
@login_required
@owner_required
def edit_group_item(item_id):
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    item = FoodItem.query.get_or_404(item_id)
    # Verify item belongs to a group category
    cat = Category.query.filter_by(CategoryID=item.CategoryID,
                                   group_id=group.id, venue_id=None).first_or_404()

    item.FoodName = (request.form.get('name') or item.FoodName).strip()
    item.Description = (request.form.get('description') or '').strip()
    item.Ingredients = (request.form.get('ingredients') or '').strip()
    try:
        item.Price = float(request.form.get('price', item.Price))
    except (ValueError, TypeError):
        pass
    item.is_active = request.form.get('is_active') != '0'

    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))
            item.ImageFilename = filename

    db.session.commit()
    return jsonify(success=True, name=item.FoodName, price=item.Price)


@group_bp.route('/menu/item/<int:item_id>/delete', methods=['POST'])
@login_required
@owner_required
def delete_group_item(item_id):
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    item = FoodItem.query.get_or_404(item_id)
    Category.query.filter_by(CategoryID=item.CategoryID,
                              group_id=group.id, venue_id=None).first_or_404()

    VenueItemPriceOverride.query.filter_by(food_item_id=item.FoodItemID).delete()
    db.session.delete(item)
    db.session.commit()
    return jsonify(success=True)


# ── Subcategory management for group menu (owner) ─────────────────────────────

@group_bp.route('/menu/subcategory/add', methods=['POST'])
@login_required
@owner_required
def add_group_subcategory():
    admin = get_current_admin()
    group, _ = get_group_context(admin)

    cat_id = request.form.get('category_id', type=int)
    name = (request.form.get('name') or '').strip()
    if not cat_id or not name:
        return jsonify(error='kategoria da saxeli savaldebuloa'), 400

    Category.query.filter_by(CategoryID=cat_id, group_id=group.id,
                              venue_id=None).first_or_404()
    sub = Subcategory(SubcategoryName=name, CategoryID=cat_id)
    db.session.add(sub)
    db.session.commit()
    return jsonify(success=True, subcategory_id=sub.SubcategoryID, name=sub.SubcategoryName)


# ── Price Overrides (branch admin) ────────────────────────────────────────────

@group_bp.route('/price-overrides')
@login_required
def price_overrides():
    admin = get_current_admin()
    group, role = get_group_context(admin)

    if not group:
        flash('jaWvis wevri ar xarT.')
        return redirect(url_for('group_bp.group_dashboard'))

    if not group.allow_price_override:
        flash('jaWvis admins fasis cvlileba ar aqvs nebarTuli.')
        return redirect(url_for('group_bp.group_dashboard'))

    venue = admin.venue
    group_cats = Category.query.filter_by(group_id=group.id, venue_id=None).all()
    overrides = {ov.food_item_id: ov.price for ov in
                 VenueItemPriceOverride.query.filter_by(venue_id=venue.id).all()}

    cat_data = []
    for cat in group_cats:
        items = FoodItem.query.filter_by(CategoryID=cat.CategoryID).all()
        cat_data.append({'cat': cat, 'items': items})

    return render_template('backoffice/group_price_overrides.html',
                           admin=admin, group=group, cat_data=cat_data,
                           overrides=overrides, role=role)


@group_bp.route('/price-overrides/set', methods=['POST'])
@login_required
def set_price_override():
    admin = get_current_admin()
    group, role = get_group_context(admin)

    if not group or not group.allow_price_override:
        return jsonify(error='nebarTva ar gaqvT'), 403

    venue = admin.venue
    item_id = request.form.get('item_id', type=int)
    price_raw = request.form.get('price', '').strip()

    if not item_id:
        return jsonify(error='item_id savaldebuloa'), 400

    # Verify the item belongs to this group
    item = FoodItem.query.get_or_404(item_id)
    cat = Category.query.filter_by(CategoryID=item.CategoryID,
                                   group_id=group.id, venue_id=None).first()
    if not cat:
        return jsonify(error='kerZi am jaWvs ar ekuTvnis'), 403

    if price_raw == '' or price_raw is None:
        # Remove override
        VenueItemPriceOverride.query.filter_by(
            venue_id=venue.id, food_item_id=item_id).delete()
        db.session.commit()
        return jsonify(success=True, price=None, base_price=item.Price)

    try:
        price = float(price_raw)
        if price < 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(error='fasi arasworia'), 400

    ov = VenueItemPriceOverride.query.filter_by(
        venue_id=venue.id, food_item_id=item_id).first()
    if ov:
        ov.price = price
    else:
        ov = VenueItemPriceOverride(venue_id=venue.id, food_item_id=item_id, price=price)
        db.session.add(ov)

    db.session.commit()
    return jsonify(success=True, price=price, base_price=item.Price)


# ── Group API helpers (used by base.html nav) ─────────────────────────────────

@group_bp.context_processor
def inject_group_context():
    """Inject group/role into all group_bp templates automatically."""
    admin = get_current_admin()
    if admin:
        group, role = get_group_context(admin)
        return {'current_group': group, 'group_role': role}
    return {'current_group': None, 'group_role': None}
