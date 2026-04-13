"""Super admin routes for managing the global product library."""
import os
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app import db
from app.models import AdminUser, GlobalCategory, GlobalSubcategory, GlobalItem, Category, Subcategory, FoodItem

lib_bp = Blueprint('lib_bp', __name__, url_prefix='/backoffice/library')

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
        admin = AdminUser.query.get(session.get('admin_id'))
        if not admin or not admin.is_super:
            flash('Access denied')
            return redirect(url_for('bo_bp.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# Global Library — Super Admin
# ============================================================

@lib_bp.route('/')
@login_required
@super_required
def library_index():
    categories = GlobalCategory.query.order_by(GlobalCategory.sort_order).all()
    return render_template('backoffice/global_library.html', categories=categories)


@lib_bp.route('/categories/add', methods=['POST'])
@login_required
@super_required
def add_global_category():
    name = request.form.get('name', '').strip()
    if not name:
        flash('სახელი სავალდებულოა')
        return redirect(url_for('lib_bp.library_index'))
    cat = GlobalCategory(name=name, description=request.form.get('description', ''))
    db.session.add(cat)
    db.session.commit()
    flash(f'კატეგორია "{name}" დაემატა')
    return redirect(url_for('lib_bp.library_index'))


@lib_bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@login_required
@super_required
def delete_global_category(cat_id):
    cat = GlobalCategory.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    flash(f'კატეგორია "{cat.name}" წაიშალა')
    return redirect(url_for('lib_bp.library_index'))


@lib_bp.route('/subcategories/add', methods=['POST'])
@login_required
@super_required
def add_global_subcategory():
    name = request.form.get('name', '').strip()
    cat_id = request.form.get('category_id', type=int)
    if not name or not cat_id:
        flash('სახელი სავალდებულოა')
        return redirect(url_for('lib_bp.library_index'))
    sub = GlobalSubcategory(name=name, category_id=cat_id)
    db.session.add(sub)
    db.session.commit()
    flash(f'საბკატეგორია "{name}" დაემატა')
    return redirect(url_for('lib_bp.library_index'))


@lib_bp.route('/subcategories/<int:sub_id>/delete', methods=['POST'])
@login_required
@super_required
def delete_global_subcategory(sub_id):
    sub = GlobalSubcategory.query.get_or_404(sub_id)
    name = sub.name
    db.session.delete(sub)
    db.session.commit()
    flash(f'საბკატეგორია "{name}" წაიშალა')
    return redirect(url_for('lib_bp.library_index'))


@lib_bp.route('/items/add', methods=['POST'])
@login_required
@super_required
def add_global_item():
    name = request.form.get('name', '').strip()
    cat_id = request.form.get('category_id', type=int)
    if not name or not cat_id:
        flash('სახელი და კატეგორია სავალდებულოა')
        return redirect(url_for('lib_bp.library_index'))

    image_filename = None
    file = request.files.get('image')
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'library')
        os.makedirs(upload_dir, exist_ok=True)
        file.save(os.path.join(upload_dir, filename))
        image_filename = 'library/' + filename

    item = GlobalItem(
        category_id=cat_id,
        name=name,
        description=request.form.get('description', ''),
        ingredients=request.form.get('ingredients', ''),
        image_filename=image_filename,
    )
    db.session.add(item)
    db.session.commit()
    flash(f'"{name}" დაემატა ბიბლიოთეკაში')
    return redirect(url_for('lib_bp.library_index'))


@lib_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
@super_required
def delete_global_item(item_id):
    item = GlobalItem.query.get_or_404(item_id)
    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(f'"{name}" წაიშალა')
    return redirect(url_for('lib_bp.library_index'))


# ============================================================
# Venue Admin — Browse & Import from Global Library
# ============================================================

@lib_bp.route('/browse')
@login_required
def browse_library():
    """Venue admin browses global library to import items."""
    admin = AdminUser.query.get(session['admin_id'])
    if not admin or not admin.venue:
        flash('No venue')
        return redirect(url_for('bo_bp.dashboard'))
    categories = GlobalCategory.query.filter_by(is_active=True).order_by(GlobalCategory.sort_order).all()
    return render_template('backoffice/library_browse.html', admin=admin, categories=categories)


@lib_bp.route('/import', methods=['POST'])
@login_required
def import_item():
    """Copy a global item into the venue's menu."""
    admin = AdminUser.query.get(session['admin_id'])
    if not admin or not admin.venue:
        return jsonify(error='No venue'), 400

    data = request.get_json() or {}
    global_item_id = data.get('item_id')
    target_cat_id = data.get('category_id')  # venue's own category
    price = data.get('price', 0.0)

    global_item = GlobalItem.query.get_or_404(global_item_id)

    # Verify target category belongs to this venue
    cat = Category.query.filter_by(CategoryID=target_cat_id, venue_id=admin.venue.id).first()
    if not cat:
        return jsonify(error='Category not found'), 404

    item = FoodItem(
        FoodName=global_item.name,
        Description=global_item.description or global_item.name,
        Ingredients=global_item.ingredients or '',
        Price=float(price),
        ImageFilename=global_item.image_filename or 'default-image.png',
        CategoryID=target_cat_id,
        allow_customization=True,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(success=True, item_id=item.FoodItemID, name=item.FoodName)


@lib_bp.route('/api/items')
@login_required
def api_library_items():
    """JSON list of global items, optionally filtered by category."""
    cat_id = request.args.get('category_id', type=int)
    q = GlobalItem.query.filter_by(is_active=True)
    if cat_id:
        q = q.filter_by(category_id=cat_id)
    items = q.order_by(GlobalItem.name).all()
    return jsonify(items=[it.to_dict() for it in items])
