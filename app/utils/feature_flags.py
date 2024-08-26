from flask import current_app

import app


class FeatureFlags:
    def __init__(self, table_id):
        self.table_id = table_id
        self.flags = self._initialize_flags()

    def _initialize_flags(self):
        # გამოიყენე `current_app.config` კონფიგურაციიდან ფლაგების მისაღებად
        return {
            "ENABLE_CART": current_app.config['FEATURE_FLAGS'].get('enable_cart_functionality', False),
            "ENABLE_PROMOTIONS": current_app.config['FEATURE_FLAGS'].get('enable_promotions', False),
        }

    def is_enabled(self, flag_name):
        return self.flags.get(flag_name, False)


def init_feature_flags(app):
    @app.context_processor
    def inject_feature_flags():
        table_id = int(current_app.config.get("TABLE_ID", 0))
        feature_flags = FeatureFlags(table_id)
        return dict(feature_flags=feature_flags)
