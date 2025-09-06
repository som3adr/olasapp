from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from extensions import db
from models import Payment, Expense, Income, Tenant, CheckInOut, TenantService, Service
from permissions import require_frontdesk_or_admin
from datetime import datetime, timedelta
from sqlalchemy import func, extract, and_
import calendar

financial_reports_bp = Blueprint('financial_reports', __name__, url_prefix='/financial-reports')


@financial_reports_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    """Financial reports dashboard"""
    return render_template('financial_reports/index.html')


@financial_reports_bp.route('/profit-loss')
@login_required
@require_frontdesk_or_admin
def profit_loss():
    """Profit & Loss Statement"""
    # Date range parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Default to current month if no dates provided
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Revenue calculations
    rental_income = db.session.query(func.sum(Payment.amount)).filter(
        Payment.payment_type == 'Daily Rent',
        Payment.payment_date >= start_dt,
        Payment.payment_date <= end_dt
    ).scalar() or 0
    
    service_income = db.session.query(func.sum(Payment.amount)).filter(
        Payment.payment_type == 'Service',
        Payment.payment_date >= start_dt,
        Payment.payment_date <= end_dt
    ).scalar() or 0
    
    other_income = db.session.query(func.sum(Payment.amount)).filter(
        and_(Payment.payment_type != 'Daily Rent', Payment.payment_type != 'Service'),
        Payment.payment_date >= start_dt,
        Payment.payment_date <= end_dt
    ).scalar() or 0
    
    # Additional income from Income table
    additional_income = db.session.query(func.sum(Income.amount)).filter(
        Income.date >= start_dt,
        Income.date <= end_dt
    ).scalar() or 0
    
    total_revenue = rental_income + service_income + other_income + additional_income
    
    # Expense calculations by category
    expense_breakdown = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total')
    ).filter(
        Expense.date >= start_dt,
        Expense.date <= end_dt
    ).group_by(Expense.category).all()
    
    total_expenses = sum([exp.total for exp in expense_breakdown])
    
    # Net profit
    net_profit = total_revenue - total_expenses
    profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Occupancy metrics
    total_nights = db.session.query(func.count(CheckInOut.id)).filter(
        CheckInOut.check_in_date >= start_dt,
        CheckInOut.check_in_date <= end_dt
    ).scalar() or 0
    
    # Average daily rate
    adr = rental_income / total_nights if total_nights > 0 else 0
    
    return render_template('financial_reports/profit_loss.html',
                         start_date=start_date,
                         end_date=end_date,
                         rental_income=rental_income,
                         service_income=service_income,
                         other_income=other_income,
                         additional_income=additional_income,
                         total_revenue=total_revenue,
                         expense_breakdown=expense_breakdown,
                         total_expenses=total_expenses,
                         net_profit=net_profit,
                         profit_margin=profit_margin,
                         total_nights=total_nights,
                         adr=adr)


@financial_reports_bp.route('/revenue-analysis')
@login_required
@require_frontdesk_or_admin
def revenue_analysis():
    """Revenue analysis and trends"""
    # Get monthly revenue for the last 12 months
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    monthly_revenue = []
    for i in range(12):
        month_start = (end_date.replace(day=1) - timedelta(days=30*i)).replace(day=1)
        month_end = (month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1]))
        
        revenue = db.session.query(func.sum(Payment.amount)).filter(
            Payment.payment_date >= month_start,
            Payment.payment_date <= month_end
        ).scalar() or 0
        
        monthly_revenue.append({
            'month': month_start.strftime('%b %Y'),
            'revenue': float(revenue)
        })
    
    monthly_revenue.reverse()
    
    # Revenue by source (current month)
    current_month_start = datetime.now().replace(day=1)
    
    revenue_sources_query = db.session.query(
        Payment.payment_type,
        func.sum(Payment.amount).label('total')
    ).filter(
        Payment.payment_date >= current_month_start
    ).group_by(Payment.payment_type).all()
    
    # Convert to serializable format
    revenue_sources = [{'payment_type': row.payment_type, 'total': float(row.total)} for row in revenue_sources_query]
    
    # Top guests by revenue
    top_guests_query = db.session.query(
        Tenant.name,
        func.sum(Payment.amount).label('total_paid')
    ).join(Payment).filter(
        Payment.payment_date >= current_month_start
    ).group_by(Tenant.id, Tenant.name).order_by(func.sum(Payment.amount).desc()).limit(10).all()
    
    # Convert to serializable format
    top_guests = [{'name': row.name, 'total_paid': float(row.total_paid)} for row in top_guests_query]
    
    return render_template('financial_reports/revenue_analysis.html',
                         monthly_revenue=monthly_revenue,
                         revenue_sources=revenue_sources,
                         top_guests=top_guests)


@financial_reports_bp.route('/expense-analysis')
@login_required
@require_frontdesk_or_admin
def expense_analysis():
    """Expense analysis and cost breakdown"""
    # Date range parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    
    # Monthly expense trends
    monthly_expenses = []
    current_date = start_dt
    while current_date <= end_dt:
        month_start = current_date.replace(day=1)
        month_end = month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])
        
        expenses = db.session.query(func.sum(Expense.amount)).filter(
            Expense.date >= month_start,
            Expense.date <= month_end
        ).scalar() or 0
        
        monthly_expenses.append({
            'month': month_start.strftime('%b %Y'),
            'expenses': float(expenses)
        })
        
        # Move to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)
    
    # Expense categories breakdown
    category_breakdown_query = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total'),
        func.count(Expense.id).label('count')
    ).filter(
        Expense.date >= start_dt,
        Expense.date <= end_dt
    ).group_by(Expense.category).order_by(func.sum(Expense.amount).desc()).all()
    
    # Convert to serializable format for template and chart
    category_breakdown = [{'category': row.category, 'total': float(row.total), 'count': row.count} for row in category_breakdown_query]
    
    # Recent large expenses
    large_expenses = db.session.query(Expense).filter(
        Expense.date >= start_dt,
        Expense.date <= end_dt,
        Expense.amount >= 100  # Configurable threshold
    ).order_by(Expense.amount.desc()).limit(10).all()
    
    return render_template('financial_reports/expense_analysis.html',
                         start_date=start_date,
                         end_date=end_date,
                         monthly_expenses=monthly_expenses,
                         category_breakdown=category_breakdown,
                         large_expenses=large_expenses)


@financial_reports_bp.route('/cash-flow')
@login_required
@require_frontdesk_or_admin
def cash_flow():
    """Cash flow analysis"""
    # Get daily cash flow for the last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    daily_flow = []
    current_date = start_date
    
    while current_date <= end_date:
        # Daily income
        daily_income = db.session.query(func.sum(Payment.amount)).filter(
            func.date(Payment.payment_date) == current_date.date()
        ).scalar() or 0
        
        # Daily expenses
        daily_expenses = db.session.query(func.sum(Expense.amount)).filter(
            func.date(Expense.date) == current_date.date()
        ).scalar() or 0
        
        net_flow = daily_income - daily_expenses
        
        daily_flow.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'income': float(daily_income),
            'expenses': float(daily_expenses),
            'net_flow': float(net_flow)
        })
        
        current_date += timedelta(days=1)
    
    # Calculate running balance
    running_balance = 0
    for day in daily_flow:
        running_balance += day['net_flow']
        day['running_balance'] = running_balance
    
    # Summary statistics
    total_income = sum([day['income'] for day in daily_flow])
    total_expenses = sum([day['expenses'] for day in daily_flow])
    net_cash_flow = total_income - total_expenses
    
    return render_template('financial_reports/cash_flow.html',
                         daily_flow=daily_flow,
                         total_income=total_income,
                         total_expenses=total_expenses,
                         net_cash_flow=net_cash_flow)


@financial_reports_bp.route('/api/monthly-comparison')
@login_required
@require_frontdesk_or_admin
def monthly_comparison_api():
    """API endpoint for monthly comparison chart"""
    months = []
    
    for i in range(12):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = month_date.replace(day=1)
        month_end = month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])
        
        revenue = db.session.query(func.sum(Payment.amount)).filter(
            Payment.payment_date >= month_start,
            Payment.payment_date <= month_end
        ).scalar() or 0
        
        expenses = db.session.query(func.sum(Expense.amount)).filter(
            Expense.date >= month_start,
            Expense.date <= month_end
        ).scalar() or 0
        
        months.append({
            'month': month_start.strftime('%b %Y'),
            'revenue': float(revenue),
            'expenses': float(expenses),
            'profit': float(revenue - expenses)
        })
    
    months.reverse()
    return jsonify(months)
