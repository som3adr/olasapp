from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Bed, Tenant, Stay, CheckInOut
from permissions import require_frontdesk_or_admin
from datetime import datetime, timedelta
import calendar

booking_calendar_bp = Blueprint('booking_calendar', __name__, url_prefix='/booking-calendar')

@booking_calendar_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    """Booking calendar main view"""
    # Get current month or requested month
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    # Validate month/year
    if month < 1 or month > 12:
        month = datetime.now().month
    if year < 2020 or year > 2030:
        year = datetime.now().year
    
    # Get calendar data
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]
    
    # Get all rooms and beds
    beds = Bed.query.order_by(Bed.bed_number).all()
    
    # Get bookings for this month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # Get all check-ins and check-outs for the month
    checkins = CheckInOut.query.filter(
        CheckInOut.check_in_date >= start_date,
        CheckInOut.check_in_date <= end_date
    ).all()
    
    checkouts = CheckInOut.query.filter(
        CheckInOut.actual_check_out_date >= start_date,
        CheckInOut.actual_check_out_date <= end_date,
        CheckInOut.actual_check_out_date.isnot(None)
    ).all()
    
    # Get current occupancy
    current_occupancy = CheckInOut.query.filter(
        CheckInOut.check_in_date <= end_date,
        db.or_(
            CheckInOut.actual_check_out_date.is_(None),
            CheckInOut.actual_check_out_date >= start_date
        )
    ).all()
    
    # Calculate availability for each day
    availability_data = {}
    for week in cal:
        for day in week:
            if day == 0:
                continue
            
            date_obj = datetime(year, month, day)
            date_str = date_obj.strftime('%Y-%m-%d')
            
            # Count available beds for this day
            total_beds = sum(len(room.beds) for room in rooms)
            occupied_beds = 0
            
            for occupancy in current_occupancy:
                if (occupancy.check_in_date <= date_obj and 
                    (occupancy.actual_check_out_date is None or occupancy.actual_check_out_date >= date_obj)):
                    occupied_beds += 1
            
            available_beds = total_beds - occupied_beds
            occupancy_rate = (occupied_beds / total_beds * 100) if total_beds > 0 else 0
            
            availability_data[date_str] = {
                'total_beds': total_beds,
                'occupied_beds': occupied_beds,
                'available_beds': available_beds,
                'occupancy_rate': occupancy_rate,
                'checkins': [c for c in checkins if c.check_in_date.date() == date_obj.date()],
                'checkouts': [c for c in checkouts if c.actual_check_out_date and c.actual_check_out_date.date() == date_obj.date()]
            }
    
    # Navigation dates
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    return render_template('booking_calendar/index.html',
                         calendar=cal,
                         year=year,
                         month=month,
                         month_name=month_name,
                         rooms=rooms,
                         availability_data=availability_data,
                         prev_month=prev_month,
                         prev_year=prev_year,
                         next_month=next_month,
                         next_year=next_year)

@booking_calendar_bp.route('/room-calendar/<int:room_id>')
@login_required
@require_frontdesk_or_admin
def room_calendar(room_id):
    """Detailed calendar view for a specific room"""
    bed = Bed.query.get_or_404(bed_id)
    
    # Get current month or requested month
    year = request.args.get('year', datetime.now().year, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    
    # Validate month/year
    if month < 1 or month > 12:
        month = datetime.now().month
    if year < 2020 or year > 2030:
        year = datetime.now().year
    
    # Get calendar data
    cal = calendar.monthcalendar(year, month)
    month_name = calendar.month_name[month]
    
    # Get bookings for this month for this room
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # Get occupancy data for each bed in this room
    bed_occupancy = {}
    for bed in room.beds:
        bed_occupancy[bed.id] = CheckInOut.query.filter(
            CheckInOut.bed_id == bed.id,
            CheckInOut.check_in_date <= end_date,
            db.or_(
                CheckInOut.actual_check_out_date.is_(None),
                CheckInOut.actual_check_out_date >= start_date
            )
        ).all()
    
    # Calculate daily availability for each bed
    bed_availability = {}
    for week in cal:
        for day in week:
            if day == 0:
                continue
            
            date_obj = datetime(year, month, day)
            date_str = date_obj.strftime('%Y-%m-%d')
            
            bed_availability[date_str] = {}
            for bed in room.beds:
                is_occupied = False
                current_guest = None
                
                for occupancy in bed_occupancy.get(bed.id, []):
                    if (occupancy.check_in_date <= date_obj and 
                        (occupancy.actual_check_out_date is None or occupancy.actual_check_out_date >= date_obj)):
                        is_occupied = True
                        current_guest = occupancy.tenant
                        break
                
                bed_availability[date_str][bed.id] = {
                    'is_occupied': is_occupied,
                    'guest': current_guest,
                    'bed': bed
                }
    
    # Navigation dates
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    return render_template('booking_calendar/room_calendar.html',
                         room=room,
                         calendar=cal,
                         year=year,
                         month=month,
                         month_name=month_name,
                         bed_availability=bed_availability,
                         prev_month=prev_month,
                         prev_year=prev_year,
                         next_month=next_month,
                         next_year=next_year)

@booking_calendar_bp.route('/api/availability/<date>')
@login_required
def api_availability(date):
    """API endpoint to get availability for a specific date"""
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    # Get all rooms and beds
    beds = Bed.query.order_by(Bed.bed_number).all()
    
    # Get current occupancy for this date
    current_occupancy = CheckInOut.query.filter(
        CheckInOut.check_in_date <= date_obj,
        db.or_(
            CheckInOut.actual_check_out_date.is_(None),
            CheckInOut.actual_check_out_date >= date_obj
        )
    ).all()
    
    # Build availability data
    availability = {
        'date': date,
        'rooms': []
    }
    
    for room in rooms:
        room_data = {
            'id': room.id,
            'room_number': room.room_number,
            'capacity': room.capacity,
            'beds': []
        }
        
        for bed in room.beds:
            is_occupied = False
            current_guest = None
            
            for occupancy in current_occupancy:
                if occupancy.bed_id == bed.id:
                    is_occupied = True
                    current_guest = {
                        'id': occupancy.tenant.id,
                        'name': occupancy.tenant.name,
                        'check_in': occupancy.check_in_date.strftime('%Y-%m-%d'),
                        'check_out': occupancy.actual_check_out_date.strftime('%Y-%m-%d') if occupancy.actual_check_out_date else None
                    }
                    break
            
            bed_data = {
                'id': bed.id,
                'bed_number': bed.bed_number,
                'places': bed.places,
                'status': bed.status,
                'is_occupied': is_occupied,
                'guest': current_guest
            }
            
            room_data['beds'].append(bed_data)
        
        availability['rooms'].append(room_data)
    
    return jsonify(availability)

@booking_calendar_bp.route('/quick-book', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def quick_book():
    """Quick booking from calendar view"""
    bed_id = request.form.get('bed_id', type=int)
    check_in_date = request.form.get('check_in_date')
    guest_name = request.form.get('guest_name')
    guest_email = request.form.get('guest_email', '')
    guest_phone = request.form.get('guest_phone', '')
    daily_rate = request.form.get('daily_rate', type=float)
    
    if not all([bed_id, check_in_date, guest_name, daily_rate]):
        flash('All required fields must be filled.', 'error')
        return redirect(url_for('booking_calendar.index'))
    
    try:
        check_in_dt = datetime.strptime(check_in_date, '%Y-%m-%d')
    except ValueError:
        flash('Invalid check-in date format.', 'error')
        return redirect(url_for('booking_calendar.index'))
    
    # Check if bed exists and is available
    bed = Bed.query.get(bed_id)
    if not bed:
        flash('Bed not found.', 'error')
        return redirect(url_for('booking_calendar.index'))
    
    # Check if bed is already occupied on this date
    existing_booking = CheckInOut.query.filter(
        CheckInOut.bed_id == bed_id,
        CheckInOut.check_in_date <= check_in_dt,
        db.or_(
            CheckInOut.actual_check_out_date.is_(None),
            CheckInOut.actual_check_out_date >= check_in_dt
        )
    ).first()
    
    if existing_booking:
        flash('Bed is already occupied on this date.', 'error')
        return redirect(url_for('booking_calendar.index'))
    
    try:
        # Create or find guest
        guest = Tenant.query.filter_by(name=guest_name, email=guest_email).first()
        if not guest:
            guest = Tenant(
                name=guest_name,
                email=guest_email,
                phone=guest_phone,
                is_active=True
            )
            db.session.add(guest)
            db.session.flush()  # Get the ID
        
        # Create stay record
        stay = Stay(
            tenant_id=guest.id,
            daily_rate=daily_rate,
            stay_type='daily'
        )
        db.session.add(stay)
        db.session.flush()
        
        # Create check-in record
        checkin = CheckInOut(
            tenant_id=guest.id,
            bed_id=bed_id,
            check_in_date=check_in_dt,
            expected_check_out_date=check_in_dt + timedelta(days=1),  # Default 1 day stay
            checked_in_by=current_user.id,
            notes=f'Quick booking from calendar'
        )
        db.session.add(checkin)
        
        # Update bed status
        bed.tenant_id = guest.id
        bed.status = 'occupied'
        
        db.session.commit()
        
        flash(f'Successfully booked {guest_name} into Room {bed.room.room_number}, Bed {bed.bed_number}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating booking: {str(e)}', 'error')
    
    return redirect(url_for('booking_calendar.index'))

@booking_calendar_bp.route('/occupancy-report')
@login_required
@require_frontdesk_or_admin
def occupancy_report():
    """Generate occupancy report for analysis"""
    # Get date range from request
    start_date_str = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('booking_calendar.index'))
    
    if end_date < start_date:
        flash('End date must be after start date.', 'error')
        return redirect(url_for('booking_calendar.index'))
    
    # Calculate daily occupancy rates
    daily_occupancy = []
    total_beds = Bed.query.count()
    
    current_date = start_date
    while current_date <= end_date:
        # Count occupied beds for this date
        occupied_beds = CheckInOut.query.filter(
            CheckInOut.check_in_date <= current_date,
            db.or_(
                CheckInOut.actual_check_out_date.is_(None),
                CheckInOut.actual_check_out_date >= current_date
            )
        ).count()
        
        occupancy_rate = (occupied_beds / total_beds * 100) if total_beds > 0 else 0
        
        daily_occupancy.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'occupied_beds': occupied_beds,
            'total_beds': total_beds,
            'available_beds': total_beds - occupied_beds,
            'occupancy_rate': round(occupancy_rate, 2)
        })
        
        current_date += timedelta(days=1)
    
    # Calculate summary statistics
    if daily_occupancy:
        avg_occupancy = sum(day['occupancy_rate'] for day in daily_occupancy) / len(daily_occupancy)
        max_occupancy = max(day['occupancy_rate'] for day in daily_occupancy)
        min_occupancy = min(day['occupancy_rate'] for day in daily_occupancy)
    else:
        avg_occupancy = max_occupancy = min_occupancy = 0
    
    return render_template('booking_calendar/occupancy_report.html',
                         daily_occupancy=daily_occupancy,
                         start_date=start_date_str,
                         end_date=end_date_str,
                         avg_occupancy=round(avg_occupancy, 2),
                         max_occupancy=round(max_occupancy, 2),
                         min_occupancy=round(min_occupancy, 2),
                         total_beds=total_beds)
