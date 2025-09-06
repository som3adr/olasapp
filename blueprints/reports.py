from flask import Blueprint, render_template, request, make_response, jsonify
from flask_login import login_required
from models import Expense, Income, Payment, Tenant, InventoryItem, InventoryTransaction, Stay, TenantService, Service
from extensions import db
from sqlalchemy import func, extract
from datetime import datetime, timedelta
import csv
import io
from permissions import require_admin

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
@login_required
@require_admin
def index():
    return render_template('reports/index.html')

@reports_bp.route('/guests', methods=['GET'])
@login_required
@require_admin
def guests_overview():
    # Date range inputs with defaults (current month)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    if not date_from or not date_to:
        current_date = datetime.now()
        date_from = current_date.replace(day=1).strftime('%Y-%m-%d')
        date_to = current_date.strftime('%Y-%m-%d')

    try:
        from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
    except ValueError:
        from_date = datetime.now().replace(day=1).date()
        to_date = datetime.now().date()
        date_from = from_date.strftime('%Y-%m-%d')
        date_to = to_date.strftime('%Y-%m-%d')

    # Advanced filter inputs
    q_name = request.args.get('q', '').strip()
    room = request.args.get('room', '').strip()
    stay_type_filter = request.args.get('stay_type', '').strip()
    min_total = request.args.get('min_total', '').strip()
    max_total = request.args.get('max_total', '').strip()

    query = Tenant.query.filter_by(is_active=True)
    if room:
        query = query.filter(Tenant.room_number.like(f"%{room}%"))
    if q_name:
        query = query.filter(Tenant.name.ilike(f"%{q_name}%"))
    guests = query.order_by(Tenant.room_number).all()

    # Preload services mapping
    def load_services_for_guest(guest_id: int):
        assignments = TenantService.query.filter_by(tenant_id=guest_id).all()
        if not assignments:
            return [], 0.0
        service_ids = [a.service_id for a in assignments]
        services = {s.id: s for s in Service.query.filter(Service.id.in_(service_ids)).all()}
        rows = []
        total = 0.0
        for a in assignments:
            svc = services.get(a.service_id)
            if not svc:
                continue
            unit_price = a.unit_price if a.unit_price is not None else svc.price or 0
            line_total = unit_price * (a.quantity or 1)
            total += float(line_total)
            rows.append({
                'name': a.custom_name or svc.name,
                'quantity': a.quantity or 1,
                'unit_price': unit_price,
                'line_total': line_total,
            })
        return rows, total

    rows = []
    grand_totals = {'rent_total': 0.0, 'services_total': 0.0, 'grand_total': 0.0}

    for g in guests:
        # Determine daily rate from active Stay or fallback to tenant.daily_rent
        stay = Stay.query.filter_by(tenant_id=g.id, is_active=True).first()
        daily_rate = (stay.daily_rate if stay and stay.daily_rate is not None else g.daily_rent) or 0

        # Clamp date range to guest stay window
        effective_start = max(from_date, g.start_date)
        effective_end = to_date
        if g.end_date:
            effective_end = min(effective_end, g.end_date)
        if stay and stay.start_date:
            effective_start = max(effective_start, stay.start_date)
        if stay and stay.end_date:
            effective_end = min(effective_end, stay.end_date)

        total_days = 0
        if effective_end >= effective_start:
            total_days = (effective_end - effective_start).days + 1

        # For prepaid guests, rent total should be 0
        if g.is_prepaid:
            rent_total = 0.0
        else:
            rent_total = float(daily_rate) * total_days

        # For all guests, allow services
        svc_rows, svc_total = load_services_for_guest(g.id)
        
        guest_total = rent_total + svc_total

        grand_totals['rent_total'] += rent_total
        grand_totals['services_total'] += svc_total
        grand_totals['grand_total'] += guest_total

        rows.append({
            'guest': g,
            'daily_rate': daily_rate,
            'total_days': total_days,
            'rent_total': rent_total,
            'services': svc_rows,
            'services_total': svc_total,
            'grand_total': guest_total,
            'effective_start': effective_start,
            'effective_end': effective_end,
        })

    return render_template('reports/guests.html',
                           date_from=date_from,
                           date_to=date_to,
                           guests=rows,
                           totals=grand_totals,
                           q=q_name,
                           room=room,
                           stay_type=stay_type_filter,
                           min_total=min_total,
                           max_total=max_total)

@reports_bp.route('/financial')
@login_required
@require_admin
def financial():
    # Get date range from query parameters
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Default to current month if no dates provided
    if not date_from or not date_to:
        current_date = datetime.now()
        date_from = current_date.replace(day=1).strftime('%Y-%m-%d')
        date_to = current_date.strftime('%Y-%m-%d')
    
    try:
        from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
    except ValueError:
        from_date = datetime.now().replace(day=1).date()
        to_date = datetime.now().date()
        date_from = from_date.strftime('%Y-%m-%d')
        date_to = to_date.strftime('%Y-%m-%d')
    
    # Income from rent payments
    rent_income = db.session.query(func.sum(Payment.amount)).filter(
        Payment.payment_date >= from_date,
        Payment.payment_date <= to_date
    ).scalar() or 0
    
    # Other income
    other_income = db.session.query(func.sum(Income.amount)).filter(
        Income.date >= from_date,
        Income.date <= to_date
    ).scalar() or 0
    
    total_income = rent_income + other_income
    
    # Expenses by category
    expense_breakdown = db.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total')
    ).filter(
        Expense.date >= from_date,
        Expense.date <= to_date
    ).group_by(Expense.category).all()
    
    total_expenses = sum(amount for _, amount in expense_breakdown)
    net_profit = total_income - total_expenses
    
    # Recent transactions
    recent_expenses = Expense.query.filter(
        Expense.date >= from_date,
        Expense.date <= to_date
    ).order_by(Expense.date.desc()).limit(10).all()
    
    recent_payments = Payment.query.filter(
        Payment.payment_date >= from_date,
        Payment.payment_date <= to_date
    ).order_by(Payment.payment_date.desc()).limit(10).all()
    
    return render_template('reports/financial.html',
                         date_from=date_from,
                         date_to=date_to,
                         rent_income=rent_income,
                         other_income=other_income,
                         total_income=total_income,
                         expense_breakdown=expense_breakdown,
                         total_expenses=total_expenses,
                         net_profit=net_profit,
                         recent_expenses=recent_expenses,
                         recent_payments=recent_payments)

@reports_bp.route('/export/expenses')
@login_required
@require_admin
def export_expenses():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = Expense.query
    
    if date_from:
        from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        query = query.filter(Expense.date >= from_date)
    
    if date_to:
        to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        query = query.filter(Expense.date <= to_date)
    
    expenses = query.order_by(Expense.date.desc()).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Date', 'Description', 'Category', 'Amount', 'Vendor', 'Notes'])
    
    # Write data
    for expense in expenses:
        writer.writerow([
            expense.date.strftime('%Y-%m-%d'),
            expense.description,
            expense.category,
            expense.amount,
            expense.vendor or '',
            expense.notes or ''
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=expenses_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response

@reports_bp.route('/export/payments')
@login_required
@require_admin
def export_payments():
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = db.session.query(Payment, Tenant).join(Tenant)
    
    if date_from:
        from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
        query = query.filter(Payment.payment_date >= from_date)
    
    if date_to:
        to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        query = query.filter(Payment.payment_date <= to_date)
    
    payments = query.order_by(Payment.payment_date.desc()).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Date', 'Tenant', 'Room', 'Amount', 'For Month', 'Type', 'Notes'])
    
    # Write data
    for payment, tenant in payments:
        writer.writerow([
            payment.payment_date.strftime('%Y-%m-%d'),
            tenant.name,
            tenant.room_number,
            payment.amount,
            payment.payment_for_month,
            payment.payment_type,
            payment.notes or ''
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=payments_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response

@reports_bp.route('/inventory')
@login_required
@require_admin
def inventory_report():
    items = InventoryItem.query.order_by(InventoryItem.category, InventoryItem.name).all()
    
    # Calculate inventory value and categorize items
    total_value = 0
    low_stock_items = []
    out_of_stock_items = []
    
    for item in items:
        item_value = item.current_stock * item.cost_per_unit
        total_value += item_value
        item.total_value = item_value
        
        if item.current_stock <= 0:
            out_of_stock_items.append(item)
        elif item.current_stock <= item.minimum_stock:
            low_stock_items.append(item)
    
    # Group by category
    categories = {}
    for item in items:
        if item.category not in categories:
            categories[item.category] = []
        categories[item.category].append(item)
    
    return render_template('reports/inventory.html',
                         items=items,
                         categories=categories,
                         total_value=total_value,
                         low_stock_items=low_stock_items,
                         out_of_stock_items=out_of_stock_items)

@reports_bp.route('/export/inventory')
@login_required
@require_admin
def export_inventory():
    items = InventoryItem.query.order_by(InventoryItem.name).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Name', 'Category', 'Current Stock', 'Unit', 'Minimum Stock', 
                    'Cost per Unit', 'Total Value', 'Supplier', 'Last Purchased'])
    
    # Write data
    for item in items:
        total_value = item.current_stock * item.cost_per_unit
        writer.writerow([
            item.name,
            item.category,
            item.current_stock,
            item.unit,
            item.minimum_stock,
            item.cost_per_unit,
            total_value,
            item.supplier or '',
            item.last_purchased.strftime('%Y-%m-%d') if item.last_purchased else ''
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=inventory_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response
