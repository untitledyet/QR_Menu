"""Payment service with adapter pattern for Stripe integration."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from app import db
from app.models import Booking


@dataclass
class PaymentResult:
    success: bool
    payment_id: str = ''
    error: str = ''
    client_secret: str = ''


class PaymentGateway(ABC):
    @abstractmethod
    def create_payment_intent(self, amount, currency, metadata):
        """Create a payment intent. Returns PaymentResult."""
        pass

    @abstractmethod
    def verify_payment(self, payment_id):
        """Verify a payment status. Returns PaymentResult."""
        pass


class StripeAdapter(PaymentGateway):
    """Stripe payment gateway adapter. Requires stripe package and STRIPE_SECRET_KEY."""

    def __init__(self, secret_key=None):
        self.secret_key = secret_key

    def create_payment_intent(self, amount, currency, metadata):
        try:
            import stripe
            stripe.api_key = self.secret_key
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100),  # Stripe uses cents
                currency=currency,
                metadata=metadata,
            )
            return PaymentResult(success=True, payment_id=intent.id, client_secret=intent.client_secret)
        except Exception as e:
            return PaymentResult(success=False, error=str(e))

    def verify_payment(self, payment_id):
        try:
            import stripe
            stripe.api_key = self.secret_key
            intent = stripe.PaymentIntent.retrieve(payment_id)
            return PaymentResult(
                success=intent.status == 'succeeded',
                payment_id=payment_id,
                error='' if intent.status == 'succeeded' else f'Status: {intent.status}'
            )
        except Exception as e:
            return PaymentResult(success=False, error=str(e))


class MockPaymentGateway(PaymentGateway):
    """Mock gateway for development/testing. Always succeeds."""

    def create_payment_intent(self, amount, currency, metadata):
        import secrets
        return PaymentResult(success=True, payment_id=f'mock_{secrets.token_hex(8)}', client_secret='mock_secret')

    def verify_payment(self, payment_id):
        return PaymentResult(success=True, payment_id=payment_id)


class PaymentService:
    def __init__(self, gateway=None):
        self.gateway = gateway or MockPaymentGateway()

    def process_deposit(self, booking):
        """Create payment intent for booking deposit. Returns PaymentResult."""
        if booking.deposit_amount <= 0:
            # No deposit required — auto-confirm
            booking.status = 'confirmed'
            db.session.commit()
            return PaymentResult(success=True, payment_id='no_deposit')

        result = self.gateway.create_payment_intent(
            amount=booking.deposit_amount,
            currency='gel',
            metadata={'booking_id': booking.id, 'venue_id': booking.venue_id}
        )

        if result.success:
            booking.payment_intent_id = result.payment_id
            db.session.commit()

        return result

    def confirm_payment(self, booking):
        """Confirm payment and update booking status."""
        if booking.payment_intent_id:
            result = self.gateway.verify_payment(booking.payment_intent_id)
            if result.success:
                booking.status = 'confirmed'
                db.session.commit()
                return result
            return result

        return PaymentResult(success=False, error='No payment intent')

    def handle_webhook(self, payload):
        """Handle payment webhook (Stripe). Update booking status."""
        payment_id = payload.get('payment_intent_id')
        if not payment_id:
            return

        booking = Booking.query.filter_by(payment_intent_id=payment_id).first()
        if booking and booking.status == 'pending_payment':
            event_type = payload.get('type', '')
            if event_type == 'payment_intent.succeeded':
                booking.status = 'confirmed'
            elif event_type == 'payment_intent.payment_failed':
                pass  # Keep pending_payment
            db.session.commit()
