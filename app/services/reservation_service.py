from datetime import datetime, timedelta, date, time

from sqlalchemy import and_

from app import db
from app.models import Booking, RestaurantTable, ReservationSettings, BOOKING_DURATION


class ReservationService:

    @staticmethod
    def check_overlap(table_id, booking_date, start_time, for_update=False):
        """Check if a booking would overlap with existing bookings.

        Uses half-open interval [start, start+3h).
        for_update=True uses SELECT FOR UPDATE (only during booking creation).

        Returns True if an overlap exists, False otherwise.
        """
        end_time = (datetime.combine(booking_date, start_time) + BOOKING_DURATION).time()

        query = Booking.query
        if for_update:
            query = query.with_for_update()

        overlap_count = (
            query
            .filter(
                and_(
                    Booking.table_id == table_id,
                    Booking.booking_date == booking_date,
                    Booking.status.in_(['pending_payment', 'confirmed']),
                    # existing booking starts before requested window ends
                    Booking.time_slot < end_time,
                )
            )
            .filter(
                # existing booking ends after requested window starts
                # i.e. existing_start + 3h > requested_start
                Booking.time_slot > (datetime.combine(booking_date, start_time) - BOOKING_DURATION).time()
            )
            .count()
        )
        return overlap_count > 0

    @staticmethod
    def get_available_tables(venue_id, date_val, time_slot, guest_count):
        """Return tables with capacity >= guest_count that have no overlapping bookings."""
        all_tables = (
            RestaurantTable.query
            .filter_by(venue_id=venue_id, is_active=True)
            .filter(RestaurantTable.capacity >= guest_count)
            .all()
        )

        available = []
        for table in all_tables:
            if not ReservationService.check_overlap(table.id, date_val, time_slot):
                available.append(table)
        return available

    @staticmethod
    def auto_assign_table(venue_id, date_val, time_slot, guest_count):
        """Select the available table with smallest capacity >= guest_count.

        Returns None if no table fits.
        """
        available_tables = ReservationService.get_available_tables(
            venue_id, date_val, time_slot, guest_count
        )
        if not available_tables:
            return None

        # Pick the table with the smallest capacity that still fits
        return min(available_tables, key=lambda t: t.capacity)

    @staticmethod
    def create_booking(venue_id, data):
        """Create a booking with overlap check.

        Sets status='pending_payment'. Gets deposit from ReservationSettings.

        data dict contains: table_id (optional), customer_id, booking_date,
        time_slot, guest_count, guest_name, guest_email, guest_phone,
        comment, language.

        If no table_id provided, auto-assigns a table.
        Raises ValueError on validation failures.
        """
        booking_date = data.get('booking_date')
        time_slot_val = data.get('time_slot')
        guest_count = data.get('guest_count')
        customer_id = data.get('customer_id')
        table_id = data.get('table_id')

        if not booking_date or not time_slot_val or not guest_count or not customer_id:
            raise ValueError("Missing required booking fields: booking_date, time_slot, guest_count, customer_id")

        # Parse date/time if provided as strings
        if isinstance(booking_date, str):
            booking_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
        if isinstance(time_slot_val, str):
            booking_date_time_parts = time_slot_val.split(':')
            time_slot_val = time(int(booking_date_time_parts[0]), int(booking_date_time_parts[1]))

        # Reject past time slots
        now = datetime.utcnow()
        booking_datetime = datetime.combine(booking_date, time_slot_val)
        if booking_datetime <= now:
            raise ValueError("Cannot book a time slot in the past")

        # Auto-assign table if not provided
        if not table_id:
            table = ReservationService.auto_assign_table(
                venue_id, booking_date, time_slot_val, guest_count
            )
            if table is None:
                raise ValueError("No available tables for the selected time slot and guest count")
            table_id = table.id
        else:
            # Verify the table exists and belongs to the venue
            table = RestaurantTable.query.filter_by(id=table_id, venue_id=venue_id, is_active=True).first()
            if not table:
                raise ValueError("Table not found or not available")
            if table.capacity < guest_count:
                raise ValueError("Table capacity is less than guest count")

        # Check for overlap (within transaction for Postgres FOR UPDATE)
        try:
            if ReservationService.check_overlap(table_id, booking_date, time_slot_val, for_update=True):
                raise ValueError("Table is already booked for the selected time slot")
        except Exception as e:
            if 'FOR UPDATE' in str(e) or 'outside of transaction' in str(e):
                # Fallback without FOR UPDATE (e.g. some Postgres configs)
                if ReservationService.check_overlap(table_id, booking_date, time_slot_val, for_update=False):
                    raise ValueError("Table is already booked for the selected time slot")
            else:
                raise

        # Get deposit amount from venue settings
        settings = ReservationSettings.query.filter_by(venue_id=venue_id).first()
        deposit_amount = settings.deposit_amount if settings else 0.0

        booking = Booking(
            venue_id=venue_id,
            table_id=table_id,
            customer_id=customer_id,
            booking_date=booking_date,
            time_slot=time_slot_val,
            guest_count=guest_count,
            guest_name=data.get('guest_name', ''),
            guest_email=data.get('guest_email', ''),
            guest_phone=data.get('guest_phone', ''),
            comment=data.get('comment'),
            status='pending_payment',
            language=data.get('language', 'ka'),
            deposit_amount=deposit_amount,
        )

        db.session.add(booking)
        db.session.commit()
        return booking

    @staticmethod
    def cancel_booking(booking_id, cancelled_by='customer'):
        """Cancel a booking.

        If cancelled_by='customer', enforce 2-hour restriction:
        cannot cancel if time_slot is less than 2 hours away.
        Sets status='cancelled'.
        Raises ValueError on failures.
        """
        booking = Booking.query.get(booking_id)
        if not booking:
            raise ValueError("Booking not found")

        if booking.status == 'cancelled':
            raise ValueError("Booking is already cancelled")

        if cancelled_by == 'customer':
            booking_datetime = datetime.combine(booking.booking_date, booking.time_slot)
            now = datetime.utcnow()
            time_until_booking = booking_datetime - now

            if time_until_booking < timedelta(hours=2):
                raise ValueError("Cannot cancel a booking less than 2 hours before the time slot")

        booking.status = 'cancelled'
        db.session.commit()
        return booking

    @staticmethod
    def get_bookings_for_venue(venue_id, filters=None):
        """Get all bookings for a venue.

        filters dict can have: date, status, table_id.
        Returns ordered by booking_date desc.
        """
        query = Booking.query.filter_by(venue_id=venue_id)

        if filters:
            if 'date' in filters and filters['date']:
                filter_date = filters['date']
                if isinstance(filter_date, str):
                    filter_date = datetime.strptime(filter_date, '%Y-%m-%d').date()
                query = query.filter(Booking.booking_date == filter_date)

            if 'status' in filters and filters['status']:
                query = query.filter(Booking.status == filters['status'])

            if 'table_id' in filters and filters['table_id']:
                query = query.filter(Booking.table_id == filters['table_id'])

        return query.order_by(Booking.booking_date.desc()).all()

    @staticmethod
    def get_customer_bookings(customer_id):
        """Get all bookings for a customer, ordered by booking_date desc."""
        return (
            Booking.query
            .filter_by(customer_id=customer_id)
            .order_by(Booking.booking_date.desc())
            .all()
        )

    @staticmethod
    def expire_pending_bookings():
        """Find all bookings with status='pending_payment' created more than
        15 minutes ago. Set status='expired'.

        Returns the number of expired bookings.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=15)

        pending_bookings = (
            Booking.query
            .filter(
                and_(
                    Booking.status == 'pending_payment',
                    Booking.created_at <= cutoff,
                )
            )
            .all()
        )

        count = 0
        for booking in pending_bookings:
            booking.status = 'expired'
            count += 1

        if count > 0:
            db.session.commit()

        return count
