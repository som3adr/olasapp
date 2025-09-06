from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_, func
from models import db, Employee, SalaryRecord, SalaryAdvance, User
import json
from permissions import require_admin

employee_salaries_bp = Blueprint('employee_salaries', __name__, url_prefix='/employee-salaries')

def calculate_salary_advance_deductions(employee_id, pay_period_start):
    """Calculate total salary advance deductions for a given month"""
    total_deductions = 0
    
    # Get all active salary advances for this employee
    active_advances = SalaryAdvance.query.filter(
        and_(
            SalaryAdvance.employee_id == employee_id,
            SalaryAdvance.status == 'active',
            SalaryAdvance.remaining_balance > 0
        )
    ).all()
    
    for advance in active_advances:
        # Check if this advance should be deducted in this pay period
        # We deduct the monthly amount if the advance was taken before or during this pay period
        if advance.advance_date <= pay_period_start:
            total_deductions += advance.monthly_deduction
    
    return total_deductions

def update_salary_advance_balances(employee_id, pay_period_start):
    """Update salary advance balances when salary is paid"""
    # Get all active salary advances for this employee
    active_advances = SalaryAdvance.query.filter(
        and_(
            SalaryAdvance.employee_id == employee_id,
            SalaryAdvance.status == 'active',
            SalaryAdvance.remaining_balance > 0
        )
    ).all()
    
    for advance in active_advances:
        # Check if this advance should be deducted in this pay period
        if advance.advance_date <= pay_period_start:
            # Update the advance balance
            advance.total_repaid += advance.monthly_deduction
            advance.remaining_balance -= advance.monthly_deduction
            
            # If fully repaid, mark as completed
            if advance.remaining_balance <= 0:
                advance.status = 'completed'
                advance.remaining_balance = 0
            
            advance.updated_at = datetime.utcnow()

@employee_salaries_bp.route('/')
@login_required
@require_admin
def index():
    """Employee salaries dashboard"""
    # Get filter parameters
    department = request.args.get('department', 'all')
    status = request.args.get('status', 'all')
    search = request.args.get('search', '')
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    
    try:
        month_date = datetime.strptime(month, '%Y-%m').date()
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
    except ValueError:
        month_date = date.today()
        month_start = month_date.replace(day=1)
        month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
    
    # Build query for employees
    query = Employee.query
    
    if department != 'all':
        query = query.filter(Employee.department == department)
    
    if status != 'all':
        query = query.filter(Employee.status == status)
    
    if search:
        query = query.filter(
            or_(
                Employee.first_name.ilike(f'%{search}%'),
                Employee.last_name.ilike(f'%{search}%'),
                Employee.employee_code.ilike(f'%{search}%'),
                Employee.position.ilike(f'%{search}%')
            )
        )
    
    employees = query.order_by(Employee.first_name, Employee.last_name).all()
    
    # Get salary records for the selected month
    salary_records = SalaryRecord.query.filter(
        and_(
            SalaryRecord.pay_period_start >= month_start,
            SalaryRecord.pay_period_end <= month_end
        )
    ).all()
    
    # Create a mapping of employee_id to salary_record
    salary_map = {record.employee_id: record for record in salary_records}
    
    # Calculate statistics
    total_employees = len(employees)
    active_employees = len([e for e in employees if e.is_active])
    total_payroll = sum(record.net_salary for record in salary_records)
    paid_salaries = len([r for r in salary_records if r.payment_status == 'paid'])
    
    # Department statistics
    departments = ['Reception', 'Housekeeping', 'Kitchen', 'Maintenance', 'Management']
    dept_stats = {}
    for dept in departments:
        dept_employees = [e for e in employees if e.department == dept and e.is_active]
        dept_salaries = [salary_map.get(e.id) for e in dept_employees if salary_map.get(e.id)]
        dept_stats[dept] = {
            'count': len(dept_employees),
            'total_salary': sum(s.net_salary for s in dept_salaries if s)
        }
    
    return render_template('employee_salaries/index.html',
                         employees=employees,
                         salary_map=salary_map,
                         total_employees=total_employees,
                         active_employees=active_employees,
                         total_payroll=total_payroll,
                         paid_salaries=paid_salaries,
                         dept_stats=dept_stats,
                         departments=departments,
                         current_month=month,
                         current_department=department,
                         current_status=status,
                         current_search=search,
                         date=date)

@employee_salaries_bp.route('/add', methods=['GET', 'POST'])
@login_required
@require_admin
def add_employee():
    """Add new employee"""
    if request.method == 'POST':
        try:
            # Generate employee code
            last_employee = Employee.query.order_by(Employee.id.desc()).first()
            employee_code = f"EMP{str(last_employee.id + 1).zfill(4)}" if last_employee else "EMP0001"
            
            employee = Employee(
                employee_code=employee_code,
                first_name=request.form.get('first_name'),
                last_name=request.form.get('last_name'),
                department=request.form.get('department'),
                position=request.form.get('position'),
                employment_type=request.form.get('employment_type'),
                hire_date=datetime.strptime(request.form.get('hire_date'), '%Y-%m-%d').date(),
                basic_salary=float(request.form.get('basic_salary', 0)),
                bank_account=request.form.get('bank_account'),
                address=request.form.get('address'),
                notes=request.form.get('notes'),
                created_by=current_user.id
            )
            
            db.session.add(employee)
            db.session.commit()
            
            flash(f'Employee {employee.full_name} added successfully!', 'success')
            return redirect(url_for('employee_salaries.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding employee: {str(e)}', 'error')
    
    departments = ['Reception', 'Housekeeping', 'Kitchen', 'Maintenance', 'Management']
    employment_types = ['Full-time', 'Part-time', 'Contract', 'Intern']
    
    return render_template('employee_salaries/add_employee.html',
                         departments=departments,
                         employment_types=employment_types,
                         date=date)

@employee_salaries_bp.route('/<int:employee_id>')
@login_required
@require_admin
def view_employee(employee_id):
    """View employee details and salary history"""
    employee = Employee.query.get_or_404(employee_id)
    
    # Get salary history
    salary_history = SalaryRecord.query.filter_by(employee_id=employee_id)\
        .order_by(SalaryRecord.pay_period_start.desc()).all()
    
    # Get salary advances
    salary_advances = SalaryAdvance.query.filter_by(employee_id=employee_id)\
        .order_by(SalaryAdvance.advance_date.desc()).all()
    
    # Get current month salary if exists
    current_month = date.today().replace(day=1)
    current_salary = SalaryRecord.query.filter(
        and_(
            SalaryRecord.employee_id == employee_id,
            SalaryRecord.pay_period_start >= current_month
        )
    ).first()
    
    return render_template('employee_salaries/view_employee.html',
                         employee=employee,
                         salary_history=salary_history,
                         salary_advances=salary_advances,
                         current_salary=current_salary,
                         date=date)

@employee_salaries_bp.route('/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@require_admin
def edit_employee(employee_id):
    """Edit employee information"""
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        try:
            employee.first_name = request.form.get('first_name')
            employee.last_name = request.form.get('last_name')
            employee.department = request.form.get('department')
            employee.position = request.form.get('position')
            employee.employment_type = request.form.get('employment_type')
            employee.hire_date = datetime.strptime(request.form.get('hire_date'), '%Y-%m-%d').date()
            employee.basic_salary = float(request.form.get('basic_salary', 0))
            employee.bank_account = request.form.get('bank_account')
            employee.address = request.form.get('address')
            employee.notes = request.form.get('notes')
            employee.status = request.form.get('status')
            employee.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            flash(f'Employee {employee.full_name} updated successfully!', 'success')
            return redirect(url_for('employee_salaries.view_employee', employee_id=employee.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating employee: {str(e)}', 'error')
    
    departments = ['Reception', 'Housekeeping', 'Kitchen', 'Maintenance', 'Management']
    employment_types = ['Full-time', 'Part-time', 'Contract', 'Intern']
    statuses = ['active', 'inactive', 'terminated']
    
    return render_template('employee_salaries/edit_employee.html',
                         employee=employee,
                         departments=departments,
                         employment_types=employment_types,
                         statuses=statuses,
                         date=date)

@employee_salaries_bp.route('/<int:employee_id>/salary', methods=['GET', 'POST'])
@login_required
@require_admin
def manage_salary(employee_id):
    """Manage employee salary for current month"""
    employee = Employee.query.get_or_404(employee_id)
    
    # Get current month
    current_month = date.today().replace(day=1)
    if current_month.month == 12:
        next_month = current_month.replace(year=current_month.year + 1, month=1)
    else:
        next_month = current_month.replace(month=current_month.month + 1)
    month_end = next_month - timedelta(days=1)
    
    # Get existing salary record for current month
    salary_record = SalaryRecord.query.filter(
        and_(
            SalaryRecord.employee_id == employee_id,
            SalaryRecord.pay_period_start >= current_month
        )
    ).first()
    
    if request.method == 'POST':
        try:
            if salary_record:
                # Calculate salary advance deductions for this month
                advance_deductions = calculate_salary_advance_deductions(employee_id, current_month)
                
                # Update existing record
                salary_record.basic_salary = float(request.form.get('basic_salary', 0))
                # Set all allowances and deductions to 0 (simplified form)
                salary_record.housing_allowance = 0
                salary_record.transport_allowance = 0
                salary_record.meal_allowance = 0
                salary_record.performance_bonus = 0
                salary_record.overtime_pay = 0
                salary_record.holiday_bonus = 0
                salary_record.other_allowances = 0
                salary_record.social_security = 0
                salary_record.income_tax = 0
                salary_record.health_insurance = 0
                salary_record.pension_contributions = 0
                salary_record.loan_deductions = 0
                salary_record.other_deductions = advance_deductions  # Only advance deductions
                salary_record.payment_status = request.form.get('payment_status')
                salary_record.payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date() if request.form.get('payment_date') else None
                salary_record.payment_method = request.form.get('payment_method')
                salary_record.payment_reference = request.form.get('payment_reference')
                salary_record.notes = request.form.get('notes')
                salary_record.updated_at = datetime.utcnow()
                
                # Update salary advance balances if payment status is 'paid'
                if request.form.get('payment_status') == 'paid':
                    update_salary_advance_balances(employee_id, current_month)
            else:
                # Calculate salary advance deductions for this month
                advance_deductions = calculate_salary_advance_deductions(employee_id, current_month)
                
                # Create new record
                salary_record = SalaryRecord(
                    employee_id=employee_id,
                    pay_period_start=current_month,
                    pay_period_end=month_end,
                    basic_salary=float(request.form.get('basic_salary', 0)),
                    # Set all allowances and deductions to 0 (simplified form)
                    housing_allowance=0,
                    transport_allowance=0,
                    meal_allowance=0,
                    performance_bonus=0,
                    overtime_pay=0,
                    holiday_bonus=0,
                    other_allowances=0,
                    social_security=0,
                    income_tax=0,
                    health_insurance=0,
                    pension_contributions=0,
                    loan_deductions=0,
                    other_deductions=advance_deductions,  # Only advance deductions
                    payment_status=request.form.get('payment_status', 'pending'),
                    payment_date=datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date() if request.form.get('payment_date') else None,
                    payment_method=request.form.get('payment_method'),
                    payment_reference=request.form.get('payment_reference'),
                    notes=request.form.get('notes'),
                    created_by=current_user.id
                )
                db.session.add(salary_record)
                
                # Update salary advance balances if payment status is 'paid'
                if request.form.get('payment_status') == 'paid':
                    update_salary_advance_balances(employee_id, current_month)
            
            db.session.commit()
            
            flash(f'Salary record for {employee.full_name} saved successfully!', 'success')
            return redirect(url_for('employee_salaries.view_employee', employee_id=employee.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving salary record: {str(e)}', 'error')
    
    payment_statuses = ['pending', 'paid', 'failed']
    payment_methods = ['Bank Transfer', 'Cash', 'Check']
    
    # Calculate advance deductions for display
    advance_deductions = calculate_salary_advance_deductions(employee_id, current_month)
    
    return render_template('employee_salaries/manage_salary.html',
                         employee=employee,
                         salary_record=salary_record,
                         current_month=current_month,
                         month_end=month_end,
                         payment_statuses=payment_statuses,
                         payment_methods=payment_methods,
                         advance_deductions=advance_deductions,
                         date=date)

def create_salary_expense_records(employee_ids, payment_date, hostel_allocation, single_hostel_name, olas_percentage, tide_percentage, general_percentage):
    """Create expense records for salary payments per hostel"""
    from models import Expense
    
    # Get all salary records for the processed employees
    salary_records = SalaryRecord.query.filter(
        SalaryRecord.employee_id.in_(employee_ids),
        SalaryRecord.payment_date == payment_date,
        SalaryRecord.payment_status == 'paid'
    ).all()
    
    # Group amounts by hostel
    hostel_amounts = {'Olas': 0, 'Tide': 0, 'General': 0}
    
    for record in salary_records:
        hostel_amounts['Olas'] += record.olas_amount
        hostel_amounts['Tide'] += record.tide_amount
        hostel_amounts['General'] += record.general_amount
    
    # Create expense records for each hostel with non-zero amounts
    for hostel_name, amount in hostel_amounts.items():
        if amount > 0:
            expense = Expense(
                description=f"Employee Salary Payments - {hostel_name}",
                amount=amount,
                category='staff',
                date=payment_date,
                vendor='Internal Payroll',
                hostel_name=hostel_name,
                staff_name='System',
                notes=f'Bulk salary payment allocation for {hostel_name} hostel',
                created_by=1  # System user
            )
            db.session.add(expense)

@employee_salaries_bp.route('/bulk-pay', methods=['POST'])
@login_required
@require_admin
def bulk_pay():
    """Process bulk salary payments with hostel allocation"""
    try:
        employee_ids = request.form.getlist('employee_ids')
        payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
        payment_method = request.form.get('payment_method')
        month = request.form.get('month', date.today().strftime('%Y-%m'))
        
        # Get hostel allocation settings
        hostel_allocation = request.form.get('hostel_allocation', 'single')
        single_hostel_name = request.form.get('single_hostel_name', 'General')
        olas_percentage = int(request.form.get('olas_percentage', 0))
        tide_percentage = int(request.form.get('tide_percentage', 0))
        general_percentage = int(request.form.get('general_percentage', 0))
        
        # Parse month to get date range
        try:
            month_date = datetime.strptime(month, '%Y-%m').date()
            month_start = month_date.replace(day=1)
            if month_date.month == 12:
                month_end = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
        except ValueError:
            month_date = date.today()
            month_start = month_date.replace(day=1)
            month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
        
        updated_count = 0
        print(f"Bulk pay: Processing {len(employee_ids)} employees for month {month}")
        print(f"Date range: {month_start} to {month_end}")
        print(f"Employee IDs received: {employee_ids}")
        print(f"Hostel allocation: {hostel_allocation}")
        
        # Helper function to calculate hostel allocation amounts
        def calculate_hostel_allocation(net_salary):
            if hostel_allocation == 'single':
                if single_hostel_name == 'Olas':
                    return {'olas_amount': net_salary, 'tide_amount': 0, 'general_amount': 0}
                elif single_hostel_name == 'Tide':
                    return {'olas_amount': 0, 'tide_amount': net_salary, 'general_amount': 0}
                else:  # General
                    return {'olas_amount': 0, 'tide_amount': 0, 'general_amount': net_salary}
            elif hostel_allocation == 'split_50_50':
                half_salary = net_salary / 2
                return {'olas_amount': half_salary, 'tide_amount': half_salary, 'general_amount': 0}
            elif hostel_allocation == 'custom':
                olas_amount = net_salary * olas_percentage / 100
                tide_amount = net_salary * tide_percentage / 100
                general_amount = net_salary * general_percentage / 100
                return {'olas_amount': olas_amount, 'tide_amount': tide_amount, 'general_amount': general_amount}
            else:
                return {'olas_amount': 0, 'tide_amount': 0, 'general_amount': net_salary}
        
        for employee_id in employee_ids:
            # Get the employee
            employee = Employee.query.get(employee_id)
            if not employee:
                print(f"Employee {employee_id}: Employee not found")
                continue
            
            # Check if there's any salary record for this employee in this month
            salary_record = SalaryRecord.query.filter(
                and_(
                    SalaryRecord.employee_id == employee_id,
                    SalaryRecord.pay_period_start >= month_start,
                    SalaryRecord.pay_period_end <= month_end
                )
            ).first()
            
            print(f"Employee {employee_id}: Record exists: {salary_record is not None}")
            
            if salary_record:
                # Record exists - update it to paid
                print(f"Employee {employee_id}: Updating existing record to paid")
                salary_record.payment_status = 'paid'
                salary_record.payment_date = payment_date
                salary_record.payment_method = payment_method
                
                # Calculate and set hostel allocation
                net_salary = salary_record.net_salary
                allocation = calculate_hostel_allocation(net_salary)
                salary_record.hostel_allocation_type = hostel_allocation
                salary_record.olas_amount = allocation['olas_amount']
                salary_record.tide_amount = allocation['tide_amount']
                salary_record.general_amount = allocation['general_amount']
                
                # Update salary advance balances
                update_salary_advance_balances(employee_id, salary_record.pay_period_start)
                
                updated_count += 1
            else:
                # No record exists - create a new one and mark as paid
                print(f"Employee {employee_id}: Creating new record and marking as paid")
                
                # Calculate salary advance deductions for this month
                advance_deductions = calculate_salary_advance_deductions(employee_id, month_start)
                
                # Calculate net salary for allocation
                net_salary = employee.basic_salary - advance_deductions
                allocation = calculate_hostel_allocation(net_salary)
                
                # Create new salary record
                salary_record = SalaryRecord(
                    employee_id=employee_id,
                    pay_period_start=month_start,
                    pay_period_end=month_end,
                    basic_salary=employee.basic_salary,
                    # Set all allowances and deductions to 0 (simplified form)
                    housing_allowance=0,
                    transport_allowance=0,
                    meal_allowance=0,
                    performance_bonus=0,
                    overtime_pay=0,
                    holiday_bonus=0,
                    other_allowances=0,
                    social_security=0,
                    income_tax=0,
                    health_insurance=0,
                    pension_contributions=0,
                    loan_deductions=0,
                    other_deductions=advance_deductions,  # Only advance deductions
                    payment_status='paid',  # Mark as paid immediately
                    payment_date=payment_date,
                    payment_method=payment_method,
                    payment_reference=None,
                    notes='Created via bulk pay',
                    created_by=current_user.id,
                    # Hostel allocation
                    hostel_allocation_type=hostel_allocation,
                    olas_amount=allocation['olas_amount'],
                    tide_amount=allocation['tide_amount'],
                    general_amount=allocation['general_amount']
                )
                db.session.add(salary_record)
                
                # Update salary advance balances
                update_salary_advance_balances(employee_id, month_start)
                
                updated_count += 1
        
        # Create expense records for hostel allocations
        create_salary_expense_records(employee_ids, payment_date, hostel_allocation, 
                                    single_hostel_name, olas_percentage, tide_percentage, general_percentage)
        
        db.session.commit()
        
        flash(f'Successfully processed payments for {updated_count} employees!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing bulk payments: {str(e)}', 'error')
    
    return redirect(url_for('employee_salaries.index'))

@employee_salaries_bp.route('/export')
@login_required
@require_admin
def export_salaries():
    """Export salary data to CSV"""
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    
    try:
        month_date = datetime.strptime(month, '%Y-%m').date()
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
    except ValueError:
        month_date = date.today()
        month_start = month_date.replace(day=1)
        month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
    
    # Get salary records for the month
    salary_records = SalaryRecord.query.join(Employee).filter(
        and_(
            SalaryRecord.pay_period_start >= month_start,
            SalaryRecord.pay_period_end <= month_end
        )
    ).all()
    
    # Create CSV data
    csv_data = []
    csv_data.append([
        'Employee Code', 'Name', 'Department', 'Position',
        'Basic Salary', 'Total Allowances', 'Total Deductions',
        'Gross Salary', 'Net Salary', 'Payment Status', 'Payment Date'
    ])
    
    for record in salary_records:
        csv_data.append([
            record.employee.employee_code,
            record.employee.full_name,
            record.employee.department,
            record.employee.position,
            f"{record.basic_salary:.2f}",
            f"{record.total_allowances:.2f}",
            f"{record.total_deductions:.2f}",
            f"{record.gross_salary:.2f}",
            f"{record.net_salary:.2f}",
            record.payment_status.title(),
            record.payment_date.strftime('%Y-%m-%d') if record.payment_date else ''
        ])
    
    # Convert to CSV string
    csv_string = '\n'.join([','.join(row) for row in csv_data])
    
    from flask import Response
    return Response(
        csv_string,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=salaries_{month}.csv'}
    )

# Salary Advance Routes
@employee_salaries_bp.route('/advances')
@login_required
@require_admin
def advances():
    """View all salary advances"""
    advances = SalaryAdvance.query.join(Employee).order_by(SalaryAdvance.advance_date.desc()).all()
    
    # Calculate statistics
    total_advances = len(advances)
    active_advances = len([a for a in advances if a.status == 'active'])
    completed_advances = len([a for a in advances if a.status == 'completed'])
    total_advance_amount = sum([a.advance_amount for a in advances if a.status == 'active'])
    
    return render_template('employee_salaries/advances.html',
                         advances=advances,
                         total_advances=total_advances,
                         active_advances=active_advances,
                         completed_advances=completed_advances,
                         total_advance_amount=total_advance_amount,
                         date=date)

@employee_salaries_bp.route('/advances/add', methods=['GET', 'POST'])
@login_required
@require_admin
def add_advance():
    """Add new salary advance"""
    if request.method == 'POST':
        try:
            employee_id = request.form.get('employee_id')
            advance_amount = float(request.form.get('advance_amount'))
            advance_date = datetime.strptime(request.form.get('advance_date'), '%Y-%m-%d').date()
            reason = request.form.get('reason')
            repayment_months = int(request.form.get('repayment_months', 1))
            payment_method = request.form.get('payment_method')
            payment_reference = request.form.get('payment_reference')
            notes = request.form.get('notes')
            
            # Calculate repayment details
            monthly_deduction = advance_amount / repayment_months
            remaining_balance = advance_amount
            
            advance = SalaryAdvance(
                employee_id=employee_id,
                advance_amount=advance_amount,
                advance_date=advance_date,
                reason=reason,
                repayment_amount=advance_amount,
                repayment_months=repayment_months,
                monthly_deduction=monthly_deduction,
                remaining_balance=remaining_balance,
                payment_method=payment_method,
                payment_reference=payment_reference,
                notes=notes,
                created_by=current_user.id
            )
            
            db.session.add(advance)
            db.session.commit()
            
            flash(f'Salary advance of {advance_amount:.2f} MAD added successfully for {advance.employee.full_name}!', 'success')
            return redirect(url_for('employee_salaries.advances'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding salary advance: {str(e)}', 'error')
    
    # Get all active employees for dropdown
    employees = Employee.query.filter_by(status='active').order_by(Employee.first_name).all()
    payment_methods = ['Cash', 'Bank Transfer', 'Check']
    
    return render_template('employee_salaries/add_advance.html',
                         employees=employees,
                         payment_methods=payment_methods,
                         date=date)

@employee_salaries_bp.route('/advances/<int:advance_id>/view')
@login_required
@require_admin
def view_advance(advance_id):
    """View salary advance details"""
    advance = SalaryAdvance.query.get_or_404(advance_id)
    
    # Get repayment history (this would be from salary records with advance deductions)
    # For now, we'll show basic info
    return render_template('employee_salaries/view_advance.html',
                         advance=advance,
                         date=date)

@employee_salaries_bp.route('/advances/<int:advance_id>/edit', methods=['GET', 'POST'])
@login_required
@require_admin
def edit_advance(advance_id):
    """Edit salary advance"""
    advance = SalaryAdvance.query.get_or_404(advance_id)
    
    if request.method == 'POST':
        try:
            advance.reason = request.form.get('reason')
            advance.payment_method = request.form.get('payment_method')
            advance.payment_reference = request.form.get('payment_reference')
            advance.notes = request.form.get('notes')
            advance.status = request.form.get('status')
            advance.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            flash(f'Salary advance updated successfully!', 'success')
            return redirect(url_for('employee_salaries.view_advance', advance_id=advance.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating salary advance: {str(e)}', 'error')
    
    statuses = ['active', 'completed', 'cancelled']
    
    return render_template('employee_salaries/edit_advance.html',
                         advance=advance,
                         statuses=statuses,
                         date=date)

@employee_salaries_bp.route('/remove/<int:employee_id>', methods=['POST'])
@login_required
@require_admin
def remove_employee(employee_id):
    """Remove employee and all related data"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        employee_name = f"{employee.first_name} {employee.last_name}"
        
        # Delete all related records
        # Delete salary records
        SalaryRecord.query.filter_by(employee_id=employee_id).delete()
        
        # Delete salary advances
        SalaryAdvance.query.filter_by(employee_id=employee_id).delete()
        
        # Delete the employee
        db.session.delete(employee)
        db.session.commit()
        
        flash(f'Employee {employee_name} has been successfully removed from the system.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error removing employee: {str(e)}', 'error')
    
    return redirect(url_for('employee_salaries.index'))