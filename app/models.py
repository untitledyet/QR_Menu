import hashlib
import secrets
import string
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import validates
from app import db


def _hash_token(raw_token: str) -> str:
    """One-way SHA-256 hash for secure token storage in DB.
    Store the hash; send the raw token to the user.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _generate_venue_code():
    """Generate a unique 8-char alphanumeric venue code e.g. TB-A3X9KZ."""
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(chars) for _ in range(6))
    return f'TB-{suffix}'


def _generate_invite_code():
    """Generate a unique invite code e.g. TB-INV-A3X9KZ."""
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(chars) for _ in range(6))
    return f'TB-INV-{suffix}'


# ============================================================
# Plans — feature bundles
# ============================================================

# Define which features each plan includes
PLAN_FEATURES = {
    'free': {
        'menu': True,
        'categories': True,
        'subcategories': True,
        'ingredient_customization': False,
        'promotions': False,
        'cart': False,
        'payments': False,
        'ratings': False,
        'analytics': False,
        'reservations': False,
    },
    'basic': {
        'menu': True,
        'categories': True,
        'subcategories': True,
        'ingredient_customization': True,
        'promotions': True,
        'cart': True,
        'payments': False,
        'ratings': False,
        'analytics': False,
        'reservations': False,
    },
    'premium': {
        'menu': True,
        'categories': True,
        'subcategories': True,
        'ingredient_customization': True,
        'promotions': True,
        'cart': True,
        'payments': True,
        'ratings': True,
        'analytics': True,
        'reservations': True,
    },
}

MAX_ITEMS_PER_VENUE = 999

FEATURE_LIST = [
    ('menu', 'Menu', 'fas fa-book-open', 'Create and manage menu items'),
    ('categories', 'Categories', 'fas fa-layer-group', 'Organize items by category'),
    ('subcategories', 'Subcategories', 'fas fa-sitemap', 'Sub-level categorization'),
    ('ingredient_customization', 'Ingredient Customization', 'fas fa-sliders-h', 'Customers can modify ingredients'),
    ('promotions', 'Promotions', 'fas fa-tags', 'Create promotional offers'),
    ('cart', 'Cart & Ordering', 'fas fa-shopping-cart', 'Cart and order placement'),
    ('payments', 'Online Payments', 'fas fa-credit-card', 'Accept payments online'),
    ('ratings', 'Ratings & Reviews', 'fas fa-star', 'Customer ratings on dishes'),
    ('analytics', 'Analytics', 'fas fa-chart-bar', 'Venue performance analytics'),
    ('reservations', 'Reservations', 'fas fa-calendar-check', 'Table reservation system'),
]


# ============================================================
# Admin & Venue
# ============================================================

class AdminUser(db.Model):
    __tablename__ = 'AdminUsers'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=True)  # kept for super admin compat
    email = db.Column(db.String(150), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='venue')
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Verification
    email_verified = db.Column(db.Boolean, default=False)
    email_token = db.Column(db.String(64), nullable=True)       # stores SHA-256 hash
    email_token_expires = db.Column(db.DateTime, nullable=True)
    phone_verified = db.Column(db.Boolean, default=False)
    sms_code_hash = db.Column(db.String(256), nullable=True)
    sms_code_expires = db.Column(db.DateTime, nullable=True)
    sms_attempts = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=False)

    # Password reset
    reset_token = db.Column(db.String(64), nullable=True)       # stores SHA-256 hash
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    # Brute force protection
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    # 2FA preference — method: None=disabled, 'sms', 'email'
    two_fa_enabled = db.Column(db.Boolean, default=False, nullable=False)
    two_fa_method = db.Column(db.String(10), nullable=True)  # 'sms' | 'email' | None

    # Language preference (used for notifications)
    lang = db.Column(db.String(5), default='ka', nullable=False)

    venue = db.relationship('Venue', backref=db.backref('admins', lazy=True))

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def set_sms_code(self, code):
        self.sms_code_hash = generate_password_hash(code)
        self.sms_attempts = 0

    def check_sms_code(self, code):
        if not self.sms_code_hash:
            return False
        return check_password_hash(self.sms_code_hash, code)

    @property
    def is_locked(self):
        if self.locked_until and datetime.utcnow() < self.locked_until:
            return True
        return False

    def record_failed_login(self):
        self.failed_login_attempts = (self.failed_login_attempts or 0) + 1
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)

    def reset_failed_logins(self):
        self.failed_login_attempts = 0
        self.locked_until = None

    @property
    def is_super(self):
        return self.role == 'super'


class Venue(db.Model):
    __tablename__ = 'Venues'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    venue_code = db.Column(db.String(12), unique=True, nullable=True)  # e.g. TB-A3X9KZ
    plan = db.Column(db.String(20), nullable=False, default='free')
    total_tables = db.Column(db.Integer, nullable=False, default=0)
    address = db.Column(db.String(300), nullable=True)
    google_place_id = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Chain membership — nullable; if set, venue belongs to this group
    group_id = db.Column(db.Integer, db.ForeignKey('VenueGroups.id',
                         use_alter=True, name='fk_venue_group'), nullable=True, index=True)

    feature_overrides = db.relationship('VenueFeatureOverride', backref='venue',
                                         lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', foreign_keys='Category.venue_id',
                                 backref='venue', lazy=True, cascade='all, delete-orphan')
    promotions = db.relationship('Promotion', backref='venue', lazy=True, cascade='all, delete-orphan')

    def has_feature(self, feature_key):
        """Check if venue has a feature: plan default + individual override."""
        # Check override first
        override = VenueFeatureOverride.query.filter_by(
            venue_id=self.id, feature_key=feature_key).first()
        if override:
            return override.enabled
        # Fall back to plan
        plan_features = PLAN_FEATURES.get(self.plan, PLAN_FEATURES['free'])
        return plan_features.get(feature_key, False)

    def get_all_features(self):
        plan_features = PLAN_FEATURES.get(self.plan, PLAN_FEATURES['free'])
        overrides = {o.feature_key: o.enabled for o in self.feature_overrides}
        result = {}
        for key, default_val in plan_features.items():
            result[key] = overrides.get(key, default_val)
        return result

    @property
    def plan_display(self):
        return self.plan.capitalize()

    def item_count(self):
        return FoodItem.query.join(Category).filter(Category.venue_id == self.id).count()


class VenueGroup(db.Model):
    """A chain/network of venues sharing a common menu."""
    __tablename__ = 'VenueGroups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # The venue that created/owns the group
    owner_venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=False, index=True)
    # Whether branch admins are allowed to override item prices
    allow_price_override = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner_venue = db.relationship('Venue', foreign_keys=[owner_venue_id],
                                  backref=db.backref('owned_group', uselist=False))
    branches = db.relationship('Venue', foreign_keys='Venue.group_id',
                               backref='group', lazy='dynamic')
    invites = db.relationship('VenueGroupInvite', backref='group',
                              lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', foreign_keys='Category.group_id',
                                 backref='venue_group', lazy=True)

    @property
    def branch_list(self):
        return Venue.query.filter_by(group_id=self.id).all()

    @property
    def branch_count(self):
        return Venue.query.filter_by(group_id=self.id).count()


class VenueGroupInvite(db.Model):
    """Single-use invite code for joining a group."""
    __tablename__ = 'VenueGroupInvites'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('VenueGroups.id'), nullable=False, index=True)
    invite_code = db.Column(db.String(20), unique=True, nullable=False)
    invited_by = db.Column(db.Integer, db.ForeignKey('AdminUsers.id'), nullable=False, index=True)
    # Optional: pre-targeted to a specific venue (unused unless specified)
    target_venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=True, index=True)
    status = db.Column(db.String(20), default='pending', nullable=False, index=True)  # pending/accepted/expired
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    inviter = db.relationship('AdminUser', foreign_keys=[invited_by])

    @property
    def is_expired(self):
        return self.status != 'pending' or datetime.utcnow() > self.expires_at


class VenueFeatureOverride(db.Model):
    """Super admin can override individual features per venue, regardless of plan."""
    __tablename__ = 'VenueFeatureOverrides'

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=False, index=True)
    feature_key = db.Column(db.String(50), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False)

    __table_args__ = (db.UniqueConstraint('venue_id', 'feature_key'),)


# ============================================================
# Menu models
# ============================================================

class Category(db.Model):
    __tablename__ = 'Categories'
    CategoryID = db.Column(db.Integer, primary_key=True)
    CategoryName = db.Column(db.String(150), nullable=False)
    CategoryName_en = db.Column(db.String(150), nullable=True)
    Description = db.Column(db.String(500), nullable=True)
    Description_en = db.Column(db.String(500), nullable=True)
    CategoryIcon = db.Column(db.String(100), nullable=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=True, index=True)
    # If group_id is set and venue_id is NULL → shared group category
    group_id = db.Column(db.Integer, db.ForeignKey('VenueGroups.id'), nullable=True, index=True)


class Subcategory(db.Model):
    __tablename__ = 'Subcategories'
    SubcategoryID = db.Column(db.Integer, primary_key=True)
    SubcategoryName = db.Column(db.String(150), nullable=False)
    SubcategoryName_en = db.Column(db.String(150), nullable=True)
    CategoryID = db.Column(db.Integer, db.ForeignKey('Categories.CategoryID'), nullable=False, index=True)
    category = db.relationship('Category', backref=db.backref('subcategories', lazy=True))


class FoodItem(db.Model):
    __tablename__ = 'FoodItems'
    FoodItemID = db.Column(db.Integer, primary_key=True)
    FoodName = db.Column(db.String(150), nullable=False)
    FoodName_en = db.Column(db.String(150), nullable=True)
    Description = db.Column(db.String(500), nullable=False)
    Description_en = db.Column(db.String(500), nullable=True)
    Ingredients = db.Column(db.String(500), nullable=False)
    Ingredients_en = db.Column(db.String(500), nullable=True)
    Price = db.Column(db.Float, nullable=False)
    ImageFilename = db.Column(db.String(500), nullable=True)
    CategoryID = db.Column(db.Integer, db.ForeignKey('Categories.CategoryID'), nullable=False, index=True)
    SubcategoryID = db.Column(db.Integer, db.ForeignKey('Subcategories.SubcategoryID'), nullable=True, index=True)
    allow_customization = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'FoodItemID': self.FoodItemID,
            'FoodName': self.FoodName, 'FoodName_en': self.FoodName_en or '',
            'Description': self.Description, 'Description_en': self.Description_en or '',
            'Ingredients': self.Ingredients, 'Ingredients_en': self.Ingredients_en or '',
            'Price': self.Price, 'ImageFilename': self.ImageFilename,
            'CategoryID': self.CategoryID, 'SubcategoryID': self.SubcategoryID,
            'AllowCustomization': self.allow_customization,
        }


class Promotion(db.Model):
    __tablename__ = 'Promotions'
    PromotionID = db.Column(db.Integer, primary_key=True)
    PromotionName = db.Column(db.String(100), nullable=False)
    Description = db.Column(db.String(255), nullable=True)
    Discount = db.Column(db.Float, nullable=True)
    StartDate = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    EndDate = db.Column(db.Date, nullable=False)
    BackgroundImage = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=True, index=True)


class Order(db.Model):
    __tablename__ = 'Orders'
    OrderID = db.Column(db.Integer, primary_key=True)
    TableID = db.Column(db.Integer, nullable=False, index=True)
    Items = db.Column(db.Text, nullable=False)
    Status = db.Column(db.String(50), default="Pending", index=True)
    CreatedAt = db.Column(db.DateTime, default=datetime.utcnow)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=True, index=True)

    def __init__(self, TableID, Items, venue_id=None):
        self.TableID = TableID
        self.Items = Items
        self.venue_id = venue_id


class GlobalCategory(db.Model):
    """Platform-wide product categories — not tied to any venue."""
    __tablename__ = 'GlobalCategories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100), nullable=True)
    description = db.Column(db.String(300), nullable=True)
    description_en = db.Column(db.String(300), nullable=True)
    icon = db.Column(db.String(100), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('GlobalItem', backref='category', lazy=True, cascade='all, delete-orphan')


class GlobalSubcategory(db.Model):
    """Platform-wide subcategories for global library."""
    __tablename__ = 'GlobalSubcategories'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('GlobalCategories.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    category = db.relationship('GlobalCategory', backref=db.backref('subcategories', lazy=True))


class GlobalItem(db.Model):
    """Platform-wide product library — not tied to any venue."""
    __tablename__ = 'GlobalItems'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('GlobalCategories.id'), nullable=True, index=True)
    subcategory_id = db.Column(db.Integer, db.ForeignKey('GlobalSubcategories.id'), nullable=True, index=True)
    name_ge = db.Column(db.String(100), nullable=False, unique=True)
    ingredients_ge = db.Column(db.String(500), nullable=True)
    description_ge = db.Column(db.String(500), nullable=True)
    name_en = db.Column(db.String(100), nullable=True)
    ingredients_en = db.Column(db.String(500), nullable=True)
    description_en = db.Column(db.String(500), nullable=True)
    image_filename = db.Column(db.String(200), nullable=True)
    tags = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def tags_list(self):
        if not self.tags:
            return []
        return [t.strip().lower() for t in self.tags.split(',') if t.strip()]

    subcategory = db.relationship('GlobalSubcategory', backref=db.backref('items', lazy=True))

    _REQUIRED_FOR_VERIFIED = (
        'name_ge', 'ingredients_ge', 'description_ge',
        'name_en', 'ingredients_en', 'description_en', 'image_filename',
    )

    @validates('is_verified')
    def validate_is_verified(self, key, value):
        if value:
            missing = [f for f in self._REQUIRED_FOR_VERIFIED if not getattr(self, f, None)]
            if missing:
                raise ValueError(f'is_verified=True მოითხოვს: {", ".join(missing)}')
        return value

    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'subcategory_id': self.subcategory_id,
            'name_ge': self.name_ge, 'name_en': self.name_en or '',
            'description_ge': self.description_ge, 'description_en': self.description_en or '',
            'ingredients_ge': self.ingredients_ge, 'ingredients_en': self.ingredients_en or '',
            'image_filename': self.image_filename,
        }


# ============================================================
# Reservation constants
# ============================================================

BOOKING_DURATION = timedelta(hours=3)

BOOKING_STATUSES = {
    'pending_payment': 'Pending Payment',
    'confirmed': 'Confirmed',
    'cancelled': 'Cancelled',
    'expired': 'Expired',
    'completed': 'Completed',
}


# ============================================================
# Reservation models
# ============================================================

class ReservationCustomer(db.Model):
    __tablename__ = 'ReservationCustomers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    preferred_language = db.Column(db.String(5), default='ka')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class RestaurantTable(db.Model):
    __tablename__ = 'RestaurantTables'

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=False, index=True)
    label = db.Column(db.String(20), nullable=False)
    shape = db.Column(db.String(20), nullable=False, default='circle')
    capacity = db.Column(db.Integer, nullable=False, default=4)
    pos_x = db.Column(db.Float, nullable=False, default=0.0)
    pos_y = db.Column(db.Float, nullable=False, default=0.0)
    width = db.Column(db.Float, nullable=False, default=60.0)
    height = db.Column(db.Float, nullable=False, default=60.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    venue = db.relationship('Venue', backref=db.backref('tables', lazy=True))


class Booking(db.Model):
    __tablename__ = 'Bookings'

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=False, index=True)
    table_id = db.Column(db.Integer, db.ForeignKey('RestaurantTables.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('ReservationCustomers.id'), nullable=False, index=True)
    booking_date = db.Column(db.Date, nullable=False, index=True)
    time_slot = db.Column(db.Time, nullable=False)
    guest_count = db.Column(db.Integer, nullable=False)
    guest_name = db.Column(db.String(100), nullable=False)
    guest_email = db.Column(db.String(150), nullable=False)
    guest_phone = db.Column(db.String(20), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending_payment', index=True)
    language = db.Column(db.String(5), nullable=False, default='ka')
    cancellation_token = db.Column(db.String(64), unique=True, nullable=True)
    payment_intent_id = db.Column(db.String(100), nullable=True)
    deposit_amount = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    venue = db.relationship('Venue', backref=db.backref('bookings', lazy=True))
    table = db.relationship('RestaurantTable', backref=db.backref('bookings', lazy=True))
    customer = db.relationship('ReservationCustomer', backref=db.backref('bookings', lazy=True))


class ReservationSettings(db.Model):
    __tablename__ = 'ReservationSettings'

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), unique=True, nullable=False)
    deposit_amount = db.Column(db.Float, nullable=False, default=0.0)
    time_slots = db.Column(db.JSON, nullable=False, default=lambda: ["18:00", "19:00", "20:00", "21:00", "22:00"])
    max_advance_days = db.Column(db.Integer, nullable=False, default=30)
    floor_layout = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    venue = db.relationship('Venue', backref=db.backref('reservation_settings', uselist=False))


# ============================================================
# Phone OTP (pre-registration verification)
# ============================================================

class PhoneOtp(db.Model):
    """Temporary OTP storage for pre-registration phone verification."""
    __tablename__ = 'PhoneOtps'
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    code_hash = db.Column(db.String(256), nullable=False)
    expires = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0)
    ip = db.Column(db.String(45), nullable=True)                # for IP-based rate limiting
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# Chain / Group — price overrides per branch
# ============================================================

class ScraperJob(db.Model):
    """Background menu scraper job — one per venue."""
    __tablename__ = 'ScraperJobs'

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=False, unique=True)
    # pending / running / done / failed / dismissed
    status = db.Column(db.String(20), nullable=False, default='pending')
    result_json = db.Column(db.JSON, nullable=True)
    sources_found = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    venue = db.relationship('Venue', backref=db.backref('scraper_job', uselist=False))


class VenueItemPriceOverride(db.Model):
    """Branch-level price override for a group-shared menu item."""
    __tablename__ = 'VenueItemPriceOverrides'

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(db.Integer, db.ForeignKey('Venues.id'), nullable=False, index=True)
    food_item_id = db.Column(db.Integer, db.ForeignKey('FoodItems.FoodItemID'), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)

    venue = db.relationship('Venue', backref=db.backref('price_overrides', lazy=True))
    food_item = db.relationship('FoodItem', backref=db.backref('price_overrides', lazy=True))

    __table_args__ = (db.UniqueConstraint('venue_id', 'food_item_id',
                                          name='uq_venue_item_price'),)


class SystemSetting(db.Model):
    """Platform-wide key/value settings (superadmin-controlled)."""
    __tablename__ = 'SystemSettings'

    key   = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(512), nullable=False, default='')

    @staticmethod
    def get(key: str, default: str = '') -> str:
        try:
            row = SystemSetting.query.get(key)
            return row.value if row is not None else default
        except Exception:
            return default

    @staticmethod
    def set(key: str, value: str) -> None:
        row = SystemSetting.query.get(key)
        if row is None:
            row = SystemSetting(key=key, value=value)
            db.session.add(row)
        else:
            row.value = value
        db.session.commit()
