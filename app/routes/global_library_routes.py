"""Super admin routes for managing the global product library."""
import os
import json
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app import db
from app.models import AdminUser, GlobalCategory, GlobalSubcategory, GlobalItem, Category, Subcategory, FoodItem
from app.services.translation_service import translate_global_item_async, needs_translation, _call_openai

lib_bp = Blueprint('lib_bp', __name__, url_prefix='/backoffice/library')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect('/login')
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
    admin = AdminUser.query.get(session['admin_id'])
    categories = GlobalCategory.query.order_by(GlobalCategory.sort_order).all()
    return render_template('backoffice/global_library.html', admin=admin, categories=categories)


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
        name_ge=name,
        name_en=request.form.get('name_en', '').strip() or None,
        description_ge=request.form.get('description', ''),
        description_en=request.form.get('description_en', '').strip() or None,
        ingredients_ge=request.form.get('ingredients', ''),
        ingredients_en=request.form.get('ingredients_en', '').strip() or None,
        image_filename=image_filename,
    )
    db.session.add(item)
    db.session.commit()

    name_en = request.form.get('name_en', '').strip()
    desc_en = request.form.get('description_en', '').strip()
    ing_en = request.form.get('ingredients_en', '').strip()
    if needs_translation(name, name_en):
        translate_global_item_async(item.id,
                                    {'name': name, 'description': item.description_ge or '',
                                     'ingredients': item.ingredients_ge or ''},
                                    'ka', 'en', current_app._get_current_object())
    elif needs_translation(name_en, name):
        translate_global_item_async(item.id,
                                    {'name': name_en, 'description': desc_en,
                                     'ingredients': ing_en},
                                    'en', 'ka', current_app._get_current_object())

    flash(f'"{name}" დაემატა ბიბლიოთეკაში')
    return redirect(url_for('lib_bp.library_index'))


@lib_bp.route('/items/<int:item_id>/delete', methods=['POST'])
@login_required
@super_required
def delete_global_item(item_id):
    item = GlobalItem.query.get_or_404(item_id)
    name = item.name_ge
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
        FoodName=global_item.name_ge,
        FoodName_en=global_item.name_en or None,
        Description=global_item.description_ge or global_item.name_ge,
        Description_en=global_item.description_en or None,
        Ingredients=global_item.ingredients_ge or '',
        Ingredients_en=global_item.ingredients_en or None,
        Price=float(price),
        ImageFilename=global_item.image_filename or 'default-image.png',
        CategoryID=target_cat_id,
        allow_customization=True,
        is_active=True,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(success=True, item_id=item.FoodItemID, name=item.FoodName)


@lib_bp.route('/create-category', methods=['POST'])
@login_required
def create_venue_category():
    """Create a new venue category inline from the library browse page.
    If global_cat_id is provided, copies name and icon from that global category."""
    from app.models import Category
    admin = AdminUser.query.get(session['admin_id'])
    if not admin or not admin.venue:
        return jsonify(error='No venue'), 400
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    global_cat_id = data.get('global_cat_id')
    icon_filename = None

    if global_cat_id:
        global_cat = GlobalCategory.query.get(global_cat_id)
        if global_cat:
            if not name:
                name = global_cat.name
            icon_filename = global_cat.icon

    if not name:
        return jsonify(error='სახელი სავალდებულოა'), 400

    cat = Category(CategoryName=name, CategoryIcon=icon_filename, venue_id=admin.venue.id)
    db.session.add(cat)
    db.session.commit()
    return jsonify(success=True, category_id=cat.CategoryID, category_name=cat.CategoryName)


@lib_bp.route('/api/items')
@login_required
def api_library_items():
    """JSON list of global items, optionally filtered by category."""
    cat_id = request.args.get('category_id', type=int)
    q = GlobalItem.query.filter_by(is_active=True)
    if cat_id:
        q = q.filter_by(category_id=cat_id)
    items = q.order_by(GlobalItem.name_ge).all()
    return jsonify(items=[it.to_dict() for it in items])


# ============================================================
# Dish Verification — Super Admin
# ============================================================

_VERIFY_FIELDS = ('name_ge', 'ingredients_ge', 'description_ge',
                  'name_en', 'ingredients_en', 'description_en', 'image_filename')


def _missing(item):
    return [f for f in _VERIFY_FIELDS if not getattr(item, f, None)]


def _item_verify_dict(item):
    d = {f: getattr(item, f) or '' for f in _VERIFY_FIELDS}
    d['id'] = item.id
    d['is_verified'] = item.is_verified
    d['is_active'] = item.is_active
    d['category_id'] = item.category_id
    d['subcategory_id'] = item.subcategory_id
    d['missing'] = _missing(item)
    return d


@lib_bp.route('/verify')
@login_required
@super_required
def verify_index():
    admin = AdminUser.query.get(session['admin_id'])
    total = GlobalItem.query.filter_by(is_active=True).count()
    verified = GlobalItem.query.filter_by(is_active=True, is_verified=True).count()
    return render_template('backoffice/verify_items.html', admin=admin,
                           total=total, verified=verified)


@lib_bp.route('/verify/api/items')
@login_required
@super_required
def verify_api_items():
    page = request.args.get('page', 1, type=int)
    per_page = 40
    only_unverified = request.args.get('unverified', '1') == '1'
    search = request.args.get('q', '').strip()

    q = GlobalItem.query.filter_by(is_active=True)
    if only_unverified:
        q = q.filter_by(is_verified=False)
    if search:
        q = q.filter(GlobalItem.name_ge.ilike(f'%{search}%'))
    q = q.order_by(GlobalItem.id)

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify(
        total=total, page=page, per_page=per_page,
        items=[_item_verify_dict(it) for it in items],
    )


@lib_bp.route('/verify/api/item/<int:item_id>')
@login_required
@super_required
def verify_api_item(item_id):
    item = GlobalItem.query.get_or_404(item_id)
    return jsonify(_item_verify_dict(item))


@lib_bp.route('/verify/api/item/<int:item_id>/save', methods=['POST'])
@login_required
@super_required
def verify_api_save(item_id):
    item = GlobalItem.query.get_or_404(item_id)
    data = request.get_json() or {}
    for field in _VERIFY_FIELDS:
        if field == 'image_filename':
            continue
        if field in data:
            setattr(item, field, data[field].strip() or None)
    db.session.commit()
    return jsonify(ok=True, missing=_missing(item))


@lib_bp.route('/verify/api/item/<int:item_id>/translate', methods=['POST'])
@login_required
@super_required
def verify_api_translate(item_id):
    item = GlobalItem.query.get_or_404(item_id)
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify(error='OPENAI_API_KEY not set'), 500

    fields = {
        'name': item.name_ge or '',
        'description': item.description_ge or '',
        'ingredients': item.ingredients_ge or '',
    }
    try:
        result = _call_openai(fields, 'ka', 'en', api_key)
    except Exception as e:
        return jsonify(error=str(e)), 500

    item.name_en = result.get('name') or item.name_en
    item.description_en = result.get('description') or item.description_en
    item.ingredients_en = result.get('ingredients') or item.ingredients_en
    db.session.commit()
    return jsonify(
        ok=True,
        name_en=item.name_en or '',
        description_en=item.description_en or '',
        ingredients_en=item.ingredients_en or '',
        missing=_missing(item),
    )


@lib_bp.route('/verify/api/item/<int:item_id>/photo', methods=['POST'])
@login_required
@super_required
def verify_api_photo(item_id):
    item = GlobalItem.query.get_or_404(item_id)
    file = request.files.get('photo')
    if not file or not file.filename:
        return jsonify(error='No file'), 400

    data = file.read()
    if len(data) < 1000:
        return jsonify(error='File too small'), 400

    from app.services.r2_storage import upload_bytes, R2_PUBLIC_URL
    url = upload_bytes(data, prefix='global-items')
    if not url:
        return jsonify(error='R2 upload failed'), 500

    # Store the full URL directly as image_filename for global items
    item.image_filename = url
    db.session.commit()
    return jsonify(ok=True, image_url=url, missing=_missing(item))


@lib_bp.route('/verify/api/item/<int:item_id>/verify', methods=['POST'])
@login_required
@super_required
def verify_api_verify(item_id):
    item = GlobalItem.query.get_or_404(item_id)
    missing = _missing(item)
    if missing:
        return jsonify(error=f'შევსებული უნდა იყოს: {", ".join(missing)}'), 400
    try:
        item.is_verified = True
        db.session.commit()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(ok=True)


@lib_bp.route('/verify/api/item/<int:item_id>/describe', methods=['POST'])
@login_required
@super_required
def verify_api_describe(item_id):
    """Generate English description from name_ge + ingredients_ge, then translate to Georgian."""
    import requests as _req
    item = GlobalItem.query.get_or_404(item_id)
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify(error='OPENAI_API_KEY not set'), 500
    if not item.name_ge:
        return jsonify(error='name_ge is required'), 400

    try:
        import certifi
        verify_ssl = certifi.where()
    except ImportError:
        verify_ssl = True

    # Step 1: generate description_en
    gen_payload = {
        'model': 'gpt-4o',
        'messages': [
            {'role': 'system', 'content': (
                'You are writing one-line dish descriptions for a restaurant menu. '
                'Your goal: help a customer who has never heard of this dish understand what it is. '
                'Write exactly 1 sentence. Explain what kind of dish it is — NOT what ingredients it contains. '
                'Focus on the dish identity (e.g. "a baked Georgian flatbread filled with spiced kidney beans"). '
                'Do not list ingredients. Do not use the word "traditional" or "delicious". '
                'Return ONLY valid JSON: {"description_en": "..."}'
            )},
            {'role': 'user', 'content': f'Dish name: {item.name_ge}'},
        ],
        'temperature': 0.2,
        'response_format': {'type': 'json_object'},
    }
    resp = _req.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=gen_payload, verify=verify_ssl, timeout=20,
    )
    resp.raise_for_status()
    description_en = json.loads(resp.json()['choices'][0]['message']['content']).get('description_en', '')

    # Step 2: translate EN → GE
    description_ge = ''
    if description_en:
        try:
            translated = _call_openai({'description': description_en}, 'en', 'ka', api_key)
            description_ge = translated.get('description', '')
        except Exception:
            pass

    item.description_en = description_en or item.description_en
    if description_ge:
        item.description_ge = description_ge
    db.session.commit()
    return jsonify(
        ok=True,
        description_en=item.description_en or '',
        description_ge=item.description_ge or '',
        missing=_missing(item),
    )


def _fetch_ingredients_ge(dish_name: str, api_key: str) -> str:
    """Ask AI for Georgian ingredients list for a dish name."""
    import requests as _req
    try:
        import certifi
        verify_ssl = certifi.where()
    except ImportError:
        verify_ssl = True

    payload = {
        'model': 'gpt-4o',
        'messages': [
            {'role': 'system', 'content': (
                'შენ ხარ კულინარიის ექსპერტი. მომეცი მითითებული კერძის სტანდარტული '
                'ინგრედიენტების სია ქართულად, გრამატიკულად სწორად. '
                'უპასუხე მხოლოდ ამ JSON ფორმატით: {"ingredients": ["ინგრ1", "ინგრ2", ...]}'
            )},
            {'role': 'user', 'content': f'კერძი: {dish_name}'},
        ],
        'temperature': 0.1,
        'response_format': {'type': 'json_object'},
    }
    resp = _req.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload, verify=verify_ssl, timeout=20,
    )
    resp.raise_for_status()
    result = json.loads(resp.json()['choices'][0]['message']['content'])
    ingredients = result.get('ingredients', [])
    return ', '.join(ingredients) if isinstance(ingredients, list) else str(ingredients)


@lib_bp.route('/verify/api/add', methods=['POST'])
@login_required
@super_required
def verify_api_add():
    """Add new dishes by name — fetches Georgian ingredients via AI."""
    from sqlalchemy import func as sqlfunc
    data = request.get_json() or {}
    raw = data.get('names', '')
    names = [n.strip() for n in raw.split(',') if n.strip()]
    if not names:
        return jsonify(error='კერძი არ შეიყვანე'), 400

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify(error='OPENAI_API_KEY not set'), 500

    results = []
    for name in names:
        existing = GlobalItem.query.filter(
            sqlfunc.lower(GlobalItem.name_ge) == name.lower()
        ).first()

        if existing:
            if existing.ingredients_ge:
                results.append({'name': name, 'status': 'skip', 'msg': 'უკვე არსებობს'})
            else:
                try:
                    ingredients = _fetch_ingredients_ge(name, api_key)
                    existing.ingredients_ge = ingredients
                    db.session.commit()
                    results.append({'name': name, 'status': 'updated', 'msg': 'ინგრედიენტები დაემატა', 'id': existing.id})
                except Exception as e:
                    results.append({'name': name, 'status': 'error', 'msg': str(e)})
        else:
            try:
                ingredients = _fetch_ingredients_ge(name, api_key)
                item = GlobalItem(name_ge=name, ingredients_ge=ingredients)
                db.session.add(item)
                db.session.commit()
                results.append({'name': name, 'status': 'new', 'msg': 'დაემატა', 'id': item.id})
            except Exception as e:
                db.session.rollback()
                results.append({'name': name, 'status': 'error', 'msg': str(e)})
    return jsonify(results=results)
