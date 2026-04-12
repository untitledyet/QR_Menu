"""Landing page and venue self-registration routes."""
import re
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app import db
from app.models import AdminUser, Venue

landing_bp = Blueprint('landing_bp', __name__)


@landing_bp.route('/')
def landing():
    venues = Venue.query.filter_by(is_active=True).all()
    return render_template('landing.html', venues=venues)


def slugify(text):
    """Generate URL-safe slug from text."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text


@landing_bp.route('/register', methods=['POST'])
def register_venue():
    data = request.get_json() or {}
    venue_name = data.get('venue_name', '').strip()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not venue_name or not username or not email or not password:
        return jsonify(error='All fields are required'), 400

    if len(password) < 6:
        return jsonify(error='Password must be at least 6 characters'), 400

    if AdminUser.query.filter_by(username=username).first():
        return jsonify(error='Username already taken'), 400

    # Generate unique slug
    base_slug = slugify(venue_name)
    if not base_slug:
        base_slug = 'venue'
    slug = base_slug
    counter = 2
    while Venue.query.filter_by(slug=slug).first():
        slug = f'{base_slug}-{counter}'
        counter += 1

    venue = Venue(name=venue_name, slug=slug, plan='free')
    db.session.add(venue)
    db.session.flush()

    admin = AdminUser(username=username, role='venue', venue_id=venue.id)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    session['admin_id'] = admin.id
    return jsonify(success=True, redirect='/backoffice')


@landing_bp.route('/login-venue', methods=['POST'])
def login_venue():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    admin = AdminUser.query.filter_by(username=username).first()
    if not admin or not admin.check_password(password):
        return jsonify(error='Invalid credentials'), 401

    session['admin_id'] = admin.id
    return jsonify(success=True, redirect='/backoffice')
