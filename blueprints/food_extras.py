from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, session
from flask_login import login_required, current_user
from models import Service, TenantService, Tenant, db
from extensions import db as db_ext
from notification_service import NotificationService
from datetime import datetime, date, timedelta
from sqlalchemy import and_

food_extras_bp = Blueprint('food_extras', __name__, url_prefix='/food-extras')

@food_extras_bp.route('/test-buttons')
def test_buttons():
    """Test route for button functionality without authentication"""
    return render_template('test_buttons.html')

@food_extras_bp.route('/debug')
@login_required
def debug():
    """Debug route to check services and database"""
    try:
        # Check if we can query services
        all_services = Service.query.all()
        active_services = Service.query.filter_by(is_active=True).all()
        
        # Check if we can query TenantService
        all_tenant_services = TenantService.query.all()
        
        debug_info = {
            'total_services': len(all_services),
            'active_services': len(active_services),
            'total_tenant_services': len(all_tenant_services),
            'service_names': [s.name for s in all_services],
            'active_service_names': [s.name for s in active_services],
            'database_connected': True
        }
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({
            'error': str(e),
            'database_connected': False
        })

@food_extras_bp.route('/')
@login_required
def index():
    """Food & Extras dashboard"""
    # Get today's date
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    
    # Get active services
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    
    # Get today's meal orders
    today_orders = TenantService.query.filter(
        and_(
            TenantService.start_date <= today,
            TenantService.end_date >= today
        )
    ).all()
    
    # Get upcoming orders
    upcoming_orders = TenantService.query.filter(
        TenantService.start_date > today
    ).order_by(TenantService.start_date).limit(10).all()
    
    # Calculate statistics
    total_services = Service.query.filter_by(is_active=True).count()
    active_orders = TenantService.query.filter(
        and_(
            TenantService.start_date <= today,
            TenantService.end_date >= today
        )
    ).count()
    
    # Calculate total meals (sum of quantities for today's orders)
    from sqlalchemy import func
    total_meals = db.session.query(func.sum(TenantService.quantity)).filter(
        and_(
            TenantService.start_date <= today,
            TenantService.end_date >= today
        )
    ).scalar() or 0
    
    # Calculate meal counts by category for today
    meal_counts = {
        'breakfast': db.session.query(func.sum(TenantService.quantity)).join(Service).filter(
            and_(
                TenantService.start_date <= today,
                TenantService.end_date >= today,
                Service.service_type.in_(['meal', 'restaurant']),
                Service.meal_category == 'breakfast'
            )
        ).scalar() or 0,
        'dinner': db.session.query(func.sum(TenantService.quantity)).join(Service).filter(
            and_(
                TenantService.start_date <= today,
                TenantService.end_date >= today,
                Service.service_type.in_(['meal', 'restaurant']),
                Service.meal_category == 'dinner'
            )
        ).scalar() or 0
    }
    
    return render_template('food_extras/index.html',
                         services=services,
                         today_orders=today_orders,
                         upcoming_orders=upcoming_orders,
                         total_services=total_services,
                         active_orders=active_orders,
                         total_meals=total_meals,
                         meal_counts=meal_counts,
                         today=today,
                         yesterday=yesterday,
                         tomorrow=tomorrow)

@food_extras_bp.route('/services')
@login_required
def services():
    """Manage food and extra services"""
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    
    return render_template('food_extras/services.html',
                         services=services)

@food_extras_bp.route('/services/add', methods=['GET', 'POST'])
@login_required
def add_service():
    """Add new food or extra service"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        service_type = request.form.get('service_type')
        meal_category = request.form.get('meal_category')
        preparation_time = request.form.get('preparation_time')
        
        if not all([name, price, service_type]):
            flash('Please fill in all required fields.', 'error')
            return render_template('food_extras/service_form.html')
        
        try:
            service = Service(
                name=name,
                description=description,
                price=float(price),
                service_type=service_type,
                meal_category=meal_category if meal_category else None,
                preparation_time=int(preparation_time) if preparation_time else None,
                is_active=True
            )
            
            db_ext.session.add(service)
            db_ext.session.commit()
            
            flash(f'Service "{name}" added successfully!', 'success')
            return redirect(url_for('food_extras.services'))
            
        except ValueError:
            flash('Please enter valid numbers for price and price.', 'error')
        except Exception as e:
            db_ext.session.rollback()
            flash(f'Error adding service: {str(e)}', 'error')
    
    return render_template('food_extras/service_form.html')

@food_extras_bp.route('/services/<int:service_id>')
@login_required
def view_service(service_id):
    """View service details"""
    service = Service.query.get_or_404(service_id)
    
    # Get recent orders for this service
    recent_orders = TenantService.query.filter_by(service_id=service_id)\
        .join(Tenant)\
        .order_by(TenantService.start_date.desc())\
        .limit(5).all()
    
    return render_template('food_extras/service_view.html',
                         service=service,
                         recent_orders=recent_orders)

@food_extras_bp.route('/services/<int:service_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_service(service_id):
    """Edit existing service"""
    service = Service.query.get_or_404(service_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        service_type = request.form.get('service_type')
        meal_category = request.form.get('meal_category')
        preparation_time = request.form.get('preparation_time')
        is_active = request.form.get('is_active') == 'on'
        
        if not all([name, price, service_type]):
            flash('Please fill in all required fields.', 'error')
            return render_template('food_extras/service_form.html', service=service)
        
        try:
            service.name = name
            service.description = description
            service.price = float(price)
            service.service_type = service_type
            service.meal_category = meal_category if meal_category else None
            service.preparation_time = int(preparation_time) if preparation_time else None
            service.is_active = is_active
            
            db_ext.session.commit()
            
            flash(f'Service "{name}" updated successfully!', 'success')
            return redirect(url_for('food_extras.services'))
            
        except ValueError:
            flash('Please enter valid numbers for price and preparation time.', 'error')
        except Exception as e:
            db_ext.session.rollback()
            flash(f'Error updating service: {str(e)}', 'error')
    
    return render_template('food_extras/service_form.html', service=service)

@food_extras_bp.route('/services/<int:service_id>/deactivate', methods=['POST'])
@login_required
def deactivate_service(service_id):
    """Deactivate a service"""
    service = Service.query.get_or_404(service_id)
    
    try:
        service.is_active = False
        db_ext.session.commit()
        flash(f'Service "{service.name}" deactivated successfully!', 'success')
    except Exception as e:
        db_ext.session.rollback()
        flash(f'Error deactivating service: {str(e)}', 'error')
    
    return redirect(url_for('food_extras.services'))

@food_extras_bp.route('/assign-service', methods=['GET', 'POST'])
@login_required
def assign_service():
    """Quick assign extra service to a guest"""
    if request.method == 'POST':
        tenant_id = request.form.get('tenant_id')
        service_id = request.form.get('service_id')
        quantity = request.form.get('quantity', 1)
        custom_price = request.form.get('custom_price')
        notes = request.form.get('notes')
        
        # Validation
        if not all([tenant_id, service_id]):
            flash('Please select both a guest and a service.', 'error')
            return redirect(url_for('food_extras.assign_service'))
        
        try:
            tenant = Tenant.query.get_or_404(tenant_id)
            service = Service.query.get_or_404(service_id)
            
            # Use custom price if provided, otherwise use service price
            unit_price = float(custom_price) if custom_price else service.price
            quantity = int(quantity)
            
            if unit_price <= 0:
                flash('Price must be greater than 0.', 'error')
                return redirect(url_for('food_extras.assign_service'))
            
            if quantity <= 0:
                flash('Quantity must be greater than 0.', 'error')
                return redirect(url_for('food_extras.assign_service'))
            
            # Create tenant service assignment
            tenant_service = TenantService(
                tenant_id=tenant.id,
                service_id=service.id,
                quantity=quantity,
                unit_price=unit_price,
                start_date=date.today(),
                end_date=date.today(),  # Same day for immediate services
                notes=notes,
                created_at=datetime.utcnow()
            )
            
            db_ext.session.add(tenant_service)
            db_ext.session.commit()
            
            # Create notification for kitchen staff if it's a food service
            print(f"🍽️ DEBUG: Checking service for notification - service_type: {service.service_type}, service_name: {service.name}")
            is_food_service = (service.service_type in ['restaurant', 'meal'] or 
                             'food' in service.name.lower() or 
                             'meal' in service.name.lower())
            print(f"🍽️ DEBUG: Is food service: {is_food_service}")
            
            if is_food_service:
                print(f"🍽️ DEBUG: Creating notification for food order - Service: {service.name}, Guest: {tenant.name}")
                notification = NotificationService.notify_all_users(
                    title="New Food Order",
                    message=f"New order: {service.name} x{quantity} for guest {tenant.name}. Total: {unit_price * quantity:.2f} MAD",
                    notification_type='food_order',
                    related_entity_type='tenant_service',
                    related_entity_id=tenant_service.id,
                    priority='high',
                    data={
                        'guest_name': tenant.name,
                        'service_name': service.name,
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'total_price': unit_price * quantity,
                        'notes': notes,
                        'order_date': date.today().isoformat()
                    }
                )
                if notification:
                    print(f"✅ DEBUG: Food order notification created successfully with ID: {notification.id}")
                else:
                    print("❌ DEBUG: Failed to create food order notification")
            else:
                print("🍽️ DEBUG: Service is not a food service, skipping notification")
            
            flash(f'Service "{service.name}" assigned to {tenant.name} successfully!', 'success')
            return redirect(url_for('food_extras.assign_service'))
            
        except ValueError:
            flash('Please enter valid numbers for quantity and price.', 'error')
        except Exception as e:
            db_ext.session.rollback()
            flash(f'Error assigning service: {str(e)}', 'error')
    
    # GET: Show assignment form
    # Get active guests
    active_guests = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    
    # Get active services (excluding meal plans)
    services = Service.query.filter(
        and_(
            Service.is_active == True,
            Service.service_type != 'meal_plan'
        )
    ).order_by(Service.name).all()
    
    return render_template('food_extras/assign_service.html',
                         guests=active_guests,
                         services=services)

@food_extras_bp.route('/bulk-assign', methods=['GET', 'POST'])
@login_required
def bulk_assign_service():
    """Bulk assign extra services to multiple guests"""
    if request.method == 'POST':
        guest_ids = request.form.get('guest_ids[]', '').split(',') if request.form.get('guest_ids[]') else []
        service_ids = request.form.get('service_ids[]', '').split(',') if request.form.get('service_ids[]') else []
        quantities = request.form.get('quantities[]', '').split(',') if request.form.get('quantities[]') else []
        custom_prices = request.form.get('custom_prices[]', '').split(',') if request.form.get('custom_prices[]') else []
        notes = request.form.get('bulk_notes', '')
        dietary_notes = request.form.get('dietary_notes', '')
        vegetarian_guests = request.form.get('vegetarian_guests[]', '').split(',') if request.form.get('vegetarian_guests[]') else []
        service_date_str = request.form.get('service_date', '')
        
        # Validation
        if not guest_ids:
            flash('Please select at least one guest.', 'error')
            return redirect(url_for('food_extras.bulk_assign_service'))
        
        if not service_ids:
            flash('Please select at least one service.', 'error')
            return redirect(url_for('food_extras.bulk_assign_service'))
        
        try:
            # Start transaction
            success_count = 0
            failed_assignments = []
            
            for i, guest_id in enumerate(guest_ids):
                for j, service_id in enumerate(service_ids):
                    try:
                        tenant = Tenant.query.get(guest_id)
                        service = Service.query.get(service_id)
                        
                        if not tenant or not service:
                            failed_assignments.append(f"Guest {guest_id} or Service {service_id} not found")
                            continue
                        
                        # Get quantity and price for this combination
                        quantity = int(quantities[i * len(service_ids) + j]) if quantities else 1
                        custom_price = custom_prices[i * len(service_ids) + j] if custom_prices else None
                        
                        # Use custom price if provided, otherwise use service price
                        unit_price = float(custom_price) if custom_price else service.price
                        
                        if unit_price <= 0:
                            failed_assignments.append(f"Invalid price for {tenant.name} - {service.name}")
                            continue
                        
                        if quantity <= 0:
                            failed_assignments.append(f"Invalid quantity for {tenant.name} - {service.name}")
                            continue
                        
                        # Create tenant service assignment
                        # Combine notes with dietary information if this guest is vegetarian
                        combined_notes = notes
                        if str(tenant.id) in vegetarian_guests:
                            combined_notes = f"{notes}\n\nDIETARY: Vegetarian guest"
                            if dietary_notes:
                                combined_notes += f"\nDietary notes: {dietary_notes}"
                        elif dietary_notes:
                            combined_notes = f"{notes}\n\nDIETARY: {dietary_notes}"
                        
                                                # Parse service date
                        try:
                            if service_date_str:
                                service_date = datetime.strptime(service_date_str, '%Y-%m-%d').date()
                            else:
                                service_date = date.today()
                        except ValueError:
                            service_date = date.today()
                        
                        tenant_service = TenantService(
                            tenant_id=tenant.id,
                            service_id=service.id,
                            quantity=quantity,
                            unit_price=unit_price,
                            start_date=service_date,
                            end_date=service_date,
                            notes=combined_notes,
                            created_at=datetime.utcnow()
                        )
                        
                        db_ext.session.add(tenant_service)
                        success_count += 1
                        
                    except Exception as e:
                        failed_assignments.append(f"Error assigning {service.name} to {tenant.name}: {str(e)}")
                        continue
            
            # Commit all successful assignments
            if success_count > 0:
                db_ext.session.commit()
                flash(f'Successfully assigned services to {success_count} guest-service combinations!', 'success')
                
                if failed_assignments:
                    flash(f'{len(failed_assignments)} assignments failed. Check details below.', 'warning')
                    # Store failed assignments in session for display
                    session['failed_assignments'] = failed_assignments
            else:
                db_ext.session.rollback()
                flash('No services were assigned. Please check your selections.', 'error')
            
            return redirect(url_for('food_extras.bulk_assign_service'))
            
        except Exception as e:
            db_ext.session.rollback()
            flash(f'Error during bulk assignment: {str(e)}', 'error')
    
    # GET: Show bulk assignment form
    # Get active guests
    active_guests = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    
    # Get active services (excluding meal plans)
    services = Service.query.filter(
        and_(
            Service.is_active == True,
            Service.service_type != 'meal_plan'
        )
    ).order_by(Service.name).all()
    
    # Get failed assignments from previous attempt
    failed_assignments = session.pop('failed_assignments', []) if 'failed_assignments' in session else []
    
    return render_template('food_extras/bulk_assign.html',
                         guests=active_guests,
                         services=services,
                         failed_assignments=failed_assignments)



@food_extras_bp.route('/guest-services/<int:tenant_id>')
@login_required
def guest_services(tenant_id):
    """View all services assigned to a specific guest"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    # Get all services assigned to this guest
    tenant_services = TenantService.query.filter_by(tenant_id=tenant.id)\
        .join(Service)\
        .order_by(TenantService.created_at.desc()).all()
    
    # Calculate totals
    total_amount = sum(ts.quantity * ts.unit_price for ts in tenant_services)
    total_services = len(tenant_services)
    
    return render_template('food_extras/guest_services.html',
                         tenant=tenant,
                         tenant_services=tenant_services,
                         total_amount=total_amount,
                         total_services=total_services)

@food_extras_bp.route('/remove-service/<int:tenant_service_id>', methods=['POST'])
@login_required
def remove_service(tenant_service_id):
    """Remove a service assignment from a guest"""
    tenant_service = TenantService.query.get_or_404(tenant_service_id)
    tenant_name = tenant_service.tenant.name
    service_name = tenant_service.service.name
    
    try:
        db_ext.session.delete(tenant_service)
        db_ext.session.commit()
        
        flash(f'Service "{service_name}" removed from {tenant_name} successfully!', 'success')
    except Exception as e:
        db_ext.session.rollback()
        flash(f'Error removing service: {str(e)}', 'error')
    
    return redirect(url_for('food_extras.guest_services', tenant_id=tenant_service.tenant_id))

@food_extras_bp.route('/orders')
@login_required
def orders():
    """View all food and extra service orders"""
    # Get filter parameters
    date_filter = request.args.get('date', 'today')
    service_filter = request.args.get('service', '')
    
    # Build query
    query = TenantService.query.join(Service).join(Tenant)
    
    # Apply date filter
    if date_filter == 'today':
        today = date.today()
        query = query.filter(
            and_(
                TenantService.start_date <= today,
                TenantService.end_date >= today
            )
        )
    elif date_filter == 'tomorrow':
        tomorrow = date.today() + timedelta(days=1)
        query = query.filter(
            and_(
                TenantService.start_date <= tomorrow,
                TenantService.end_date >= tomorrow
            )
        )
    elif date_filter == 'week':
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_end = week_start + timedelta(days=6)
        query = query.filter(
            and_(
                TenantService.start_date <= week_end,
                TenantService.end_date >= week_start
            )
        )
    
    # Apply service filter
    if service_filter:
        query = query.filter(Service.name.ilike(f'%{service_filter}%'))
    
    orders = query.order_by(TenantService.start_date).all()
    
    return render_template('food_extras/orders.html',
                         orders=orders,
                         date_filter=date_filter,
                         service_filter=service_filter,
                         today=date.today())

@food_extras_bp.route('/daily-summary')
@login_required
def daily_summary():
    """Daily summary of food and extra services"""
    selected_date = request.args.get('date', date.today().isoformat())
    
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    
    # Get orders for selected date
    daily_orders = TenantService.query.filter(
        and_(
            TenantService.start_date <= selected_date,
            TenantService.end_date >= selected_date
        )
    ).join(Service).join(Tenant).order_by(Service.name).all()
    
    # Group by service
    service_summary = {}
    for order in daily_orders:
        service_name = order.service.name
        if service_name not in service_summary:
            service_summary[service_name] = {
                'total_quantity': 0,
                'total_revenue': 0,
                'orders': []
            }
        
        service_summary[service_name]['total_quantity'] += order.quantity
        service_summary[service_name]['total_revenue'] += order.quantity * order.unit_price
        service_summary[service_name]['orders'].append(order)
    
    return render_template('food_extras/daily_summary.html',
                         service_summary=service_summary,
                         selected_date=selected_date)

@food_extras_bp.route('/api/quick-stats')
@login_required
def quick_stats():
    """API endpoint for quick dashboard stats"""
    try:
        today = date.today()
        
        # Today's orders
        today_orders = TenantService.query.filter(
            and_(
                TenantService.start_date <= today,
                TenantService.end_date >= today
            )
        ).count()
        
        # Total active services
        total_services = Service.query.filter_by(is_active=True).count()
        
        # Revenue today
        today_revenue = db_ext.session.query(
            db_ext.func.sum(TenantService.quantity * TenantService.unit_price)
        ).filter(
            and_(
                TenantService.start_date <= today,
                TenantService.end_date >= today
            )
        ).scalar() or 0
        
        return jsonify({
            'success': True,
            'stats': {
                'today_orders': today_orders,
                'total_services': total_services,
                'today_revenue': float(today_revenue)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
