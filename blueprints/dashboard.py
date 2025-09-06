from flask import Blueprint, render_template, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import Tenant, Expense, Income, Payment, CashFlow, InventoryItem, Bed, Stay
from extensions import db
from sqlalchemy import func, extract
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/')
@login_required
def index():
    # Only allow admin users to access the admin dashboard
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('staff_dashboard.index'))
    # Get current month and year
    current_date = datetime.now()
    current_month = current_date.month
    current_year = current_date.year
    
    # Calculate financial metrics
    total_active_guests = Tenant.query.filter_by(is_active=True).count()
    
    # Monthly income from rent payments
    monthly_income = db.session.query(func.sum(Payment.amount)).filter(
        extract('month', Payment.payment_date) == current_month,
        extract('year', Payment.payment_date) == current_year
    ).scalar() or 0
    
    # Monthly expenses
    monthly_expenses = db.session.query(func.sum(Expense.amount)).filter(
        extract('month', Expense.date) == current_month,
        extract('year', Expense.date) == current_year
    ).scalar() or 0
    
    # Net income for the month
    net_income = monthly_income - monthly_expenses
    
    # Calculate monthly profit (income - expenses)
    monthly_profit = monthly_income - monthly_expenses
    
    # Key hostel metrics for modern dashboard
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    
    # Payment metrics
    total_payments = db.session.query(func.sum(Payment.amount)).filter(
        func.date(Payment.payment_date) == today
    ).scalar() or 0
    
    # Calculate payment percentage change from yesterday
    yesterday_payments = db.session.query(func.sum(Payment.amount)).filter(
        func.date(Payment.payment_date) == yesterday
    ).scalar() or 0
    
    if yesterday_payments > 0:
        payment_percentage_change = ((total_payments - yesterday_payments) / yesterday_payments) * 100
    else:
        payment_percentage_change = 100 if total_payments > 0 else 0
    
    # Calculate pending payments - guests with outstanding balances
    # Get all active guests with outstanding balances
    active_guests_with_balance = Tenant.query.filter(
        Tenant.is_active == True,
        Tenant.already_paid_online == False,
        Tenant.is_prepaid == False
    ).all()
    
    pending_payments = 0
    for guest in active_guests_with_balance:
        # Calculate total amount owed
        total_owed = guest.total_amount
        
        # Calculate total paid
        total_paid = db.session.query(func.sum(Payment.amount)).filter(
            Payment.tenant_id == guest.id
        ).scalar() or 0
        
        # If there's still a balance owed, count as pending
        if total_owed > total_paid:
            pending_payments += 1
    
    # Calculate pending payments percentage change from yesterday
    yesterday_pending = 0
    # For simplicity, we'll use a different approach - count guests who should have paid by yesterday
    yesterday_guests_with_balance = Tenant.query.filter(
        Tenant.is_active == True,
        Tenant.already_paid_online == False,
        Tenant.is_prepaid == False,
        Tenant.start_date <= yesterday  # Started before yesterday
    ).all()
    
    for guest in yesterday_guests_with_balance:
        total_owed = guest.total_amount
        total_paid = db.session.query(func.sum(Payment.amount)).filter(
            Payment.tenant_id == guest.id
        ).scalar() or 0
        if total_owed > total_paid:
            yesterday_pending += 1
    
    if yesterday_pending > 0:
        pending_percentage_change = ((pending_payments - yesterday_pending) / yesterday_pending) * 100
    else:
        pending_percentage_change = -100 if pending_payments > 0 else 0
    
    # Calculate guest percentage change from last week
    last_week_guests = Tenant.query.filter(
        Tenant.start_date <= last_week,
        Tenant.end_date >= last_week,
        Tenant.is_active == True
    ).count()
    
    if last_week_guests > 0:
        guest_percentage_change = ((total_active_guests - last_week_guests) / last_week_guests) * 100
    else:
        guest_percentage_change = 100 if total_active_guests > 0 else 0
    
    # Upcoming checkouts (next 3 days)
    upcoming_checkouts = Tenant.query.filter(
        Tenant.end_date.between(today, today + timedelta(days=3)),
        Tenant.is_active == True
    ).count()
    
    # Find the nearest checkout date
    nearest_checkout = Tenant.query.filter(
        Tenant.end_date >= today,
        Tenant.is_active == True
    ).order_by(Tenant.end_date.asc()).first()
    
    if nearest_checkout:
        days_until_checkout = (nearest_checkout.end_date - today).days
        if days_until_checkout == 0:
            nearest_checkout_text = "Today"
        elif days_until_checkout == 1:
            nearest_checkout_text = "Tomorrow"
        else:
            nearest_checkout_text = f"In {days_until_checkout} days"
    else:
        nearest_checkout_text = "No checkouts"
    
    # Tasks metrics (placeholder for now)
    cleaning_tasks = 0  # Will be implemented with maintenance system
    maintenance_tasks = 0  # Will be implemented with maintenance system
    admin_tasks = 0  # Will be implemented with staff tasks system
    
    # Recent guests for activity feed
    recent_guests = Tenant.query.filter_by(is_active=True).order_by(Tenant.start_date.desc()).limit(5).all()
    
    # Recent payments for activity feed
    recent_payments = Payment.query.order_by(Payment.payment_date.desc()).limit(5).all()
    
    # Determine moment of day for greeting
    current_hour = current_date.hour
    if current_hour < 12:
        moment_of_day = 'morning'
    elif current_hour < 17:
        moment_of_day = 'afternoon'
    else:
        moment_of_day = 'evening'
    
    return render_template('dashboard/index.html',
                         total_active_guests=total_active_guests,
                         total_payments=total_payments,
                         pending_payments=pending_payments,
                         upcoming_checkouts=upcoming_checkouts,
                         cleaning_tasks=cleaning_tasks,
                         maintenance_tasks=maintenance_tasks,
                         admin_tasks=admin_tasks,
                         monthly_profit=monthly_profit,
                         recent_guests=recent_guests,
                         recent_payments=recent_payments,
                         guest_percentage_change=guest_percentage_change,
                         payment_percentage_change=payment_percentage_change,
                         pending_percentage_change=pending_percentage_change,
                         nearest_checkout_text=nearest_checkout_text,
                         moment_of_day=moment_of_day)

@dashboard_bp.route('/api/chart-data')
@login_required
def chart_data():
    # Only allow admin users to access admin dashboard API
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    # Get data for the current year (January to December)
    current_year = datetime.now().year
    
    # Monthly income and expenses for current year
    monthly_data = []
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    for month_num in range(1, 13):  # January to December
        income = db.session.query(func.sum(Payment.amount)).filter(
            extract('month', Payment.payment_date) == month_num,
            extract('year', Payment.payment_date) == current_year
        ).scalar() or 0
        
        expenses = db.session.query(func.sum(Expense.amount)).filter(
            extract('month', Expense.date) == month_num,
            extract('year', Expense.date) == current_year
        ).scalar() or 0
        
        monthly_data.append({
            'month': f'{month_names[month_num-1]} {current_year}',
            'income': float(income),
            'expenses': float(expenses),
            'net': float(income - expenses)
        })
    
    # Expense breakdown by category
    expense_categories = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total')
    ).group_by(Expense.category).all()
    
    category_data = [{'category': cat, 'amount': float(amount)} for cat, amount in expense_categories]
    
    return jsonify({
        'monthly': monthly_data,
        'categories': category_data
    })

@dashboard_bp.route('/api/revenue-data/<int:days>')
@login_required
def revenue_data(days):
    # Only allow admin users to access admin dashboard API
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    """Get revenue data for a specific number of days"""
    try:
        # Validate input
        if days <= 0 or days > 365:
            return jsonify({'error': 'Invalid number of days. Must be between 1 and 365.'}), 400
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Get daily revenue data
        daily_data = []
        current_date = start_date
        
        while current_date <= end_date:
            # Get income for this day (all payment types, not just Daily Rent)
            income = db.session.query(func.sum(Payment.amount)).filter(
                Payment.payment_date == current_date.date()
            ).scalar() or 0
            
            # Get expenses for this day
            expenses = db.session.query(func.sum(Expense.amount)).filter(
                Expense.date == current_date.date()
            ).scalar() or 0
            
            daily_data.append({
                'date': current_date.strftime('%b %d'),
                'income': float(income),
                'expenses': float(expenses),
                'net': float(income - expenses)
            })
            
            current_date += timedelta(days=1)
        
        # Add debug logging
        print(f"Revenue API: Generated {len(daily_data)} days of data")
        print(f"Sample data: {daily_data[:3] if daily_data else 'No data'}")
        
        # Check if we have any actual data
        total_income = sum(item['income'] for item in daily_data)
        total_expenses = sum(item['expenses'] for item in daily_data)
        
        print(f"Total income: {total_income}, Total expenses: {total_expenses}")
        
        return jsonify({
            'labels': [item['date'] for item in daily_data],
            'income': [item['income'] for item in daily_data],
            'expenses': [item['expenses'] for item in daily_data],
            'net': [item['net'] for item in daily_data],
            'summary': {
                'total_income': total_income,
                'total_expenses': total_expenses,
                'total_net': total_income - total_expenses,
                'days_with_data': len([d for d in daily_data if d['income'] > 0 or d['expenses'] > 0])
            }
        })
        
    except Exception as e:
        print(f"Error in revenue_data API: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@dashboard_bp.route('/api/test-data')
@login_required
def test_data():
    # Only allow admin users to access admin dashboard API
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    """Test endpoint to verify API functionality"""
    try:
        # Get some sample data to verify database connections
        total_payments = db.session.query(func.count(Payment.id)).scalar() or 0
        total_expenses = db.session.query(func.count(Expense.id)).scalar() or 0
        total_tenants = db.session.query(func.count(Tenant.id)).scalar() or 0
        
        # Get sample payment data
        sample_payments = db.session.query(
            Payment.payment_date,
            Payment.amount,
            Payment.payment_type
        ).limit(5).all()
        
        payment_data = []
        for payment in sample_payments:
            payment_data.append({
                'date': payment.payment_date.isoformat() if payment.payment_date else None,
                'amount': float(payment.amount) if payment.amount else 0,
                'type': payment.payment_type
            })
        
        return jsonify({
            'status': 'success',
            'message': 'Test endpoint working',
            'counts': {
                'payments': total_payments,
                'expenses': total_expenses,
                'tenants': total_tenants
            },
            'sample_payments': payment_data
        })
        
    except Exception as e:
        print(f"Error in test_data API: {str(e)}")
        return jsonify({'error': f'Test failed: {str(e)}'}), 500
