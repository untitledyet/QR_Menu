from flask import current_app


class FeatureFlags:
    def __init__(self):
        self.flags = {
            "ENABLE_CART": current_app.config['FEATURE_FLAGS'].get('enable_cart_functionality', False),
            "ENABLE_PROMOTIONS": current_app.config['FEATURE_FLAGS'].get('enable_promotions', False),
        }

    def is_enabled(self, flag_name):
        return self.flags.get(flag_name, False)


def init_feature_flags(app):
    @app.context_processor
    def inject_feature_flags():
        feature_flags = FeatureFlags()
        return dict(feature_flags=feature_flags)
