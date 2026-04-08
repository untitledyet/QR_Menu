"""Notification service for reservation emails."""
import secrets
from datetime import datetime
from flask import current_app, render_template_string


# Simple email templates (inline for now, can be moved to files later)
TEMPLATES = {
    'confirmation': {
        'ka': {
            'subject': 'ჯავშნის დადასტურება — {venue_name}',
            'body': '''
<h2>ჯავშანი დადასტურებულია!</h2>
<p><strong>რესტორანი:</strong> {venue_name}</p>
<p><strong>თარიღი:</strong> {date}</p>
<p><strong>დრო:</strong> {time_slot}</p>
<p><strong>მაგიდა:</strong> {table_label}</p>
<p><strong>სტუმრები:</strong> {guest_count}</p>
<p><a href="{cancel_url}">ჯავშნის გაუქმება</a></p>
'''
        },
        'en': {
            'subject': 'Booking Confirmation — {venue_name}',
            'body': '''
<h2>Booking Confirmed!</h2>
<p><strong>Restaurant:</strong> {venue_name}</p>
<p><strong>Date:</strong> {date}</p>
<p><strong>Time:</strong> {time_slot}</p>
<p><strong>Table:</strong> {table_label}</p>
<p><strong>Guests:</strong> {guest_count}</p>
<p><a href="{cancel_url}">Cancel Booking</a></p>
'''
        }
    },
    'cancellation': {
        'ka': {
            'subject': 'ჯავშანი გაუქმებულია — {venue_name}',
            'body': '<h2>ჯავშანი გაუქმებულია</h2><p>თქვენი ჯავშანი {date} {time_slot}-ზე გაუქმდა.</p>'
        },
        'en': {
            'subject': 'Booking Cancelled — {venue_name}',
            'body': '<h2>Booking Cancelled</h2><p>Your booking for {date} at {time_slot} has been cancelled.</p>'
        }
    },
    'reminder': {
        'ka': {
            'subject': 'შეხსენება — ჯავშანი ხვალ {venue_name}',
            'body': '<h2>შეხსენება</h2><p>ხვალ {time_slot}-ზე გაქვთ ჯავშანი {venue_name}-ში. მაგიდა: {table_label}, სტუმრები: {guest_count}.</p>'
        },
        'en': {
            'subject': 'Reminder — Booking tomorrow at {venue_name}',
            'body': '<h2>Reminder</h2><p>You have a booking tomorrow at {time_slot} at {venue_name}. Table: {table_label}, Guests: {guest_count}.</p>'
        }
    }
}


class NotificationService:

    @staticmethod
    def generate_cancellation_token(booking_id):
        """Generate a unique cancellation token for a booking."""
        from app.models import Booking
        from app import db

        token = secrets.token_urlsafe(32)
        booking = Booking.query.get(booking_id)
        if booking:
            booking.cancellation_token = token
            db.session.commit()
        return token

    @staticmethod
    def verify_cancellation_token(token):
        """Verify a cancellation token. Returns booking_id or None."""
        from app.models import Booking
        booking = Booking.query.filter_by(cancellation_token=token).first()
        if booking and booking.status in ('pending_payment', 'confirmed'):
            return booking.id
        return None

    @staticmethod
    def _get_booking_context(booking):
        """Build template context from a booking."""
        return {
            'venue_name': booking.venue.name if booking.venue else '',
            'date': str(booking.booking_date),
            'time_slot': booking.time_slot.strftime('%H:%M') if booking.time_slot else '',
            'table_label': booking.table.label if booking.table else '',
            'guest_count': booking.guest_count,
            'cancel_url': f'/api/{booking.venue.slug}/reservations/cancel/{booking.cancellation_token}' if booking.cancellation_token else '',
        }

    @staticmethod
    def _render_email(template_key, booking):
        """Render an email template in the booking's language."""
        lang = booking.language or 'ka'
        template = TEMPLATES.get(template_key, {}).get(lang, TEMPLATES.get(template_key, {}).get('en', {}))
        context = NotificationService._get_booking_context(booking)

        subject = template.get('subject', '').format(**context)
        body = template.get('body', '').format(**context)
        return subject, body

    @staticmethod
    def send_booking_confirmation(booking):
        """Send confirmation email. Non-blocking — logs errors but doesn't raise."""
        if not booking.cancellation_token:
            NotificationService.generate_cancellation_token(booking.id)
            from app import db
            db.session.refresh(booking)

        subject, body = NotificationService._render_email('confirmation', booking)
        NotificationService._send_email(booking.guest_email, subject, body)

    @staticmethod
    def send_booking_cancellation(booking):
        """Send cancellation confirmation email."""
        subject, body = NotificationService._render_email('cancellation', booking)
        NotificationService._send_email(booking.guest_email, subject, body)

    @staticmethod
    def send_booking_reminder(booking):
        """Send reminder email 24h before booking."""
        subject, body = NotificationService._render_email('reminder', booking)
        NotificationService._send_email(booking.guest_email, subject, body)

    @staticmethod
    def _send_email(to, subject, html_body):
        """Send an email. Uses Flask-Mail if configured, otherwise logs."""
        try:
            # Try Flask-Mail if available
            from flask_mail import Message
            mail = current_app.extensions.get('mail')
            if mail:
                msg = Message(subject=subject, recipients=[to], html=html_body)
                mail.send(msg)
                current_app.logger.info(f'Email sent to {to}: {subject}')
                return
        except (ImportError, Exception):
            pass

        # Fallback: just log
        current_app.logger.info(f'[EMAIL] To: {to}, Subject: {subject}')
