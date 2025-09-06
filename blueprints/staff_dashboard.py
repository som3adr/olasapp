from flask import Blueprint, render_template, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Tenant, Bed, TenantService, Service, Payment
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_

staff_dashboard_bp = Blueprint('staff_dashboard', __name__, url_prefix='/staff-dashboard')


@staff_dashboard_bp.route('/')
@login_required
def index():
    """Staff dashboard - operational focus without financial data"""
    # Only allow non-admin users to access the staff dashboard
    if current_user.is_admin:
        flash('Access denied. Admin users should use the admin dashboard.', 'error')
        return redirect(url_for('dashboard.index'))
    
    # Get today's date
    today = date.today()
    
    # Guest statistics (non-financial)
    total_guests = Tenant.query.count()
    active_guests = Tenant.query.filter(Tenant.is_active == True).count()
    inactive_guests = total_guests - active_guests
    
    # Check-in/out statistics
    checkins_today = Tenant.query.filter(
        func.date(Tenant.start_date) == today
    ).count()
    
    checkouts_today = Tenant.query.filter(
        and_(
            func.date(Tenant.end_date) == today,
            Tenant.is_active == False
        )
    ).count()
    
    # Bed occupancy
    total_beds = Bed.query.count()
    occupied_beds = Bed.query.filter(Bed.is_occupied == True).count()
    
    # Recent guests (last 7 days)
    week_ago = today - timedelta(days=7)
    recent_guests = Tenant.query.filter(
        Tenant.start_date >= week_ago
    ).order_by(Tenant.start_date.desc()).limit(5).all()
    
    # Upcoming checkouts (next 3 days)
    upcoming_checkouts = Tenant.query.filter(
        and_(
            Tenant.end_date <= today + timedelta(days=3),
            Tenant.end_date >= today,
            Tenant.is_active == True
        )
    ).order_by(Tenant.end_date.asc()).all()
    
    # Guest services statistics
    total_services = TenantService.query.count()
    active_services = TenantService.query.filter(
        and_(
            TenantService.start_date <= today,
            TenantService.end_date >= today
        )
    ).count()
    
    # Popular services
    popular_services = db.session.query(
        Service.name,
        func.count(TenantService.id).label('count')
    ).join(TenantService).group_by(Service.name).order_by(
        func.count(TenantService.id).desc()
    ).limit(5).all()
    
    # Guest duration statistics - calculate manually to avoid PostgreSQL EXTRACT issues
    completed_guests = Tenant.query.filter(
        and_(
            Tenant.end_date.isnot(None),
            Tenant.is_active == False
        )
    ).all()
    
    if completed_guests:
        total_days = sum((guest.end_date - guest.start_date).days for guest in completed_guests)
        avg_duration = total_days / len(completed_guests)
    else:
        avg_duration = 0
    
    return render_template('staff_dashboard/index.html',
                         total_guests=total_guests,
                         active_guests=active_guests,
                         inactive_guests=inactive_guests,
                         checkins_today=checkins_today,
                         checkouts_today=checkouts_today,
                         total_beds=total_beds,
                         occupied_beds=occupied_beds,
                         recent_guests=recent_guests,
                         upcoming_checkouts=upcoming_checkouts,
                         total_services=total_services,
                         active_services=active_services,
                         popular_services=popular_services,
                         avg_duration=round(avg_duration, 1),
                         today=today,
                         timedelta=timedelta)


@staff_dashboard_bp.route('/api/occupancy-data')
@login_required
def occupancy_data():
    """API endpoint for bed occupancy chart data"""
    # Only allow non-admin users to access staff dashboard API
    if current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get occupancy data for the last 7 days
    today = date.today()
    occupancy_data = []
    
    for i in range(7):
        check_date = today - timedelta(days=i)
        
        # Count occupied beds on this date
        occupied = db.session.query(func.count(Tenant.id)).filter(
            and_(
                Tenant.start_date <= check_date,
                Tenant.end_date >= check_date,
                Tenant.is_active == True
            )
        ).scalar()
        
        total_beds = Bed.query.count()
        occupancy_rate = (occupied / total_beds * 100) if total_beds > 0 else 0
        
        occupancy_data.append({
            'date': check_date.strftime('%Y-%m-%d'),
            'day': check_date.strftime('%a'),
            'occupied': occupied,
            'total': total_beds,
            'occupancy_rate': round(occupancy_rate, 1)
        })
    
    return jsonify({
        'success': True,
        'data': list(reversed(occupancy_data))  # Reverse to show oldest to newest
    })


@staff_dashboard_bp.route('/api/guest-activity')
@login_required
def guest_activity():
    """API endpoint for guest activity data"""
    # Only allow non-admin users to access staff dashboard API
    if current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    # Get guest activity for the last 7 days
    today = date.today()
    activity_data = []
    
    for i in range(7):
        check_date = today - timedelta(days=i)
        
        # Count check-ins and check-outs for this date
        checkins = Tenant.query.filter(
            func.date(Tenant.start_date) == check_date
        ).count()
        
        checkouts = Tenant.query.filter(
            and_(
                func.date(Tenant.end_date) == check_date,
                Tenant.is_active == False
            )
        ).count()
        
        activity_data.append({
            'date': check_date.strftime('%Y-%m-%d'),
            'day': check_date.strftime('%a'),
            'checkins': checkins,
            'checkouts': checkouts
        })
    
    return jsonify({
        'success': True,
        'data': list(reversed(activity_data))  # Reverse to show oldest to newest
    })
