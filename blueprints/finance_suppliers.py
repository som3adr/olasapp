from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from models import Expense, Income, Payment, Tenant, StaffCashAdvance, CashAdvanceHistory, User, SalaryRecord, db
from extensions import db as db_ext
from datetime import datetime, date, timedelta
from sqlalchemy import func
from permissions import require_permission

finance_suppliers_bp = Blueprint('finance_suppliers', __name__, url_prefix='/finance-suppliers')

@finance_suppliers_bp.route('/')
@login_required
def index():
    """Finance & Suppliers dashboard"""
    today = date.today()
    this_month = today.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    
    # Get financial summary - remaining balance of cash advances
    monthly_cash_advances = db_ext.session.query(
        func.sum(StaffCashAdvance.amount)
    ).filter(
        StaffCashAdvance.date_given >= this_month,
        StaffCashAdvance.status.in_(['pending', 'partially_used'])
    ).scalar() or 0
    
    monthly_expenses = db_ext.session.query(
        func.sum(Expense.amount)
    ).filter(
        Expense.date >= this_month
    ).scalar() or 0
    
    monthly_payments = db_ext.session.query(
        func.sum(Payment.amount)
    ).filter(
        Payment.payment_date >= this_month
    ).scalar() or 0
    
    # Calculate profit (payments minus expenses and cash advances)
    monthly_profit = monthly_payments - monthly_expenses - monthly_cash_advances
    
    # Get recent transactions
    recent_expenses = Expense.query.order_by(Expense.date.desc()).limit(5).all()
    recent_cash_advances = StaffCashAdvance.query.order_by(StaffCashAdvance.date_given.desc()).limit(5).all()
    
    # Get expense categories summary
    expense_categories = db_ext.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total')
    ).filter(
        Expense.date >= this_month
    ).group_by(Expense.category).all()
    
    return render_template('finance_suppliers/index.html',
                         monthly_cash_advances=monthly_cash_advances,
                         monthly_expenses=monthly_expenses,
                         monthly_payments=monthly_payments,
                         monthly_profit=monthly_profit,
                         recent_expenses=recent_expenses,
                         recent_cash_advances=recent_cash_advances,
                         expense_categories=expense_categories,
                         this_month=this_month)

@finance_suppliers_bp.route('/expenses')
@login_required
@require_permission('view_supplier_expenses')
def expenses():
    """Manage expenses"""
    # Get filter parameters
    category_filter = request.args.get('category', '')
    vendor_filter = request.args.get('vendor_filter', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = Expense.query
    
    # Apply filters
    if category_filter:
        query = query.filter(Expense.category == category_filter)
    
    if vendor_filter:
        query = query.filter(Expense.vendor == vendor_filter)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Expense.date >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Expense.date <= date_to_obj)
        except ValueError:
            pass
    
    expenses = query.order_by(Expense.date.desc()).all()
    
    # Get categories for filter
    categories = db_ext.session.query(Expense.category).distinct().all()
    categories = [cat[0] for cat in categories]
    
    return render_template('finance_suppliers/expenses.html',
                         expenses=expenses,
                         categories=categories,
                         category_filter=category_filter,
                         vendor_filter=vendor_filter,
                         date_from=date_from,
                         date_to=date_to)

@finance_suppliers_bp.route('/expenses/add', methods=['GET', 'POST'])
@login_required
@require_permission('create_supplier_expenses')
def add_expense():
    """Add new expense"""
    if request.method == 'POST':
        description = request.form.get('description')
        amount = request.form.get('amount')
        category = request.form.get('category')
        expense_date = request.form.get('date')  # Changed from expense_date to date
        vendor = request.form.get('vendor')
        hostel_name = request.form.get('hostel_name')
        staff_name = request.form.get('staff_name')
        notes = request.form.get('notes')
        
        if not all([description, amount, category, expense_date]):
            flash('Please fill in all required fields.', 'error')
            return render_template('finance_suppliers/expense_form.html')
        
        try:
            expense = Expense(
                description=description,
                amount=float(amount),
                category=category,
                date=datetime.strptime(expense_date, '%Y-%m-%d').date(),
                vendor=vendor,
                hostel_name=hostel_name,
                staff_name=staff_name,  # Add staff_name field
                notes=notes,
                created_by=current_user.id
            )
            
            db_ext.session.add(expense)
            db_ext.session.commit()
            
            # If staff_name is provided, deduct from their cash advance
            if staff_name:
                deduct_from_cash_advance(staff_name, float(amount), expense.id)
            
            flash(f'Expense "{description}" added successfully!', 'success')
            return redirect(url_for('finance_suppliers.expenses'))
            
        except ValueError:
            flash('Please enter a valid amount.', 'error')
        except Exception as e:
            db_ext.session.rollback()
            flash(f'Error adding expense: {str(e)}', 'error')
    
    return render_template('finance_suppliers/expense_form.html')

@finance_suppliers_bp.route('/expenses/<int:expense_id>')
@login_required
@require_permission('view_supplier_expenses')
def view_expense(expense_id):
    """View expense details"""
    expense = Expense.query.get_or_404(expense_id)
    return render_template('finance_suppliers/expense_detail.html', expense=expense)

@finance_suppliers_bp.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('edit_supplier_expenses')
def edit_expense(expense_id):
    """Edit expense"""
    expense = Expense.query.get_or_404(expense_id)
    
    if request.method == 'POST':
        expense.description = request.form.get('description')
        expense.amount = float(request.form.get('amount'))
        expense.category = request.form.get('category')
        expense.date = datetime.strptime(request.form.get('expense_date'), '%Y-%m-%d').date()
        expense.vendor = request.form.get('vendor')
        expense.hostel_name = request.form.get('hostel_name')
        expense.notes = request.form.get('notes')
        expense.payment_method = request.form.get('payment_method')
        
        try:
            db_ext.session.commit()
            flash(f'Expense "{expense.description}" updated successfully!', 'success')
            return redirect(url_for('finance_suppliers.expenses'))
        except Exception as e:
            db_ext.session.rollback()
            flash(f'Error updating expense: {str(e)}', 'error')
    
    return render_template('finance_suppliers/expense_edit.html', expense=expense)

@finance_suppliers_bp.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
@require_permission('delete_supplier_expenses')
def delete_expense(expense_id):
    """Delete expense"""
    expense = Expense.query.get_or_404(expense_id)
    
    try:
        description = expense.description
        db_ext.session.delete(expense)
        db_ext.session.commit()
        flash(f'Expense "{description}" deleted successfully!', 'success')
    except Exception as e:
        db_ext.session.rollback()
        flash(f'Error deleting expense: {str(e)}', 'error')
    
    return redirect(url_for('finance_suppliers.expenses'))



@finance_suppliers_bp.route('/suppliers')
@login_required
def suppliers():
    """Manage suppliers/vendors"""
    # Get all unique vendors from expenses
    vendors = db_ext.session.query(
        Expense.vendor,
        func.count(Expense.id).label('transaction_count'),
        func.sum(Expense.amount).label('total_spent')
    ).filter(
        Expense.vendor.isnot(None),
        Expense.vendor != ''
    ).group_by(Expense.vendor).order_by(func.sum(Expense.amount).desc()).all()
    
    return render_template('finance_suppliers/suppliers.html',
                         vendors=vendors)

@finance_suppliers_bp.route('/reports')
@login_required
def reports():
    """Financial reports"""
    # Get date range from query parameters
    report_type = request.args.get('report_type', 'summary')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    hostel_filter = request.args.get('hostel', '')
    
    # Set default date range if not provided
    if not date_from or not date_to:
        start_date = date.today().replace(day=1)
        end_date = date.today()
    else:
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            start_date = date.today().replace(day=1)
            end_date = date.today()
    
    # Get financial data
    expenses_query = db_ext.session.query(
        Expense.category,
        func.sum(Expense.amount).label('total')
    ).filter(
        Expense.date >= start_date,
        Expense.date <= end_date
    )
    
    # Apply hostel filter to expenses if specified
    if hostel_filter:
        expenses_query = expenses_query.filter(Expense.hostel_name == hostel_filter)
    
    expenses = expenses_query.group_by(Expense.category).all()
    
    income = db_ext.session.query(
        Income.source,
        func.sum(Income.amount).label('total')
    ).filter(
        Income.date >= start_date,
        Income.date <= end_date
    ).group_by(Income.source).all()
    
    
    # Calculate detailed revenue breakdown
    # Rent income (from guest room charges - calculate total room charges for guests in period)
    from models import Tenant, TenantService, Service
    
    # Get all guests who were active during the selected period (including inactive guests)
    guests_query = db_ext.session.query(Tenant).filter(
        Tenant.start_date <= end_date,
        Tenant.end_date >= start_date
    )
    
    # Apply hostel filter if specified
    if hostel_filter:
        guests_query = guests_query.filter(Tenant.hostel_name == hostel_filter)
    
    guests_in_period = guests_query.all()
    
    rent_amount = 0
    print(f"DEBUG: Calculating rent for period {start_date} to {end_date}")
    print(f"DEBUG: Found {len(guests_in_period)} guests in period")
    
    for guest in guests_in_period:
        print(f"DEBUG: Guest {guest.id} - {guest.name}")
        print(f"DEBUG: - Start: {guest.start_date}, End: {guest.end_date}")
        print(f"DEBUG: - Daily rent: {guest.daily_rent}")
        print(f"DEBUG: - Is prepaid: {guest.is_prepaid}")
        print(f"DEBUG: - Number of guests: {guest.number_of_guests}")
        print(f"DEBUG: - Multiply by guests: {guest.multiply_rent_by_guests}")
        
        # Calculate room charges for this guest
        stay_start = max(guest.start_date, start_date)
        stay_end = min(guest.end_date, end_date)
        # For hostel stays, checkout day is not charged (exclude the end date)
        days_in_period = (stay_end - stay_start).days
        
        print(f"DEBUG: - Stay start: {stay_start}, Stay end: {stay_end}")
        print(f"DEBUG: - Days in period: {days_in_period}")
        
        guest_rent = (guest.daily_rent or 0) * days_in_period
        print(f"DEBUG: - Base rent: {guest_rent}")
        
        if guest.multiply_rent_by_guests and guest.number_of_guests:
            guest_rent *= guest.number_of_guests
            print(f"DEBUG: - After multiplying by {guest.number_of_guests} guests: {guest_rent}")
        
        print(f"DEBUG: - Final guest rent: {guest_rent}")
        rent_amount += guest_rent
        print(f"DEBUG: - Running total: {rent_amount}")
        print("---")
    
    print(f"DEBUG: Final rent amount: {rent_amount}")
    
    # Restaurant income (from meal-related services)
    restaurant_query = db_ext.session.query(
        func.sum(TenantService.quantity * TenantService.unit_price)
    ).join(
        Service, TenantService.service_id == Service.id
    ).join(
        Tenant, TenantService.tenant_id == Tenant.id
    ).filter(
        TenantService.start_date >= start_date,
        TenantService.start_date <= end_date,
        Service.service_type == 'meal'
    )
    
    # Apply hostel filter if specified
    if hostel_filter:
        restaurant_query = restaurant_query.filter(Tenant.hostel_name == hostel_filter)
    
    restaurant_amount = restaurant_query.scalar() or 0
    
    # Surf lessons (from services where service name = "Surf Lessons")
    surf_query = db_ext.session.query(
        func.sum(TenantService.quantity * TenantService.unit_price)
    ).join(
        Service, TenantService.service_id == Service.id
    ).join(
        Tenant, TenantService.tenant_id == Tenant.id
    ).filter(
        TenantService.start_date >= start_date,
        TenantService.start_date <= end_date,
        Service.name == 'Surf Lessons'
    )
    
    # Apply hostel filter if specified
    if hostel_filter:
        surf_query = surf_query.filter(Tenant.hostel_name == hostel_filter)
    
    surf_amount = surf_query.scalar() or 0
    
    # Board rental (from services where service name = "Board Rental")
    board_rental_query = db_ext.session.query(
        func.sum(TenantService.quantity * TenantService.unit_price)
    ).join(
        Service, TenantService.service_id == Service.id
    ).join(
        Tenant, TenantService.tenant_id == Tenant.id
    ).filter(
        TenantService.start_date >= start_date,
        TenantService.start_date <= end_date,
        Service.name == 'Board Rental'
    )
    
    # Apply hostel filter if specified
    if hostel_filter:
        board_rental_query = board_rental_query.filter(Tenant.hostel_name == hostel_filter)
    
    surf_lessons_amount = board_rental_query.scalar() or 0
    
    # Add debug output for restaurant calculation
    print(f"DEBUG: Restaurant amount (from meal services): {restaurant_amount}")
    print(f"DEBUG: Surf lessons amount (from 'Surf Lessons' service name): {surf_amount}")
    print(f"DEBUG: Board rental amount (from 'Board Rental' service name): {surf_lessons_amount}")
    
    # Get services breakdown from TenantService records
    
    services_query = db_ext.session.query(
        Service.service_type,
        Service.name,
        Tenant.hostel_name,
        func.sum(TenantService.quantity * TenantService.unit_price).label('total_amount'),
        func.count(TenantService.id).label('service_count')
    ).join(
        TenantService, Service.id == TenantService.service_id
    ).join(
        Tenant, TenantService.tenant_id == Tenant.id
    ).filter(
        TenantService.start_date >= start_date,
        TenantService.start_date <= end_date
    )
    
    # Apply hostel filter if specified
    if hostel_filter:
        services_query = services_query.filter(Tenant.hostel_name == hostel_filter)
    
    services_breakdown = services_query.group_by(
        Service.service_type, Service.name, Tenant.hostel_name
    ).order_by(
        func.sum(TenantService.quantity * TenantService.unit_price).desc()
    ).all()
    
    # Calculate total services amount
    total_services_amount = sum(item.total_amount for item in services_breakdown)
    
    # Get inventory data for Est. Total Value
    from models import InventoryItem
    inventory_items = InventoryItem.query.all()
    estimated_total_value = sum(item.current_stock * item.cost_per_unit for item in inventory_items if item.cost_per_unit)
    
    # Calculate total payments for all paid guests
    payments_query = db_ext.session.query(
        func.sum(Payment.amount)
    ).join(Tenant, Payment.tenant_id == Tenant.id).filter(
        Payment.payment_date >= start_date,
        Payment.payment_date <= end_date
    )
    
    # Apply hostel filter to payments if specified
    if hostel_filter:
        payments_query = payments_query.filter(Tenant.hostel_name == hostel_filter)
    
    total_payments = payments_query.scalar() or 0
    
    # Calculate total salaries for the period
    # Since net_salary is a property, we need to calculate it using the actual columns
    if hostel_filter:
        # When filtering by hostel, sum only the hostel-specific amounts
        if hostel_filter == 'Olas':
            total_salaries = db_ext.session.query(
                func.sum(SalaryRecord.olas_amount)
            ).filter(
                SalaryRecord.payment_date >= start_date,
                SalaryRecord.payment_date <= end_date,
                SalaryRecord.payment_status == 'paid',
                SalaryRecord.olas_amount > 0
            ).scalar() or 0
        elif hostel_filter == 'Tide':
            total_salaries = db_ext.session.query(
                func.sum(SalaryRecord.tide_amount)
            ).filter(
                SalaryRecord.payment_date >= start_date,
                SalaryRecord.payment_date <= end_date,
                SalaryRecord.payment_status == 'paid',
                SalaryRecord.tide_amount > 0
            ).scalar() or 0
        elif hostel_filter == 'General':
            total_salaries = db_ext.session.query(
                func.sum(SalaryRecord.general_amount)
            ).filter(
                SalaryRecord.payment_date >= start_date,
                SalaryRecord.payment_date <= end_date,
                SalaryRecord.payment_status == 'paid',
                SalaryRecord.general_amount > 0
            ).scalar() or 0
        else:
            # Unknown hostel filter, show all salaries
            total_salaries = db_ext.session.query(
                func.sum(
                    SalaryRecord.basic_salary + 
                    SalaryRecord.housing_allowance + 
                    SalaryRecord.transport_allowance + 
                    SalaryRecord.meal_allowance + 
                    SalaryRecord.performance_bonus + 
                    SalaryRecord.overtime_pay + 
                    SalaryRecord.holiday_bonus + 
                    SalaryRecord.other_allowances - 
                    SalaryRecord.social_security - 
                    SalaryRecord.income_tax - 
                    SalaryRecord.health_insurance - 
                    SalaryRecord.pension_contributions - 
                    SalaryRecord.loan_deductions - 
                    SalaryRecord.other_deductions
                )
            ).filter(
                SalaryRecord.payment_date >= start_date,
                SalaryRecord.payment_date <= end_date,
                SalaryRecord.payment_status == 'paid'
            ).scalar() or 0
    else:
        # No hostel filter, show total net salary
        total_salaries = db_ext.session.query(
            func.sum(
                SalaryRecord.basic_salary + 
                SalaryRecord.housing_allowance + 
                SalaryRecord.transport_allowance + 
                SalaryRecord.meal_allowance + 
                SalaryRecord.performance_bonus + 
                SalaryRecord.overtime_pay + 
                SalaryRecord.holiday_bonus + 
                SalaryRecord.other_allowances - 
                SalaryRecord.social_security - 
                SalaryRecord.income_tax - 
                SalaryRecord.health_insurance - 
                SalaryRecord.pension_contributions - 
                SalaryRecord.loan_deductions - 
                SalaryRecord.other_deductions
            )
        ).filter(
            SalaryRecord.payment_date >= start_date,
            SalaryRecord.payment_date <= end_date,
            SalaryRecord.payment_status == 'paid'
        ).scalar() or 0
    
    return render_template('finance_suppliers/reports.html',
                         expenses=expenses,
                         income=income,
                         total_payments=total_payments,
                         total_salaries=total_salaries,
                         report_type=report_type,
                         start_date=start_date,
                         end_date=end_date,
                         hostel_filter=hostel_filter,
                         rent_amount=rent_amount,
                         restaurant_amount=restaurant_amount,
                         surf_amount=surf_amount,
                         surf_lessons_amount=surf_lessons_amount,
                         services_breakdown=services_breakdown,
                         total_services_amount=total_services_amount,
                         estimated_total_value=estimated_total_value)

@finance_suppliers_bp.route('/api/quick-stats')
@login_required
def quick_stats():
    """API endpoint for quick dashboard stats"""
    try:
        today = date.today()
        this_month = today.replace(day=1)
        
        # Today's expenses
        today_expenses = db_ext.session.query(
            func.sum(Expense.amount)
        ).filter(Expense.date == today).scalar() or 0
        
        # This month's profit
        monthly_income = db_ext.session.query(
            func.sum(Income.amount)
        ).filter(Income.date >= this_month).scalar() or 0
        
        monthly_expenses = db_ext.session.query(
            func.sum(Expense.amount)
        ).filter(Expense.date >= this_month).scalar() or 0
        
        monthly_profit = monthly_income - monthly_expenses
        
        return jsonify({
            'success': True,
            'stats': {
                'today_expenses': float(today_expenses),
                'monthly_profit': float(monthly_profit),
                'monthly_expenses': float(monthly_expenses)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Cash Advance Routes
@finance_suppliers_bp.route('/cash-advances')
@login_required
@require_permission('view_supplier_expenses')
def cash_advances():
    """List all cash advances"""
    advances = StaffCashAdvance.query.order_by(StaffCashAdvance.date_given.desc()).all()
    return render_template('finance_suppliers/cash_advances.html', advances=advances)

@finance_suppliers_bp.route('/cash-advances/add', methods=['GET', 'POST'])
@login_required
@require_permission('create_supplier_expenses')
def add_cash_advance():
    """Add new cash advance"""
    # Get active users for dropdown (excluding admins)
    users = User.query.filter_by(is_active=True).filter(User.is_admin == False).order_by(User.full_name).all()
    
    if request.method == 'POST':
        try:
            # Get user name from selected user
            user_id = request.form.get('user_id')
            if user_id:
                user = User.query.get(user_id)
                staff_name = user.full_name or user.username
            else:
                staff_name = request.form.get('staff_name', '')
            
            advance = StaffCashAdvance(
                staff_name=staff_name,
                amount=float(request.form['amount']),
                purpose=request.form.get('purpose', ''),  # Make purpose optional
                date_given=datetime.strptime(request.form['date_given'], '%Y-%m-%d').date(),
                expected_return_date=datetime.strptime(request.form['expected_return_date'], '%Y-%m-%d').date() if request.form.get('expected_return_date') else None,
                notes=request.form.get('notes', ''),
                created_by=current_user.id
            )
            db.session.add(advance)
            db.session.commit()
            flash('Cash advance added successfully!', 'success')
            return redirect(url_for('finance_suppliers.cash_advances'))
        except Exception as e:
            flash(f'Error adding cash advance: {str(e)}', 'error')
    
    return render_template('finance_suppliers/add_cash_advance.html', users=users)

@finance_suppliers_bp.route('/cash-advances/<int:advance_id>')
@login_required
@require_permission('view_supplier_expenses')
def view_cash_advance(advance_id):
    """View cash advance details"""
    advance = StaffCashAdvance.query.get_or_404(advance_id)
    
    # Calculate original amount (current amount + all expenses - all additions)
    original_amount = advance.amount
    for history in advance.history:
        if history.transaction_type == 'expense':
            original_amount += abs(history.amount)  # Add back expenses
        elif history.transaction_type == 'addition':
            original_amount -= history.amount  # Subtract additions
    
    return render_template('finance_suppliers/view_cash_advance.html', 
                         advance=advance, 
                         original_amount=original_amount)

@finance_suppliers_bp.route('/cash-advances/<int:advance_id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('edit_supplier_expenses')
def edit_cash_advance(advance_id):
    """Edit cash advance"""
    advance = StaffCashAdvance.query.get_or_404(advance_id)
    
    if request.method == 'POST':
        try:
            advance.staff_name = request.form['staff_name']
            advance.amount = float(request.form['amount'])
            advance.purpose = request.form['purpose']
            advance.date_given = datetime.strptime(request.form['date_given'], '%Y-%m-%d').date()
            advance.expected_return_date = datetime.strptime(request.form['expected_return_date'], '%Y-%m-%d').date() if request.form.get('expected_return_date') else None
            advance.status = request.form['status']
            advance.notes = request.form.get('notes', '')
            
            db.session.commit()
            flash('Cash advance updated successfully!', 'success')
            return redirect(url_for('finance_suppliers.view_cash_advance', advance_id=advance.id))
        except Exception as e:
            flash(f'Error updating cash advance: {str(e)}', 'error')
    
    return render_template('finance_suppliers/edit_cash_advance.html', advance=advance)

@finance_suppliers_bp.route('/cash-advances/<int:advance_id>/delete', methods=['POST'])
@login_required
@require_permission('delete_supplier_expenses')
def delete_cash_advance(advance_id):
    """Delete cash advance"""
    advance = StaffCashAdvance.query.get_or_404(advance_id)
    try:
        db.session.delete(advance)
        db.session.commit()
        flash('Cash advance deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting cash advance: {str(e)}', 'error')
    
    return redirect(url_for('finance_suppliers.cash_advances'))

@finance_suppliers_bp.route('/cash-advances/<int:advance_id>/add-cash', methods=['GET', 'POST'])
@login_required
@require_permission('edit_supplier_expenses')
def add_cash_to_advance(advance_id):
    """Add more cash to an existing cash advance"""
    advance = StaffCashAdvance.query.get_or_404(advance_id)
    
    if request.method == 'POST':
        try:
            additional_amount = float(request.form['amount'])
            description = request.form.get('description', f'Additional cash added')
            
            if additional_amount <= 0:
                flash('Amount must be greater than 0.', 'error')
                return render_template('finance_suppliers/add_cash_to_advance.html', advance=advance)
            
            # Update the cash advance amount
            advance.amount += additional_amount
            
            # Update status if it was completed
            if advance.status == 'completed':
                advance.status = 'partially_used'
            
            # Create history record
            history = CashAdvanceHistory(
                cash_advance_id=advance.id,
                transaction_type='addition',
                amount=additional_amount,
                description=description,
                created_by=current_user.id
            )
            
            db.session.add(history)
            db.session.commit()
            
            flash(f'Successfully added {additional_amount} MAD to {advance.staff_name}\'s cash advance!', 'success')
            return redirect(url_for('finance_suppliers.view_cash_advance', advance_id=advance.id))
            
        except ValueError:
            flash('Please enter a valid amount.', 'error')
        except Exception as e:
            flash(f'Error adding cash: {str(e)}', 'error')
    
    return render_template('finance_suppliers/add_cash_to_advance.html', advance=advance)

def deduct_from_cash_advance(staff_name, amount, expense_id):
    """Deduct expense amount from staff member's cash advance"""
    try:
        # Find the most recent cash advance for this staff member (pending or partially_used)
        cash_advance = StaffCashAdvance.query.filter(
            StaffCashAdvance.staff_name == staff_name,
            StaffCashAdvance.status.in_(['pending', 'partially_used'])
        ).order_by(StaffCashAdvance.date_given.desc()).first()
        
        if cash_advance:
            # Calculate remaining balance
            remaining_balance = cash_advance.amount - amount
            
            # Update cash advance status and amount
            if remaining_balance <= 0:
                # Fully used
                cash_advance.status = 'completed'
                cash_advance.amount = 0
                flash(f'Cash advance for {staff_name} has been fully used.', 'info')
            else:
                # Partially used
                cash_advance.status = 'partially_used'
                cash_advance.amount = remaining_balance
                flash(f'Cash advance for {staff_name} reduced by {amount} MAD. Remaining: {remaining_balance} MAD.', 'info')
            
            # Create history record for the expense
            history = CashAdvanceHistory(
                cash_advance_id=cash_advance.id,
                transaction_type='expense',
                amount=-amount,  # Negative for expenses
                description=f'Expense #{expense_id}',
                expense_id=expense_id,
                created_by=current_user.id
            )
            
            db.session.add(history)
            db.session.commit()
        else:
            flash(f'No pending cash advance found for {staff_name}.', 'warning')
            
    except Exception as e:
        flash(f'Error updating cash advance: {str(e)}', 'error')
