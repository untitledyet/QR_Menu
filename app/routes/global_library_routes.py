"""Super admin routes for managing the global product library."""
import os
import json
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from app import db
from app.models import AdminUser, GlobalCategory, GlobalSubcategory, GlobalItem, Category, Subcategory, FoodItem, SystemSetting
from app.services.translation_service import translate_global_item_async, needs_translation, _call_openai

lib_bp = Blueprint('lib_bp', __name__, url_prefix='/backoffice/library')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

_TAG_GEN_SYSTEM = (
    'You are a culinary expert familiar with Georgian restaurant menus. '
    'Given a dish name in Georgian and English, generate a comprehensive list of '
    'alias names that a waiter, OCR scan, or customer might use to refer to this '
    'exact dish on a printed menu — in both Georgian and English.\n'
    'INCLUDE:\n'
    '• Word-order variants: "ყველის ხინKALi" ↔ "ხინKALi ყველის"\n'
    '• Parenthetical forms: "მეგRULi ხაჭაpური" → "ხაჭაpური (მეგRULi)"\n'
    '• Portion/size variants ONLY for dishes sold by individual piece count '
    '(ხინKALi, პელმენი, მანTi, ვარENIKi and similar dumplings/pastries sold by the piece): '
    'append "(8 ნAჭRIANi)" and "(6 ნAჭRIANi)" and "8 ნAჭRIANi <name>" and "6 ნAჭRIANi <name>". '
    'Do NOT add these size tags to other dishes (pizzas, salads, soups, khachapuri, lobiani, etc.).\n'
    '• Shortened/informal forms and common alternate spellings\n'
    '• English transliterations and standard English culinary names\n'
    'DO NOT include other dishes that are merely similar.\n'
    'DO NOT repeat the canonical name itself.\n'
    'Return ONLY a comma-separated list. No explanation, no numbering.'
)


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
    subcategories = GlobalSubcategory.query.order_by(GlobalSubcategory.sort_order).all()
    subs_by_cat = {}
    for s in subcategories:
        subs_by_cat.setdefault(s.category_id, []).append(s)
    total = GlobalItem.query.filter_by(is_active=True).count()
    verified = GlobalItem.query.filter_by(is_active=True, is_verified=True).count()
    return render_template('backoffice/global_library.html',
                           admin=admin, categories=categories,
                           subs_by_cat=subs_by_cat,
                           total=total, verified=verified)


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
    q = GlobalItem.query.filter_by(is_active=True, is_verified=True)
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
    d['category_name'] = item.category.name if item.category else ''
    d['subcategory_name'] = item.subcategory.name if item.subcategory else ''
    d['missing'] = _missing(item)
    d['image_url'] = item.image_filename or None
    d['tags'] = item.tags or ''
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
    per_page = request.args.get('per_page', 40, type=int)
    per_page = min(per_page, 100)

    # filter= all/verified/unverified (new), or unverified=1/0 (legacy)
    filt = request.args.get('filter', '').strip()
    if filt == 'verified':
        only_verified, only_unverified = True, False
    elif filt == 'unverified':
        only_verified, only_unverified = False, True
    elif filt == 'all':
        only_verified, only_unverified = False, False
    else:
        only_unverified = request.args.get('unverified', '1') == '1'
        only_verified = False

    search = (request.args.get('search') or request.args.get('q', '')).strip()
    cat_id = request.args.get('cat_id', type=int)
    sub_id = request.args.get('sub_id', type=int)

    q = GlobalItem.query.filter_by(is_active=True)
    if only_verified:
        q = q.filter_by(is_verified=True)
    elif only_unverified:
        q = q.filter_by(is_verified=False)
    if cat_id:
        q = q.filter_by(category_id=cat_id)
    if sub_id:
        q = q.filter_by(subcategory_id=sub_id)
    if search:
        q = q.filter(GlobalItem.name_ge.ilike(f'%{search}%'))
    q = q.order_by(GlobalItem.id)

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    has_more = (page * per_page) < total
    return jsonify(
        total=total, page=page, per_page=per_page,
        has_more=has_more,
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
    if 'tags' in data:
        item.tags = data['tags'].strip() or None
    # Category / subcategory assignment
    if 'category_id' in data:
        item.category_id = int(data['category_id']) if data['category_id'] else None
    if 'subcategory_id' in data:
        item.subcategory_id = int(data['subcategory_id']) if data['subcategory_id'] else None
    db.session.commit()
    return jsonify(ok=True, missing=_missing(item),
                   category_name=item.category.name if item.category else '',
                   subcategory_name=item.subcategory.name if item.subcategory else '')


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


@lib_bp.route('/verify/api/item/<int:item_id>/generate-tags', methods=['POST'])
@login_required
@super_required
def verify_api_generate_tags(item_id):
    """Generate alias tags for a GlobalItem using GPT-4o."""
    item = GlobalItem.query.get_or_404(item_id)
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify(error='OPENAI_API_KEY not set'), 500

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    system = _TAG_GEN_SYSTEM
    user = f'Georgian name: {item.name_ge or ""}\nEnglish name: {item.name_en or ""}'

    try:
        resp = client.chat.completions.create(
            model='gpt-4o',
            messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
            temperature=0.2,
            max_tokens=300,
        )
        tags = resp.choices[0].message.content.strip()
    except Exception as e:
        return jsonify(error=str(e)), 500

    item.tags = tags
    db.session.commit()
    return jsonify(ok=True, tags=tags)


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


@lib_bp.route('/verify/api/item/<int:item_id>/generate-photo', methods=['POST'])
@login_required
@super_required
def verify_api_generate_photo(item_id):
    """Generate a food photo using the configured AI provider and upload to R2."""
    item = GlobalItem.query.get_or_404(item_id)
    if not item.name_ge:
        return jsonify(error='name_ge is required'), 400

    api_key = os.environ.get('OPENAI_API_KEY', '')
    dish_label = item.name_en or item.name_ge
    prompt = (
        f'A highly realistic professional food photography image of {dish_label}. '
        'The dish must be placed in the center of the frame and fully visible, not cropped or cut off at the edges. '
        f'The image must strictly represent exactly this dish: "{dish_label}". '
        'Do not reinterpret or replace it with a more popular variation. '
        'Styled in rustic, dark moody food photography style. '
        'Set on a dark wooden table with natural textures and subtle props. '
        'Warm, soft, directional lighting creating gentle shadows and depth. '
        'Captured from a three-quarter angle, approximately 45-degree view, slightly top-down perspective. '
        'Sharp focus on the dish with shallow depth of field and soft background blur. '
        'Rich textures, natural colors, slightly warm tones. '
        'Ultra-realistic, high detail, crisp quality.'
    )

    provider = SystemSetting.get('ai.image_gen.provider', 'openai')
    t0 = time.time()
    img_bytes = None

    if provider == 'google':
        g_model = SystemSetting.get('ai.image_gen.google_model', 'imagen-4.0-generate-001')
        logger.info(f"[IMAGE-GEN] provider=google  model={g_model}  dish='{dish_label}'  → starting")
        try:
            from google import genai as _genai
            from google.genai import types as _gtypes
            g_key = os.environ.get('GOOGLE_API_KEY', '')
            if not g_key:
                return jsonify(error='GOOGLE_API_KEY not set'), 500
            gclient = _genai.Client(api_key=g_key)
            resp = gclient.models.generate_images(
                model=g_model,
                prompt=prompt,
                config=_gtypes.GenerateImagesConfig(number_of_images=1),
            )
            img_bytes = resp.generated_images[0].image.image_bytes
            logger.info(f"[IMAGE-GEN] provider=google  model={g_model}  dish='{dish_label}'  → done  {time.time()-t0:.1f}s")
        except Exception as e:
            logger.warning(f"[IMAGE-GEN] provider=google  model={g_model}  dish='{dish_label}'  → FAILED  {time.time()-t0:.1f}s  {e}")
            return jsonify(error=f'Image generation failed: {e}'), 500
    else:
        from openai import OpenAI
        import base64
        _model = SystemSetting.get('ai.image_gen.openai_model', 'gpt-image-1')
        logger.info(f"[IMAGE-GEN] provider=openai  model={_model}  dish='{dish_label}'  → starting")
        try:
            client = OpenAI(api_key=api_key)
            result = client.images.generate(
                model=_model,
                prompt=prompt,
                size='1024x1024',
            )
            img_bytes = base64.b64decode(result.data[0].b64_json)
            logger.info(f"[IMAGE-GEN] provider=openai  model={_model}  dish='{dish_label}'  → done  {time.time()-t0:.1f}s")
        except Exception as e:
            logger.warning(f"[IMAGE-GEN] provider=openai  model={_model}  dish='{dish_label}'  → FAILED  {time.time()-t0:.1f}s  {e}")
            return jsonify(error=f'Image generation failed: {e}'), 500

    from app.services.r2_storage import upload_bytes
    url = upload_bytes(img_bytes, prefix='global-items', no_compress=False)
    if not url:
        return jsonify(error='R2 upload failed'), 500

    item.image_filename = url
    db.session.commit()
    return jsonify(ok=True, image_url=url, missing=_missing(item))


@lib_bp.route('/verify/api/item/<int:item_id>/generate-photo-styled', methods=['POST'])
@login_required
@super_required
def verify_api_generate_photo_styled(item_id):
    """Generate a food photo using a reference image for style/subject guidance."""
    item = GlobalItem.query.get_or_404(item_id)
    if 'reference' not in request.files:
        return jsonify(error='reference file required'), 400

    api_key = os.environ.get('OPENAI_API_KEY', '')

    ref_file = request.files['reference']
    ref_bytes = ref_file.read()
    content_type = ref_file.content_type or 'image/jpeg'
    if content_type not in ('image/jpeg', 'image/png', 'image/webp'):
        content_type = 'image/jpeg'
    dish_label = item.name_en or item.name_ge or 'dish'

    prompt = (
        f'Transform this reference photo into a professional restaurant menu photograph of {dish_label}. '
        'Keep the dish appearance faithful to the reference. '
        'Dark wooden table, soft warm directional light from the left, 45-degree overhead angle, '
        'bokeh background, shallow depth of field. '
        'Photorealistic, natural food textures, no artificial gloss, no studio overexposure.'
    )

    provider = SystemSetting.get('ai.image_gen.provider', 'openai')
    t0 = time.time()
    img_bytes = None

    if provider == 'google':
        g_model = SystemSetting.get('ai.image_gen.google_model', 'imagen-4.0-generate-001')
        logger.info(f"[IMAGE-GEN] provider=google  model={g_model}  task=generate-styled  dish='{dish_label}'  → starting")
        try:
            from google import genai as _genai
            from google.genai import types as _gtypes
            g_key = os.environ.get('GOOGLE_API_KEY', '')
            if not g_key:
                return jsonify(error='GOOGLE_API_KEY not set'), 500
            gclient = _genai.Client(api_key=g_key)
            resp = gclient.models.generate_images(
                model=g_model,
                prompt=prompt,
                config=_gtypes.GenerateImagesConfig(number_of_images=1),
            )
            img_bytes = resp.generated_images[0].image.image_bytes
            logger.info(f"[IMAGE-GEN] provider=google  model={g_model}  task=generate-styled  dish='{dish_label}'  → done  {time.time()-t0:.1f}s")
        except Exception as e:
            logger.warning(f"[IMAGE-GEN] provider=google  model={g_model}  task=generate-styled  dish='{dish_label}'  → FAILED  {time.time()-t0:.1f}s  {e}")
            return jsonify(error=f'Image generation failed: {e}'), 500
    else:
        from openai import OpenAI
        import base64
        _model = SystemSetting.get('ai.image_gen.openai_model', 'gpt-image-1')
        logger.info(f"[IMAGE-GEN] provider=openai  model={_model}  task=edit-styled  dish='{dish_label}'  → starting")
        try:
            client = OpenAI(api_key=api_key)
            result = client.images.edit(
                model=_model,
                image=[('reference', ref_bytes, content_type)],
                prompt=prompt,
                size='1024x1024',
                quality='medium',
            )
            img_bytes = base64.b64decode(result.data[0].b64_json)
            logger.info(f"[IMAGE-GEN] provider=openai  model={_model}  task=edit-styled  dish='{dish_label}'  → done  {time.time()-t0:.1f}s")
        except Exception as e:
            logger.warning(f"[IMAGE-GEN] provider=openai  model={_model}  task=edit-styled  dish='{dish_label}'  → FAILED  {time.time()-t0:.1f}s  {e}")
            return jsonify(error=f'Image generation failed: {e}'), 500

    from app.services.r2_storage import upload_bytes
    url = upload_bytes(img_bytes, prefix='global-items', no_compress=False)
    if not url:
        return jsonify(error='R2 upload failed'), 500

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
                'You are writing one-sentence dish descriptions for a restaurant menu. '
                'Write exactly 1 sentence that conveys what the dish is — its nature, origin, and essence. '
                'Describe what the dish represents as a whole, not what it contains. '
                'Do not list ingredients. '
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


@lib_bp.route('/api/auto-assign-categories', methods=['POST'])
@login_required
@super_required
def auto_assign_categories():
    """AI batch: assign GlobalItems to GlobalCategories/Subcategories.

    POST body (JSON):
        only_unassigned: bool (default true)  — skip items that already have category_id
        dry_run: bool (default false)         — return plan without saving
    """
    import openai
    api_key = os.environ.get('OPENAI_API_KEY', '')
    model_fast = os.environ.get('OPENAI_MODEL_FAST', 'gpt-4o-mini')
    if not api_key:
        return jsonify(error='OPENAI_API_KEY not set'), 500

    data = request.get_json() or {}
    only_unassigned = data.get('only_unassigned', True)
    dry_run = data.get('dry_run', False)

    # Build taxonomy reference
    cats = GlobalCategory.query.order_by(GlobalCategory.sort_order).all()
    subs = GlobalSubcategory.query.order_by(GlobalSubcategory.sort_order).all()
    if not cats:
        return jsonify(error='GlobalCategories is empty — seed first'), 400

    cat_by_id = {c.id: c for c in cats}
    sub_by_id = {s.id: s for s in subs}
    subs_by_cat = {}
    for s in subs:
        subs_by_cat.setdefault(s.category_id, []).append(s)

    taxonomy = []
    for c in cats:
        taxonomy.append({
            'cat_id': c.id,
            'cat': f'{c.name} / {c.name_en}',
            'subs': [{'sub_id': s.id, 'sub': f'{s.name} / {s.name_en}'} for s in subs_by_cat.get(c.id, [])],
        })

    # Fetch items
    q = GlobalItem.query.filter_by(is_active=True)
    if only_unassigned:
        q = q.filter(GlobalItem.category_id.is_(None))
    items = q.all()

    if not items:
        return jsonify(assigned=0, skipped=0, message='ყველა item უკვე განაწილებულია')

    client = openai.OpenAI(api_key=api_key)

    BATCH = 60
    assigned = 0
    errors = 0
    details = []

    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        payload = [{'i': j, 'name_ge': it.name_ge, 'name_en': it.name_en or ''} for j, it in enumerate(batch)]

        prompt = (
            'You are classifying Georgian restaurant menu items into a taxonomy.\n\n'
            'TAXONOMY (cat_id, cat name, sub_id, sub name):\n'
            + json.dumps(taxonomy, ensure_ascii=False)
            + '\n\nFor each item below, return the best matching cat_id and sub_id (or null if no good match).\n'
            'Return JSON: {"results": [{"i": 0, "cat_id": 1, "sub_id": 3}, ...]}\n\n'
            'Items:\n' + json.dumps(payload, ensure_ascii=False)
        )

        try:
            resp = client.responses.create(
                model=config.OPENAI_MODEL_FAST,
                input=prompt,
                text={'format': {'type': 'json_object'}},
            )
            parsed = json.loads(resp.output_text)
            for row in parsed.get('results', []):
                idx = row.get('i')
                if idx is None or idx >= len(batch):
                    continue
                it = batch[idx]
                cat_id = row.get('cat_id')
                sub_id = row.get('sub_id')
                cat_name = cat_by_id[cat_id].name if cat_id and cat_id in cat_by_id else None
                sub_name = sub_by_id[sub_id].name if sub_id and sub_id in sub_by_id else None
                details.append({'id': it.id, 'name': it.name_ge, 'cat': cat_name, 'sub': sub_name})
                if not dry_run and cat_id:
                    it.category_id = cat_id
                    it.subcategory_id = sub_id if sub_id and sub_id in sub_by_id else None
                    assigned += 1
        except Exception as e:
            logger.warning(f'auto-assign batch {i}: {e}')
            errors += 1

    if not dry_run:
        db.session.commit()

    return jsonify(
        assigned=assigned,
        total=len(items),
        errors=errors,
        dry_run=dry_run,
        details=details[:100],
    )
