from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_
from models import db, TenantService, Tenant, Bed, Stay, Service, DailyMealService
from flask_login import current_user

meals_bp = Blueprint('meals', __name__, url_prefix='/meals')

@meals_bp.route('/')
@login_required
def index():
    """Display meal plan tracking for kitchen staff"""
    # Get selected date (default to today)
    selected_date = request.args.get('date', date.today().isoformat())
    
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    
    # Get breakfast services for the selected date
    breakfast_service_id = db.session.query(Service.id).filter(Service.name == 'Breakfast').scalar()
    if breakfast_service_id:
        breakfast_services = db.session.query(
            TenantService, Tenant, Stay
        ).join(
            Tenant, TenantService.tenant_id == Tenant.id
        ).join(
            Stay, and_(Stay.tenant_id == Tenant.id, Stay.is_active == True)
        ).filter(
            TenantService.service_id == breakfast_service_id,
            TenantService.quantity > 0
        ).filter(
            (TenantService.start_date.is_(None)) | 
            (TenantService.end_date.is_(None)) | 
            ((TenantService.start_date <= selected_date) & (TenantService.end_date >= selected_date))
        ).all()
    else:
        breakfast_services = []
        print("Debug - Breakfast service not found!")
    
    # Get dinner services for the selected date
    dinner_service_id = db.session.query(Service.id).filter(Service.name == 'Dinner').scalar()
    if dinner_service_id:
        dinner_services = db.session.query(
            TenantService, Tenant, Stay
        ).join(
            Tenant, TenantService.tenant_id == Tenant.id
        ).join(
            Stay, and_(Stay.tenant_id == Tenant.id, Stay.is_active == True)
        ).filter(
            TenantService.service_id == dinner_service_id,
            TenantService.quantity > 0
        ).filter(
            (TenantService.start_date.is_(None)) | 
            (TenantService.end_date.is_(None)) | 
            ((TenantService.start_date <= selected_date) & (TenantService.end_date >= selected_date))
        ).all()
    else:
        dinner_services = []
        print("Debug - Dinner service not found!")
    
    # Debug: Print what we found
    print(f"Debug - Selected date: {selected_date}")
    print(f"Debug - Breakfast services found: {len(breakfast_services)}")
    print(f"Debug - Dinner services found: {len(dinner_services)}")
    print(f"Debug - Breakfast service ID: {breakfast_service_id}")
    print(f"Debug - Dinner service ID: {dinner_service_id}")
    
    # Check all services
    all_services = Service.query.all()
    print(f"Debug - All services: {[s.name for s in all_services]}")
    
    # Check if there are any TenantService records at all
    all_tenant_services = TenantService.query.all()
    print(f"Debug - Total TenantService records: {len(all_tenant_services)}")
    if all_tenant_services:
        sample = all_tenant_services[0]
        print(f"Debug - Sample TenantService: ID={sample.id}, tenant_id={sample.tenant_id}, service_id={sample.service_id}")
        print(f"Debug - Sample TenantService dates: start={sample.start_date}, end={sample.end_date}")
        print(f"Debug - Sample TenantService quantity: {sample.quantity}")
        
        # Check if this service is Breakfast or Dinner
        service_name = Service.query.get(sample.service_id).name if sample.service_id else "None"
        print(f"Debug - Sample service name: {service_name}")
        
        # Check active stays
        active_stays = Stay.query.filter_by(is_active=True).all()
        print(f"Debug - Active stays: {len(active_stays)}")
        if active_stays:
            print(f"Debug - Sample stay: tenant_id={active_stays[0].tenant_id}, start={active_stays[0].start_date}, end={active_stays[0].end_date}")
    
    # Count totals
    breakfast_count = sum(service.TenantService.quantity for service in breakfast_services)
    dinner_count = sum(service.TenantService.quantity for service in dinner_services)
    
    # Get available dates for date picker (last 30 days to next 30 days)
    today = date.today()
    date_range = []
    for i in range(-30, 31):
        # Use timedelta for safe date arithmetic
        check_date = today + timedelta(days=i)
        date_range.append(check_date)
    
    return render_template('meals/index.html',
                         selected_date=selected_date,
                         breakfast_services=breakfast_services,
                         dinner_services=dinner_services,
                         breakfast_count=breakfast_count,
                         dinner_count=dinner_count,
                         date_range=date_range)

@meals_bp.route('/api/meal-data/<date_str>')
@login_required
def get_meal_data(date_str):
    """API endpoint to get meal data for a specific date"""
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    
    # Get breakfast services
    breakfast_services = db.session.query(
        TenantService, Tenant, Stay
    ).join(
        Tenant, TenantService.tenant_id == Tenant.id
    ).join(
        Stay, and_(Stay.tenant_id == Tenant.id, Stay.is_active == True)
    ).filter(
        TenantService.service_id == db.session.query(Service.id).filter(Service.name == 'Breakfast').scalar(),
        TenantService.quantity > 0
    ).filter(
        (TenantService.start_date.is_(None)) | 
        (TenantService.end_date.is_(None)) | 
        ((TenantService.start_date <= selected_date) & (TenantService.end_date >= selected_date))
    ).all()
    
    # Get dinner services
    dinner_services = db.session.query(
        TenantService, Tenant, Stay
    ).join(
        Tenant, TenantService.tenant_id == Tenant.id
    ).join(
        Stay, and_(Stay.tenant_id == Tenant.id, Stay.is_active == True)
    ).filter(
        TenantService.service_id == db.session.query(Service.id).filter(Service.name == 'Dinner').scalar(),
        TenantService.quantity > 0
    ).filter(
        (TenantService.start_date.is_(None)) | 
        (TenantService.end_date.is_(None)) | 
        ((TenantService.start_date <= selected_date) & (TenantService.end_date >= selected_date))
    ).all()
    
    # Format data for JSON response
    breakfast_data = []
    for service in breakfast_services:
        breakfast_data.append({
            'guest_name': service.Tenant.name,
            'room_number': service.Tenant.room_number,
            'bed_number': '-',
            'check_in': service.Stay.start_date.strftime('%Y-%m-%d') if service.Stay.start_date else 'N/A',
            'check_out': service.Stay.end_date.strftime('%Y-%m-%d') if service.Stay.end_date else 'Ongoing',
            'quantity': service.TenantService.quantity,
            'unit_price': service.TenantService.unit_price
        })
    
    dinner_data = []
    for service in dinner_services:
        dinner_data.append({
            'guest_name': service.Tenant.name,
            'room_number': service.Tenant.room_number,
            'bed_number': '-',
            'check_in': service.Stay.start_date.strftime('%Y-%m-%d') if service.Stay.start_date else 'N/A',
            'check_out': service.Stay.end_date.strftime('%Y-%m-%d') if service.Stay.end_date else 'Ongoing',
            'quantity': service.TenantService.quantity,
            'unit_price': service.TenantService.unit_price
        })
    
    return jsonify({
        'breakfast': {
            'count': sum(service.TenantService.quantity for service in breakfast_services),
            'guests': breakfast_data
        },
        'dinner': {
            'count': sum(service.TenantService.quantity for service in dinner_services),
            'guests': dinner_data
        }
    })


# New daily meal management routes
@meals_bp.route('/daily')
@meals_bp.route('/daily/<date_str>')
@login_required
def daily_meals(date_str='today'):
    """Display daily meal management for a specific date"""
    try:
        if date_str == 'today':
            selected_date = date.today()
        else:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = date.today()
    
    # Get all active guests for this date
    active_guests = db.session.query(Tenant, Stay).join(
        Stay, and_(Stay.tenant_id == Tenant.id, Stay.is_active == True)
    ).filter(
        Stay.start_date <= selected_date,
        (Stay.end_date.is_(None) | (Stay.end_date >= selected_date))
    ).all()
    
    # Get daily meal services for this date
    daily_breakfast = DailyMealService.query.filter_by(
        meal_date=selected_date,
        service_type='breakfast',
        is_active=True
    ).all()
    
    daily_dinner = DailyMealService.query.filter_by(
        meal_date=selected_date,
        service_type='dinner',
        is_active=True
    ).all()
    
    # Count totals
    breakfast_count = sum(meal.quantity for meal in daily_breakfast)
    dinner_count = sum(meal.quantity for meal in daily_dinner)
    
    return render_template('meals/daily.html',
                         selected_date=selected_date,
                         active_guests=active_guests,
                         daily_breakfast=daily_breakfast,
                         daily_dinner=daily_dinner,
                         breakfast_count=breakfast_count,
                         dinner_count=dinner_count)


@meals_bp.route('/api/add-meal', methods=['POST'])
@login_required
def add_meal():
    """Add a meal for a specific guest and date"""
    try:
        data = request.get_json()
        tenant_id = data.get('tenant_id')
        service_type = data.get('service_type')  # 'breakfast' or 'dinner'
        meal_date = datetime.strptime(data.get('meal_date'), '%Y-%m-%d').date()
        quantity = data.get('quantity', 1)
        unit_price = data.get('unit_price', 0.0)
        notes = data.get('notes', '')
        
        # Check if meal already exists
        existing_meal = DailyMealService.query.filter_by(
            tenant_id=tenant_id,
            service_type=service_type,
            meal_date=meal_date
        ).first()
        
        if existing_meal:
            # Update existing meal
            existing_meal.quantity = quantity
            existing_meal.unit_price = unit_price
            existing_meal.notes = notes
            existing_meal.is_active = True
        else:
            # Create new meal
            new_meal = DailyMealService(
                tenant_id=tenant_id,
                service_type=service_type,
                meal_date=meal_date,
                quantity=quantity,
                unit_price=unit_price,
                notes=notes,
                created_by=current_user.id
            )
            db.session.add(new_meal)
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{service_type.title()} meal added successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@meals_bp.route('/api/remove-meal', methods=['POST'])
@login_required
def remove_meal():
    """Remove a meal for a specific guest and date"""
    try:
        data = request.get_json()
        tenant_id = data.get('tenant_id')
        service_type = data.get('service_type')
        meal_date = datetime.strptime(data.get('meal_date'), '%Y-%m-%d').date()
        
        # Find and deactivate the meal
        meal = DailyMealService.query.filter_by(
            tenant_id=tenant_id,
            service_type=service_type,
            meal_date=meal_date
        ).first()
        
        if meal:
            meal.is_active = False
            db.session.commit()
            return jsonify({'success': True, 'message': f'{service_type.title()} meal removed successfully'})
        else:
            return jsonify({'success': False, 'error': 'Meal not found'}), 404
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@meals_bp.route('/api/bulk-add-meals', methods=['POST'])
@login_required
def bulk_add_meals():
    """Add meals to multiple guests at once"""
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        service_type = data.get('service_type')  # 'breakfast' or 'dinner'
        meal_date = datetime.strptime(data.get('meal_date'), '%Y-%m-%d').date()
        quantity = data.get('quantity', 1)
        unit_price = data.get('unit_price', 0.0)
        notes = data.get('notes', '')
        
        if not guest_ids:
            return jsonify({'success': False, 'error': 'No guests selected'}), 400
        
        added_count = 0
        updated_count = 0
        
        for tenant_id in guest_ids:
            # Check if meal already exists
            existing_meal = DailyMealService.query.filter_by(
                tenant_id=tenant_id,
                service_type=service_type,
                meal_date=meal_date
            ).first()
            
            if existing_meal:
                # Update existing meal
                existing_meal.quantity = quantity
                existing_meal.unit_price = unit_price
                existing_meal.notes = notes
                existing_meal.is_active = True
                updated_count += 1
            else:
                # Create new meal
                new_meal = DailyMealService(
                    tenant_id=tenant_id,
                    service_type=service_type,
                    meal_date=meal_date,
                    quantity=quantity,
                    unit_price=unit_price,
                    notes=notes,
                    created_by=current_user.id
                )
                db.session.add(new_meal)
                added_count += 1
        
        db.session.commit()
        
        message = f"Added {added_count} new meals, updated {updated_count} existing meals"
        return jsonify({
            'success': True, 
            'message': message,
            'added': added_count,
            'updated': updated_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@meals_bp.route('/api/bulk-remove-meals', methods=['POST'])
@login_required
def bulk_remove_meals():
    """Remove meals from multiple guests at once"""
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        service_type = data.get('service_type')
        meal_date = datetime.strptime(data.get('meal_date'), '%Y-%m-%d').date()
        
        if not guest_ids:
            return jsonify({'success': False, 'error': 'No guests selected'}), 400
        
        removed_count = 0
        
        for tenant_id in guest_ids:
            meal = DailyMealService.query.filter_by(
                tenant_id=tenant_id,
                service_type=service_type,
                meal_date=meal_date
            ).first()
            
            if meal:
                meal.is_active = False
                removed_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Removed {removed_count} meals successfully',
            'removed': removed_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@meals_bp.route('/api/guest-meals/<int:tenant_id>')
@login_required
def get_guest_meals(tenant_id):
    """Get meal schedule for a specific guest"""
    try:
        # Get guest's meal schedule for next 30 days
        today = date.today()
        end_date = today + timedelta(days=30)
        
        meals = DailyMealService.query.filter(
            DailyMealService.tenant_id == tenant_id,
            DailyMealService.meal_date >= today,
            DailyMealService.meal_date <= end_date,
            DailyMealService.is_active == True
        ).order_by(DailyMealService.meal_date).all()
        
        meal_schedule = []
        for meal in meals:
            meal_schedule.append({
                'date': meal.meal_date.isoformat(),
                'service_type': meal.service_type,
                'quantity': meal.quantity,
                'unit_price': meal.unit_price,
                'notes': meal.notes
            })
        
        return jsonify({'success': True, 'meals': meal_schedule})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
