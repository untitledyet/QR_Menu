from functools import wraps
from flask import abort

def require_feature(feature_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not getattr(args[0], 'feature_flags', None).is_enabled(feature_name):
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def format_currency(value):
    """Helper function to format a number as currency."""
    return "${:,.2f}".format(value)
