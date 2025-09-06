from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import RestaurantOrder, Service, Tenant, TenantService, db
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_

restaurant_orders_bp = Blueprint('restaurant_orders', __name__, url_prefix='/restaurant-orders')

def auto_generate_meal_orders(target_date):
    """Automatically generate breakfast and dinner orders for guests with meal services"""
    try:
        # Get breakfast service
        breakfast_service = Service.query.filter_by(
            name='Breakfast',
            meal_category='breakfast',
            is_active=True
        ).first()
        
        # Get dinner service
        dinner_service = Service.query.filter_by(
            name='Dinner',
            meal_category='dinner',
            is_active=True
        ).first()
        
        # Generate breakfast orders
        if breakfast_service:
            tenants_with_breakfast = Tenant.query.join(TenantService).filter(
                and_(
                    Tenant.is_active == True,
                    TenantService.service_id == breakfast_service.id,
                    TenantService.quantity > 0
                )
            ).distinct().all()
            
            for tenant in tenants_with_breakfast:
                # Get tenant's breakfast service details
                breakfast_service_detail = TenantService.query.filter_by(
                    tenant_id=tenant.id,
                    service_id=breakfast_service.id
                ).first()
                
                if not breakfast_service_detail:
                    continue
                
                # Determine the date range for the service
                service_start = breakfast_service_detail.start_date or tenant.start_date
                service_end = breakfast_service_detail.end_date or tenant.end_date
                
                if not service_start or not service_end:
                    continue
                
                # Check if target date falls within the service period
                if not (service_start <= target_date <= service_end):
                    continue
                
                # Check for existing orders to prevent duplicates
                existing_order = RestaurantOrder.query.filter_by(
                    tenant_id=tenant.id,
                    service_id=breakfast_service.id,
                    order_date=target_date,
                    meal_time='breakfast'
                ).first()
                
                if existing_order:
                    continue
                
                # Create the restaurant order
                order = RestaurantOrder(
                    tenant_id=tenant.id,
                    service_id=breakfast_service.id,
                    order_date=target_date,
                    meal_time='breakfast',
                    quantity=tenant.number_of_guests,
                    special_requests=f'Auto-generated for {tenant.name}',
                    status='pending',
                    created_by=current_user.id if current_user.is_authenticated else 1
                )
                
                db.session.add(order)
        
        # Generate dinner orders
        if dinner_service:
            tenants_with_dinner = Tenant.query.join(TenantService).filter(
                and_(
                    Tenant.is_active == True,
                    TenantService.service_id == dinner_service.id,
                    TenantService.quantity > 0
                )
            ).distinct().all()
            
            for tenant in tenants_with_dinner:
                # Get tenant's dinner service details
                dinner_service_detail = TenantService.query.filter_by(
                    tenant_id=tenant.id,
                    service_id=dinner_service.id
                ).first()
                
                if not dinner_service_detail:
                    continue
                
                # Determine the date range for the service
                service_start = dinner_service_detail.start_date or tenant.start_date
                service_end = dinner_service_detail.end_date or tenant.end_date
                
                if not service_start or not service_end:
                    continue
                
                # Check if target date falls within the service period
                if not (service_start <= target_date <= service_end):
                    continue
                
                # Check for existing orders to prevent duplicates
                existing_order = RestaurantOrder.query.filter_by(
                    tenant_id=tenant.id,
                    service_id=dinner_service.id,
                    order_date=target_date,
                    meal_time='dinner'
                ).first()
                
                if existing_order:
                    continue
                
                # Create the restaurant order
                order = RestaurantOrder(
                    tenant_id=tenant.id,
                    service_id=dinner_service.id,
                    order_date=target_date,
                    meal_time='dinner',
                    quantity=tenant.number_of_guests,
                    special_requests=f'Auto-generated for {tenant.name}',
                    status='pending',
                    created_by=current_user.id if current_user.is_authenticated else 1
                )
                
                db.session.add(order)
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        print(f"Error auto-generating meal orders: {str(e)}")

@restaurant_orders_bp.route('/')
@login_required
def index():
    """Display today's orders from TenantService for kitchen staff"""
    selected_date = request.args.get('date', date.today().isoformat())
    meal_time = request.args.get('meal_time', 'all')
    status = request.args.get('status', 'all')
    
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    
    # Auto-generate meal orders (breakfast and dinner) for the selected date
    auto_generate_meal_orders(selected_date)
    
    # Get RestaurantOrder entries (auto-generated orders)
    restaurant_order_query = RestaurantOrder.query.join(Service).filter(
        RestaurantOrder.order_date == selected_date
    )
    
    if meal_time != 'all':
        restaurant_order_query = restaurant_order_query.filter(Service.meal_category == meal_time)
    
    if status != 'all':
        restaurant_order_query = restaurant_order_query.filter(RestaurantOrder.status == status)
    
    restaurant_orders = restaurant_order_query.order_by(RestaurantOrder.created_at).all()
    
    # Get dinner meals from food-extras system (TenantService)
    dinner_tenant_services = TenantService.query.join(Service).join(Tenant).filter(
        and_(
            TenantService.start_date <= selected_date,
            TenantService.end_date >= selected_date,
            Service.meal_category == 'dinner',
            Tenant.is_active == True
        )
    ).all()
    
    # Convert TenantService to RestaurantOrder-like objects for display
    dinner_orders = []
    for tenant_service in dinner_tenant_services:
        # Create a mock RestaurantOrder object for display
        mock_order = type('MockOrder', (), {
            'id': f"ts_{tenant_service.id}",  # Prefix to avoid conflicts
            'tenant': tenant_service.tenant,
            'service': tenant_service.service,
            'order_date': selected_date,
            'meal_time': 'dinner',
            'quantity': tenant_service.quantity,
            'special_requests': tenant_service.notes or 'From food-extras system',
            'status': 'pending',
            'created_at': tenant_service.created_at,
            'is_from_food_extras': True  # Flag to identify source
        })()
        dinner_orders.append(mock_order)
    
    # Combine both types of orders
    orders = restaurant_orders + dinner_orders
    
    # Sort by created_at
    orders.sort(key=lambda x: x.created_at)
    
    # Get available dates for date picker (last 7 days to next 7 days)
    today = date.today()
    date_range = []
    for i in range(-7, 8):
        date_range.append(today + timedelta(days=i))
    
    # Calculate yesterday and tomorrow dates for quick navigation
    yesterday_date = selected_date - timedelta(days=1)
    tomorrow_date = selected_date + timedelta(days=1)
    
    # Calculate total quantities by meal category for the selected date (from RestaurantOrder only)
    from sqlalchemy import func
    
    # Calculate meal counts from RestaurantOrder
    restaurant_meal_counts = {
        'breakfast': db.session.query(func.sum(RestaurantOrder.quantity)).join(Service).filter(
            and_(
                RestaurantOrder.order_date == selected_date,
                Service.meal_category == 'breakfast'
            )
        ).scalar() or 0,
        'lunch': db.session.query(func.sum(RestaurantOrder.quantity)).join(Service).filter(
            and_(
                RestaurantOrder.order_date == selected_date,
                Service.meal_category == 'lunch'
            )
        ).scalar() or 0,
        'dinner': db.session.query(func.sum(RestaurantOrder.quantity)).join(Service).filter(
            and_(
                RestaurantOrder.order_date == selected_date,
                Service.meal_category == 'dinner'
            )
        ).scalar() or 0,
        'snack': db.session.query(func.sum(RestaurantOrder.quantity)).join(Service).filter(
            and_(
                RestaurantOrder.order_date == selected_date,
                Service.meal_category == 'snack'
            )
        ).scalar() or 0
    }
    
    # Calculate dinner meals from TenantService (food-extras system)
    dinner_tenant_count = db.session.query(func.sum(TenantService.quantity)).join(Service).join(Tenant).filter(
        and_(
            TenantService.start_date <= selected_date,
            TenantService.end_date >= selected_date,
            Service.meal_category == 'dinner',
            Tenant.is_active == True
        )
    ).scalar() or 0
    
    # Combine meal counts
    meal_counts = {
        'breakfast': restaurant_meal_counts['breakfast'],
        'lunch': restaurant_meal_counts['lunch'],
        'dinner': restaurant_meal_counts['dinner'] + dinner_tenant_count,
        'snack': restaurant_meal_counts['snack']
    }
    
    # Calculate total orders and total meals for summary cards
    total_orders = len(orders)
    total_meals = sum(order.quantity for order in orders)
    
    # Get unique guests and services for filtering
    unique_guests = list(set(order.tenant.name for order in orders))
    unique_services = list(set(order.service.name for order in orders))
    unique_meal_times = list(set(order.service.meal_category for order in orders if order.service.meal_category))
    
    return render_template('restaurant_orders/index.html', 
                         orders=orders, 
                         selected_date=selected_date,
                         date_range=date_range,
                         meal_time=meal_time,
                         status=status,
                         meal_counts=meal_counts,
                         yesterday_date=yesterday_date,
                         tomorrow_date=tomorrow_date,
                         date=date,
                         total_orders=total_orders,
                         total_meals=total_meals,
                         unique_guests=unique_guests,
                         unique_services=unique_services,
                         unique_meal_times=unique_meal_times)

@restaurant_orders_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create new restaurant order"""
    if request.method == 'POST':
        tenant_id = request.form.get('tenant_id')
        service_id = request.form.get('service_id')
        order_date = request.form.get('order_date')
        meal_time = request.form.get('meal_time')
        quantity = int(request.form.get('quantity', 1))
        special_requests = request.form.get('special_requests')
        
        if not all([tenant_id, service_id, order_date, meal_time]):
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('restaurant_orders.create'))
        
        try:
            order_date = datetime.strptime(order_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'error')
            return redirect(url_for('restaurant_orders.create'))
        
        # Check if tenant exists and is active
        tenant = Tenant.query.get(tenant_id)
        if not tenant or not tenant.is_active:
            flash('Selected guest is not active.', 'error')
            return redirect(url_for('restaurant_orders.create'))
        
        # Check if service exists and is available
        service = Service.query.get(service_id)
        if not service or not service.is_active:
            flash('Selected service is not available.', 'error')
            return redirect(url_for('restaurant_orders.create'))
        
        order = RestaurantOrder(
            tenant_id=tenant_id,
            service_id=service_id,
            order_date=order_date,
            meal_time=meal_time,
            quantity=quantity,
            special_requests=special_requests,
            created_by=current_user.id
        )
        
        db.session.add(order)
        db.session.commit()
        
        flash('Restaurant order created successfully!', 'success')
        return redirect(url_for('restaurant_orders.index'))
    
    # GET: Show form
    tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    services = Service.query.filter(
        and_(
            Service.is_active == True,
            or_(
                Service.service_type == 'restaurant',
                Service.service_type == 'meal'
            )
        )
    ).order_by(Service.name).all()
    
    return render_template('restaurant_orders/create.html', 
                         tenants=tenants, 
                         services=services,
                         date=date)

@restaurant_orders_bp.route('/<int:order_id>/update-status', methods=['POST'])
@login_required
def update_status(order_id):
    """Update order status (for kitchen staff)"""
    order = RestaurantOrder.query.get_or_404(order_id)
    new_status = request.form.get('status')
    
    if new_status not in ['pending', 'preparing', 'ready', 'served']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    
    order.status = new_status
    
    if new_status == 'served':
        order.served_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'message': f'Order status updated to {new_status}',
        'new_status': new_status
    })

@restaurant_orders_bp.route('/<order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    """Cancel/delete a restaurant order or food-extras service"""
    try:
        # Check if this is a food-extras order (starts with 'ts_')
        if order_id.startswith('ts_'):
            # Extract the actual TenantService ID
            tenant_service_id = int(order_id.replace('ts_', ''))
            tenant_service = TenantService.query.get_or_404(tenant_service_id)
            
            # Store order details for logging
            order_details = {
                'tenant_name': tenant_service.tenant.name,
                'service_name': tenant_service.service.name,
                'order_date': 'food-extras service',
                'meal_time': tenant_service.service.meal_category or 'general',
                'quantity': tenant_service.quantity
            }
            
            # Delete the tenant service
            db.session.delete(tenant_service)
            db.session.commit()
            
            flash(f'Food service for {order_details["tenant_name"]} ({order_details["service_name"]}) has been cancelled successfully.', 'success')
            
        else:
            # Regular restaurant order
            order = RestaurantOrder.query.get_or_404(int(order_id))
            
            # Store order details for logging
            order_details = {
                'tenant_name': order.tenant.name,
                'service_name': order.service.name,
                'order_date': order.order_date,
                'meal_time': order.meal_time,
                'quantity': order.quantity
            }
            
            # Delete the order
            db.session.delete(order)
            db.session.commit()
            
            flash(f'Order for {order_details["tenant_name"]} ({order_details["service_name"]}) has been cancelled successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error cancelling order: {str(e)}', 'error')
    
    return redirect(url_for('restaurant_orders.index'))

@restaurant_orders_bp.route('/<int:order_id>')
@login_required
def view(order_id):
    """Get order details as JSON"""
    order = RestaurantOrder.query.get_or_404(order_id)
    return jsonify({
        'id': order.id,
        'tenant': {'name': order.tenant.name},
        'service': {'name': order.service.name},
        'order_date': order.order_date.isoformat(),
        'meal_time': order.meal_time,
        'quantity': order.quantity,
        'status': order.status,
        'special_requests': order.special_requests,
        'created_at': order.created_at.isoformat()
    })

@restaurant_orders_bp.route('/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(order_id):
    """Edit restaurant order"""
    order = RestaurantOrder.query.get_or_404(order_id)
    
    if request.method == 'POST':
        service_id = request.form.get('service_id')
        order_date = request.form.get('order_date')
        meal_time = request.form.get('meal_time')
        quantity = int(request.form.get('quantity', 1))
        special_requests = request.form.get('special_requests')
        
        if not all([service_id, order_date, meal_time]):
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('restaurant_orders.edit', order_id=order_id))
        
        try:
            order_date = datetime.strptime(order_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'error')
            return redirect(url_for('restaurant_orders.edit', order_id=order_id))
        
        order.service_id = service_id
        order.order_date = order_date
        order.meal_time = meal_time
        order.quantity = quantity
        order.special_requests = special_requests
        
        db.session.commit()
        
        flash('Restaurant order updated successfully!', 'success')
        return redirect(url_for('restaurant_orders.index'))
    
    # GET: Show edit form
    services = Service.query.filter(
        and_(
            Service.is_active == True,
            or_(
                Service.service_type == 'restaurant',
                Service.service_type == 'meal'
            )
        )
    ).order_by(Service.name).all()
    
    return render_template('restaurant_orders/edit.html', 
                         order=order, 
                         services=services)

@restaurant_orders_bp.route('/<int:order_id>/delete', methods=['POST'])
@login_required
def delete(order_id):
    """Delete restaurant order"""
    order = RestaurantOrder.query.get_or_404(order_id)
    
    # Only allow deletion of pending orders
    if order.status != 'pending':
        flash('Only pending orders can be deleted.', 'error')
        return redirect(url_for('restaurant_orders.index'))
    
    db.session.delete(order)
    db.session.commit()
    
    flash('Restaurant order deleted successfully!', 'success')
    return redirect(url_for('restaurant_orders.index'))

@restaurant_orders_bp.route('/api/tenant-orders/<int:tenant_id>')
@login_required
def tenant_orders(tenant_id):
    """API endpoint to get orders for a specific tenant"""
    orders = RestaurantOrder.query.filter_by(tenant_id=tenant_id).order_by(RestaurantOrder.order_date.desc()).all()
    
    orders_data = []
    for order in orders:
        orders_data.append({
            'id': order.id,
            'service_name': order.service.name,
            'order_date': order.order_date.isoformat(),
            'meal_time': order.meal_time,
            'quantity': order.quantity,
            'status': order.status,
            'special_requests': order.special_requests,
            'created_at': order.created_at.isoformat()
        })
    
    return jsonify(orders_data)

@restaurant_orders_bp.route('/api/daily-summary')
@login_required
def daily_summary():
    """API endpoint to get daily order summary for dashboard"""
    selected_date = request.args.get('date', date.today().isoformat())
    
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    
    # Get orders by meal time for the selected date
    breakfast_orders = RestaurantOrder.query.filter(
        RestaurantOrder.order_date == selected_date,
        RestaurantOrder.meal_time == 'breakfast'
    ).count()
    
    dinner_orders = RestaurantOrder.query.filter(
        RestaurantOrder.order_date == selected_date,
        RestaurantOrder.meal_time == 'dinner'
    ).count()
    
    lunch_orders = RestaurantOrder.query.filter(
        RestaurantOrder.order_date == selected_date,
        RestaurantOrder.meal_time == 'lunch'
    ).count()
    
    pending_orders = RestaurantOrder.query.filter(
        RestaurantOrder.order_date == selected_date,
        RestaurantOrder.status == 'pending'
    ).count()
    
    return jsonify({
        'date': selected_date.isoformat(),
        'breakfast_orders': breakfast_orders,
        'dinner_orders': dinner_orders,
        'lunch_orders': lunch_orders,
        'pending_orders': pending_orders,
        'total_orders': breakfast_orders + dinner_orders + lunch_orders
    })
