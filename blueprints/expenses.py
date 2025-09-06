from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Expense, EXPENSE_CATEGORIES
from extensions import db
from permissions import require_frontdesk_or_admin
from datetime import datetime

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

@expenses_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = Expense.query
    
    # Apply filters
    if category:
        query = query.filter(Expense.category == category)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Expense.date >= from_date)
        except ValueError:
            flash('Invalid from date format.', 'error')
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Expense.date <= to_date)
        except ValueError:
            flash('Invalid to date format.', 'error')
    
    expenses = query.order_by(Expense.date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Calculate total for filtered results
    total_amount = query.with_entities(db.func.sum(Expense.amount)).scalar() or 0
    
    return render_template('expenses/index.html',
                         expenses=expenses,
                         categories=EXPENSE_CATEGORIES,
                         total_amount=total_amount,
                         filters={
                             'category': category,
                             'date_from': date_from,
                             'date_to': date_to
                         })

@expenses_bp.route('/add', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def add():
    if request.method == 'POST':
        description = request.form.get('description')
        amount = request.form.get('amount')
        category = request.form.get('category')
        date = request.form.get('date')
        vendor = request.form.get('vendor')
        hostel_name = request.form.get('hostel_name')
        notes = request.form.get('notes')
        
        if not all([description, amount, category, date]):
            flash('Please fill in all required fields.', 'error')
            return render_template('expenses/form.html', categories=EXPENSE_CATEGORIES)
        
        try:
            amount = float(amount)
            if amount <= 0:
                flash('Amount must be greater than zero.', 'error')
                return render_template('expenses/form.html', categories=EXPENSE_CATEGORIES)
        except ValueError:
            flash('Invalid amount format.', 'error')
            return render_template('expenses/form.html', categories=EXPENSE_CATEGORIES)
        
        try:
            expense_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'error')
            return render_template('expenses/form.html', categories=EXPENSE_CATEGORIES)
        
        expense = Expense(
            description=description,
            amount=amount,
            category=category,
            date=expense_date,
            vendor=vendor,
            hostel_name=hostel_name,
            notes=notes,
            created_by=current_user.id
        )
        
        try:
            db.session.add(expense)
            db.session.commit()
            flash('Expense added successfully.', 'success')
            return redirect(url_for('expenses.index'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the expense.', 'error')
    
    return render_template('expenses/form.html', categories=EXPENSE_CATEGORIES)

@expenses_bp.route('/edit/<int:expense_id>', methods=['GET', 'POST'])
@login_required
def edit(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    
    if request.method == 'POST':
        expense.description = request.form.get('description')
        expense.amount = float(request.form.get('amount'))
        expense.category = request.form.get('category')
        expense.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        expense.vendor = request.form.get('vendor')
        expense.hostel_name = request.form.get('hostel_name')
        expense.notes = request.form.get('notes')
        
        try:
            db.session.commit()
            flash('Expense updated successfully.', 'success')
            return redirect(url_for('expenses.index'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the expense.', 'error')
    
    return render_template('expenses/form.html', expense=expense, categories=EXPENSE_CATEGORIES)

@expenses_bp.route('/delete/<int:expense_id>', methods=['POST'])
@login_required
def delete(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    
    try:
        db.session.delete(expense)
        db.session.commit()
        flash('Expense deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the expense.', 'error')
    
    return redirect(url_for('expenses.index'))
