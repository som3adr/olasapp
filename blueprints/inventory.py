from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import InventoryItem, InventoryTransaction, INVENTORY_CATEGORIES, Bed, Tenant
from extensions import db
from datetime import datetime

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

@inventory_bp.route('/')
@login_required
def index():
    items = InventoryItem.query.order_by(InventoryItem.name).all()
    
    # Mark items with low stock
    for item in items:
        item.is_low_stock = item.current_stock <= item.minimum_stock
    
    # Get recent inventory transactions for global history
    recent_transactions = InventoryTransaction.query.order_by(
        InventoryTransaction.created_at.desc()
    ).limit(50).all()
    
    # Get transaction summary statistics
    from sqlalchemy import func
    transaction_stats = db.session.query(
        func.count(InventoryTransaction.id).label('total_transactions'),
        func.sum(InventoryTransaction.total_cost).label('total_value'),
        func.count(InventoryTransaction.id).filter(InventoryTransaction.transaction_type == 'purchase').label('purchases'),
        func.count(InventoryTransaction.id).filter(InventoryTransaction.transaction_type == 'consumption').label('consumptions'),
        func.count(InventoryTransaction.id).filter(InventoryTransaction.transaction_type == 'adjustment').label('adjustments')
    ).first()
    
    # Beds occupancy snapshot
    beds = Bed.query.all()
    occupied_beds = sum(1 for b in beds if b.is_occupied)
    available_beds = len(beds) - occupied_beds
    
    return render_template('inventory/index.html', 
                         items=items, 
                         occupied_beds=occupied_beds,
                         available_beds=available_beds,
                         recent_transactions=recent_transactions,
                         transaction_stats=transaction_stats)

@inventory_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        unit = request.form.get('unit')
        current_stock = request.form.get('current_stock', 0)
        minimum_stock = request.form.get('minimum_stock', 0)
        cost_per_unit = request.form.get('cost_per_unit', 0)
        supplier = request.form.get('supplier')
        
        if not all([name, category, unit]):
            flash('Please fill in all required fields.', 'error')
            return render_template('inventory/form.html', categories=INVENTORY_CATEGORIES)
        
        try:
            current_stock = int(current_stock)
            minimum_stock = int(minimum_stock)
            cost_per_unit = float(cost_per_unit)
        except ValueError:
            flash('Invalid number format.', 'error')
            return render_template('inventory/form.html', categories=INVENTORY_CATEGORIES)
        
        item = InventoryItem(
            name=name,
            category=category,
            unit=unit,
            current_stock=current_stock,
            minimum_stock=minimum_stock,
            cost_per_unit=cost_per_unit,
            supplier=supplier
        )
        
        try:
            db.session.add(item)
            db.session.commit()
            flash('Inventory item added successfully.', 'success')
            return redirect(url_for('inventory.index'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the item.', 'error')
    
    return render_template('inventory/form.html', categories=INVENTORY_CATEGORIES)

@inventory_bp.route('/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
def edit(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        item.name = request.form.get('name')
        item.category = request.form.get('category')
        item.unit = request.form.get('unit')
        item.minimum_stock = int(request.form.get('minimum_stock', 0))
        item.cost_per_unit = float(request.form.get('cost_per_unit', 0))
        item.supplier = request.form.get('supplier')
        
        try:
            db.session.commit()
            flash('Inventory item updated successfully.', 'success')
            return redirect(url_for('inventory.index'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the item.', 'error')
    
    return render_template('inventory/form.html', item=item, categories=INVENTORY_CATEGORIES)

@inventory_bp.route('/<int:item_id>/transactions')
@login_required
def transactions(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    transactions = InventoryTransaction.query.filter_by(item_id=item_id).order_by(
        InventoryTransaction.date.asc()
    ).all()
    
    return render_template('inventory/transactions.html', item=item, transactions=transactions)

@inventory_bp.route('/<int:item_id>/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    
    if request.method == 'POST':
        transaction_type = request.form.get('transaction_type')
        quantity = request.form.get('quantity')
        cost_per_unit = request.form.get('cost_per_unit', 0)
        date = request.form.get('date')
        notes = request.form.get('notes')
        
        if not all([transaction_type, quantity, date]):
            flash('Please fill in all required fields.', 'error')
            return render_template('inventory/transaction_form.html', item=item)
        
        try:
            quantity = int(quantity)
            cost_per_unit = float(cost_per_unit) if cost_per_unit else 0
            date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid number or date format.', 'error')
            return render_template('inventory/transaction_form.html', item=item)
        
        total_cost = quantity * cost_per_unit if cost_per_unit > 0 else 0
        
        # Calculate running stock after this transaction
        if transaction_type == 'purchase':
            running_stock = item.current_stock + quantity
        elif transaction_type == 'consumption':
            running_stock = item.current_stock - quantity
            if running_stock < 0:
                running_stock = 0
        else:  # adjustment
            running_stock = item.current_stock + quantity
            if running_stock < 0:
                running_stock = 0
        
        transaction = InventoryTransaction(
            item_id=item_id,
            transaction_type=transaction_type,
            quantity=quantity,
            cost_per_unit=cost_per_unit if cost_per_unit > 0 else None,
            total_cost=total_cost if total_cost > 0 else None,
            date=date,
            notes=notes,
            running_stock=running_stock,
            created_by=current_user.id
        )
        
        # Update item stock
        if transaction_type == 'purchase':
            item.current_stock += quantity
            if cost_per_unit > 0:
                item.cost_per_unit = cost_per_unit
                item.last_purchased = date
        elif transaction_type == 'consumption':
            item.current_stock -= quantity
            if item.current_stock < 0:
                item.current_stock = 0
        elif transaction_type == 'adjustment':
            # For adjustments, quantity can be positive or negative
            item.current_stock += quantity
            if item.current_stock < 0:
                item.current_stock = 0
        
        try:
            db.session.add(transaction)
            db.session.commit()
            flash('Transaction recorded successfully.', 'success')
            return redirect(url_for('inventory.transactions', item_id=item_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while recording the transaction.', 'error')
    
    return render_template('inventory/transaction_form.html', item=item)

@inventory_bp.route('/delete/<int:item_id>', methods=['POST'])
@login_required
def delete(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    
    try:
        # Check if there are any related transactions
        transaction_count = InventoryTransaction.query.filter_by(item_id=item_id).count()
        
        if transaction_count > 0:
            # Delete all related transactions first
            InventoryTransaction.query.filter_by(item_id=item_id).delete()
            flash(f'Deleted {transaction_count} related transactions and the inventory item.', 'success')
        else:
            flash('Inventory item deleted successfully.', 'success')
        
        # Now delete the item
        db.session.delete(item)
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting inventory item: {str(e)}")  # Debug logging
        flash('An error occurred while deleting the item. Please check if there are any related records.', 'error')
    
    return redirect(url_for('inventory.index'))

@inventory_bp.route('/transactions')
@login_required
def global_transactions():
    """Global view of all inventory transactions with filtering and pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    transaction_type = request.args.get('type', '')
    category = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = InventoryTransaction.query
    
    if transaction_type:
        query = query.filter(InventoryTransaction.transaction_type == transaction_type)
    if category:
        query = query.join(InventoryItem).filter(InventoryItem.category == category)
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(InventoryTransaction.date >= from_date)
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(InventoryTransaction.date <= to_date)
        except ValueError:
            pass
    
    # Get paginated results
    transactions = query.order_by(InventoryTransaction.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get summary statistics
    from sqlalchemy import func
    stats = db.session.query(
        func.count(InventoryTransaction.id).label('total_transactions'),
        func.sum(InventoryTransaction.total_cost).label('total_value'),
        func.count(InventoryTransaction.id).filter(InventoryTransaction.transaction_type == 'purchase').label('purchases'),
        func.count(InventoryTransaction.id).filter(InventoryTransaction.transaction_type == 'consumption').label('consumptions'),
        func.count(InventoryTransaction.id).filter(InventoryTransaction.transaction_type == 'adjustment').label('adjustments')
    ).first()
    
    # Get available categories for filter
    categories = db.session.query(InventoryItem.category).distinct().all()
    categories = [cat[0] for cat in categories]
    
    return render_template('inventory/global_transactions.html',
                         transactions=transactions,
                         stats=stats,
                         categories=categories,
                         filters={
                             'type': transaction_type,
                             'category': category,
                             'date_from': date_from,
                             'date_to': date_to
                         })
