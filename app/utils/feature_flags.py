from flask import current_app

class FeatureFlags:
    def __init__(self, table_id):
        self.table_id = table_id
        self.flags = self._initialize_flags()

    def _initialize_flags(self):
        # აქ შეგიძლიათ დაამატოთ ლოგიკა, თუ გსურთ განსხვავებული ფლაგების ჩართვა თითოეული table_id-ისთვის
        return {
            "ENABLE_CART": True,  # მაგიდის ID-ს საფუძველზე, ეს ფუნქციონალი შეიძლება იყოს აქტიური
            "ENABLE_PROMOTIONS": True,  # მაგიდის ID-ს საფუძველზე, ეს ფუნქციონალი შეიძლება იყოს აქტიური
        }

    def is_enabled(self, flag_name):
        return self.flags.get(flag_name, False)

def init_feature_flags(app):
    @app.context_processor
    def inject_feature_flags():
        table_id = int(current_app.config.get("TABLE_ID", 0))
        feature_flags = FeatureFlags(table_id)
        return dict(feature_flags=feature_flags)
