from app.models import Promotion

class PromotionService:
    @staticmethod
    def get_promotion_by_id(promotion_id):
        return Promotion.query.get(promotion_id)

    @staticmethod
    def get_active_promotions():
        from datetime import datetime
        return Promotion.query.filter(Promotion.StartDate <= datetime.utcnow(),
                                      Promotion.EndDate >= datetime.utcnow()).all()
