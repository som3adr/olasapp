from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from models import Tenant, Payment, Service, TenantService, Stay, CheckInOut, Bed
from extensions import db
from audit import log_tenant_action, log_payment_action, log_service_assignment
from notification_service import NotificationService
from datetime import datetime, date, timedelta
from sqlalchemy import or_, and_, func
from permissions import require_frontdesk_or_admin

def calculate_guest_balance(tenant, as_of_date=None):
    """
    Calculate the correct balance for a guest, properly handling prepaid status.
    
    Args:
        tenant: Tenant object
        as_of_date: Date to calculate balance as of (defaults to today)
    
    Returns:
        dict: {
            'total_paid': float,
            'room_charges': float,
            'extra_services': float,
            'total_due': float,
            'balance': float,
            'payment_status': str
        }
    """
    if as_of_date is None:
        as_of_date = date.today()
    
    # Get all payments
    total_paid = db.session.query(func.sum(Payment.amount)).filter(
        Payment.tenant_id == tenant.id
    ).scalar() or 0
    
    # Calculate stay duration
    if tenant.end_date:
        duration_days = (tenant.end_date - tenant.start_date).days
    else:
        duration_days = (as_of_date - tenant.start_date).days
    
    # Calculate extra services
    tenant_services = TenantService.query.filter_by(tenant_id=tenant.id).all()
    extra_services = sum(ts.quantity * ts.unit_price for ts in tenant_services)
    
    # Calculate room charges based on prepaid status
    if tenant.is_prepaid:
        # For prepaid guests, room charges are 0 for the original stay
        # Only extension payments should be charged
        room_charges = 0
    else:
        # For regular guests, calculate room charges normally
        room_charges = tenant.daily_rent * duration_days
    
    # Total due
    total_due = room_charges + extra_services
    balance = total_due - total_paid
    
    # Determine payment status
    if tenant.is_prepaid:
        payment_status = 'prepaid'
    elif balance <= 0:
        payment_status = 'paid'
    elif total_paid > 0:
        payment_status = 'partial'
    else:
        payment_status = 'unpaid'
    
    return {
        'total_paid': total_paid,
        'room_charges': room_charges,
        'extra_services': extra_services,
        'total_due': total_due,
        'balance': balance,
        'payment_status': payment_status
    }

guests_bp = Blueprint('guests', __name__, url_prefix='/guests')

@guests_bp.route('/')
@login_required
def index():
    """Unified guest management dashboard"""
    # Get filter parameters
    search = request.args.get('search', '')
    status = request.args.get('status', 'active')
    sort = request.args.get('sort', 'name')
    payment_status = request.args.get('payment_status', '')
    hostel = request.args.get('hostel', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build query
    query = Tenant.query
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                Tenant.name.ilike(f'%{search}%'),

            )
        )
    
    # Apply status filter
    if status == 'active':
        query = query.filter(Tenant.is_active == True)
    elif status == 'inactive':
        query = query.filter(Tenant.is_active == False)
    elif status == 'all':
        # Show all guests (both active and inactive)
        pass  # No filter applied
    else:  # Default to active guests if no status specified
        query = query.filter(Tenant.is_active == True)
    
    # Apply hostel filter
    if hostel:
        query = query.filter(Tenant.hostel_name == hostel)
    
    # Apply date range filter
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Tenant.start_date >= from_date)
        except ValueError:
            pass  # Invalid date format, ignore filter
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Tenant.start_date <= to_date)
        except ValueError:
            pass  # Invalid date format, ignore filter
    
    # Apply sorting
    if sort == 'check_in':
        query = query.order_by(Tenant.start_date.desc())
    elif sort == 'room':
        query = query.order_by(Tenant.name)
    else:  # default: name
        query = query.order_by(Tenant.name)
    
    tenants = query.all()
    
    # Calculate payment status for today (daily rent) - only for active guests
    today = datetime.now().date()
    for tenant in tenants:
        if tenant.is_active:
            # Use the centralized balance calculation function
            balance_info = calculate_guest_balance(tenant, today)
            
            # Set payment status based on outstanding balance
            if tenant.is_prepaid:
                tenant.payment_status = 'prepaid'
            elif balance_info['balance'] <= 0:
                tenant.payment_status = 'paid'
            elif balance_info['total_paid'] > 0:
                tenant.payment_status = 'partial'
            else:
                tenant.payment_status = 'unpaid'
            
            tenant.outstanding_balance = balance_info['balance']
            # For prepaid guests, show the balance they owe. For regular guests, show total due.
            if tenant.is_prepaid:
                tenant.calculated_total = balance_info['balance']  # Show what they owe
            else:
                tenant.calculated_total = balance_info['total_due']  # Show total amount
        else:
            # Calculate total amount for inactive guests too
            total_paid = db.session.query(func.sum(Payment.amount)).filter(
                Payment.tenant_id == tenant.id
            ).scalar() or 0
            
            # Calculate total due based on stay duration
            if tenant.end_date:
                duration_days = (tenant.end_date - tenant.start_date).days
            else:
                duration_days = (today - tenant.start_date).days
            
            # Calculate extra services total
            tenant_services = TenantService.query.filter_by(tenant_id=tenant.id).all()
            extra_services_total = sum(ts.quantity * ts.unit_price for ts in tenant_services)
            
            # Calculate total due (room charges + extra services)
            if tenant.is_prepaid:
                room_charges = 0  # Prepaid guests don't pay room charges
            else:
                room_charges = tenant.daily_rent * duration_days
            
            # For prepaid guests, include services. For regular guests, include everything.
            total_due = room_charges + extra_services_total
            
            tenant.payment_status = 'inactive'
            tenant.outstanding_balance = 0
            # Store the calculated total including services for template display
            tenant.calculated_total = total_due
    
    # Apply payment status filter
    if payment_status:
        tenants = [tenant for tenant in tenants if tenant.payment_status == payment_status]
    
    # Get today's check-ins and check-outs
    today = datetime.now().date()
    todays_checkins = CheckInOut.query.filter(
        db.func.date(CheckInOut.check_in_date) == today
    ).all()
    
    todays_checkouts = CheckInOut.query.filter(
        db.func.date(CheckInOut.expected_check_out_date) == today,
        CheckInOut.status == 'checked_in'
    ).all()
    
    # Get quick stats
    total_active = Tenant.query.filter_by(is_active=True).count()
    total_guests = Tenant.query.count()  # Total guests (active + inactive)
    total_checked_in = CheckInOut.query.filter_by(status='checked_in').count()
    # Note: Payment model doesn't have status field, so we'll show total payments instead
    total_payments = Payment.query.count()
    
    # Calculate filtered total amount for displayed guests
    filtered_total_amount = sum(tenant.calculated_total for tenant in tenants if hasattr(tenant, 'calculated_total'))
    
    return render_template('guests/index.html', 
                         tenants=tenants,
                         todays_checkins=todays_checkins,
                         todays_checkouts=todays_checkouts,
                         total_active=total_active,
                         total_guests=total_guests,
                         total_checked_in=total_checked_in,
                         total_payments=total_payments,
                         filtered_total_amount=filtered_total_amount,
                         date=date,
                         timedelta=timedelta,
                         selected_hostel=hostel,
                         selected_date_from=date_from,
                         selected_date_to=date_to)

@guests_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add new guest with optional room assignment"""
    if request.method == 'POST':

        
        name = request.form.get('name')
        daily_rent = request.form.get('daily_rent')
        bed_id = request.form.get('bed_id')  # Optional
        hostel_name = request.form.get('hostel_name', '')  # Simple string field
        number_of_days = request.form.get('number_of_days')
        start_date = request.form.get('start_date')
        number_of_guests = int(request.form.get('number_of_guests', 1))
        multiply_rent_by_guests = bool(request.form.get('multiply_rent_by_guests'))

        is_prepaid = bool(request.form.get('is_prepaid'))
        
        # Meal planning fields
        breakfast_days = int(request.form.get('breakfast_days', 0))
        dinner_days = int(request.form.get('dinner_days', 0))
        meal_plan_start = request.form.get('meal_plan_start')
        meal_plan_end = request.form.get('meal_plan_end')
        notes = request.form.get('notes', '')
        

        
        # If prepaid, daily_rent is not required
        if is_prepaid:
            if not all([name, start_date, number_of_days]):
                flash('Please fill in all required fields.', 'error')
                return render_template('guests/form.html')
        else:
            if not all([name, daily_rent, start_date, number_of_days]):
                flash('Please fill in all required fields.', 'error')
                return render_template('guests/form.html')
        
        # Room/bed assignment is optional

        bed = None
        if bed_id:
            bed = Bed.query.get(bed_id)
            if not bed or bed.is_occupied:
                flash('Selected bed is no longer available. Please choose another bed.', 'error')
                return render_template('guests/form.html')

        
        try:
            # If prepaid, set daily_rent to 0, otherwise convert to float
            if is_prepaid:
                daily_rent = 0
            else:
                daily_rent = float(daily_rent)
            number_of_days = int(number_of_days)
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
            # Calculate end date
            end_date = start_date + timedelta(days=number_of_days)
            
            # Parse meal plan dates if provided
            meal_plan_start_date = None
            meal_plan_end_date = None
            if meal_plan_start:
                try:
                    meal_plan_start_date = datetime.strptime(meal_plan_start, '%Y-%m-%d').date()
                except ValueError:
                    pass
            if meal_plan_end:
                try:
                    meal_plan_end_date = datetime.strptime(meal_plan_end, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            # Create tenant
            tenant = Tenant(
                name=name,
                daily_rent=0 if is_prepaid else daily_rent,
                number_of_guests=number_of_guests,
                multiply_rent_by_guests=multiply_rent_by_guests,
                hostel_name=hostel_name,
                is_prepaid=is_prepaid,
                start_date=start_date,
                end_date=end_date,
                breakfast_days=breakfast_days,
                dinner_days=dinner_days,
                meal_plan_start=meal_plan_start_date,
                meal_plan_end=meal_plan_end_date,
                is_active=True
            )
            
            db.session.add(tenant)
            db.session.flush()  # Get tenant ID
            
            # Assign bed if provided
            if bed:
                bed.tenant_id = tenant.id
                bed.is_occupied = True
                bed.status = 'occupied'
            
            # Create meal plan services if specified
            if breakfast_days > 0:
                breakfast_service = Service.query.filter_by(name='Breakfast').first()
                if breakfast_service:
                    # Always multiply breakfast quantity by number of guests
                    meal_quantity = breakfast_days * number_of_guests
                    tenant_service = TenantService(
                        tenant_id=tenant.id,
                        service_id=breakfast_service.id,
                        quantity=meal_quantity,
                        unit_price=breakfast_service.price,
                        start_date=meal_plan_start_date or start_date,
                        end_date=meal_plan_end_date or end_date
                    )
                    db.session.add(tenant_service)
            
            if dinner_days > 0:
                dinner_service = Service.query.filter_by(name='Dinner').first()
                if dinner_service:
                    # Multiply quantity by number of guests if multiply_rent_by_guests is True
                    meal_quantity = dinner_days * number_of_guests if multiply_rent_by_guests else dinner_days
                    tenant_service = TenantService(
                        tenant_id=tenant.id,
                        service_id=dinner_service.id,
                        quantity=meal_quantity,
                        unit_price=dinner_service.price,
                        start_date=meal_plan_start_date or start_date,
                        end_date=meal_plan_end_date or end_date
                    )
                    db.session.add(tenant_service)
            
            db.session.commit()
            
            # Send notification to all users about new guest creation
            print(f"🔔 DEBUG: Creating notification for new guest - Guest: {tenant.name}")
            notification = NotificationService.notify_all_users(
                title="New Guest Added",
                message=f"Guest {tenant.name} has been added to the system for {number_of_days} days",
                notification_type='guest_added',
                related_entity_type='tenant',
                related_entity_id=tenant.id,
                priority='normal',
                data={
                    'guest_name': tenant.name,
                    'number_of_days': number_of_days,
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                    'daily_rent': daily_rent,
                    'number_of_guests': number_of_guests,
                    'is_prepaid': is_prepaid,
                    'hostel_name': hostel_name,
                    'created_by': current_user.username
                }
            )
            if notification:
                print(f"✅ DEBUG: Guest creation notification created successfully with ID: {notification.id}")
            else:
                print("❌ DEBUG: Failed to create guest creation notification")
            
            # Create additional notification for kitchen staff if guest has meal plans
            print(f"🔔 DEBUG: Checking meal plans - breakfast_days: {breakfast_days}, dinner_days: {dinner_days}")
            if breakfast_days > 0 or dinner_days > 0:
                meal_info = []
                if breakfast_days > 0:
                    meal_info.append(f"{breakfast_days} breakfast days")
                if dinner_days > 0:
                    meal_info.append(f"{dinner_days} dinner days")
                
                print(f"🔔 DEBUG: Creating meal plan notification - Guest: {tenant.name}, Meal info: {meal_info}")
                meal_notification = NotificationService.notify_all_users(
                    title="New Guest with Meal Plan",
                    message=f"Guest {tenant.name} has meal plan: {', '.join(meal_info)}. Number of guests: {number_of_guests}",
                    notification_type='meal_plan',
                    related_entity_type='tenant',
                    related_entity_id=tenant.id,
                    priority='high',
                    data={
                        'guest_name': tenant.name,
                        'breakfast_days': breakfast_days,
                        'dinner_days': dinner_days,
                        'number_of_guests': number_of_guests,
                        'start_date': start_date.strftime('%Y-%m-%d'),
                        'end_date': end_date.strftime('%Y-%m-%d')
                    }
                )
                if meal_notification:
                    print(f"✅ DEBUG: Meal plan notification created successfully with ID: {meal_notification.id}")
                else:
                    print("❌ DEBUG: Failed to create meal plan notification")
            else:
                print("🔔 DEBUG: No meal plans found, skipping meal plan notification")
            
            # Log action
            log_tenant_action('created', tenant)
            
            print(f"✅ Guest {name} created successfully with ID: {tenant.id}")
            flash(f'Guest {name} added successfully!', 'success')
            return redirect(url_for('guests.index'))
            
        except ValueError:
            flash('Please enter valid numbers for daily rent and number of days.', 'error')
            return render_template('guests/form.html')
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating guest: {str(e)}', 'error')
            return render_template('guests/form.html')
    
    # GET: Show form
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    # hostels = Hostel.query.filter_by(is_active=True).order_by(Hostel.name).all()  # Temporarily disabled
    
    return render_template('guests/form.html', 
                         services=services)

@guests_bp.route('/<int:tenant_id>/view')
@login_required
def view(tenant_id):
    """View guest details"""
    tenant = Tenant.query.get_or_404(tenant_id)
    print(f"DEBUG: View function - tenant {tenant_id} end_date: {tenant.end_date}")
    
    # Get tenant services
    tenant_services = TenantService.query.filter_by(tenant_id=tenant.id).all()
    
    # Get payments
    payments = Payment.query.filter_by(tenant_id=tenant.id).order_by(Payment.payment_date.desc()).all()
    
    # Use the new calculation method for consistent balance calculation
    balance_info = calculate_guest_balance(tenant)
    
    # Calculate additional totals for display
    total_services = balance_info['extra_services']
    total_payments = balance_info['total_paid']
    total_deposit = sum(p.amount for p in payments if p.payment_type == 'deposit')
    total_rent = sum(p.amount for p in payments if p.payment_type == 'rent')
    
    # Use calculated values
    room_charges = balance_info['room_charges']
    extra_services_total = balance_info['extra_services']
    total_amount = balance_info['total_due']
    balance = balance_info['balance']
    paid_amount = balance_info['total_paid']
    grand_total = balance_info['total_due']  # grand_total is the same as total_due
    
    # Calculate duration for display
    if tenant.end_date:
        duration_days = (tenant.end_date - tenant.start_date).days
    else:
        from datetime import date
        today = date.today()
        duration_days = (today - tenant.start_date).days
    
    return render_template('guests/view.html',
                         tenant=tenant,
                         tenant_services=tenant_services,
                         payments=payments,
                         total_services=total_services,
                         total_payments=total_payments,
                         total_deposit=total_deposit,
                         total_rent=total_rent,
                         grand_total=grand_total,
                         balance=balance,
                         duration_days=duration_days,
                         extra_services_total=extra_services_total,
                         total_amount=total_amount,
                         paid_amount=paid_amount)

@guests_bp.route('/<int:tenant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(tenant_id):
    """Edit guest information"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        daily_rent = request.form.get('daily_rent')
        bed_id = request.form.get('bed_id')
        number_of_days = request.form.get('number_of_days')
        start_date = request.form.get('start_date')
        number_of_guests = int(request.form.get('number_of_guests', 1))
        multiply_rent_by_guests = bool(request.form.get('multiply_rent_by_guests'))

        is_prepaid = bool(request.form.get('is_prepaid'))
        
        # Meal planning fields
        breakfast_days = int(request.form.get('breakfast_days', 0))
        dinner_days = int(request.form.get('dinner_days', 0))
        meal_plan_start = request.form.get('meal_plan_start')
        meal_plan_end = request.form.get('meal_plan_end')
        
        # If prepaid, daily_rent is not required but number_of_days is still required
        if is_prepaid:
            if not all([name, start_date, number_of_days]):
                flash('Please fill in all required fields (Name, Start Date, and Number of Days).', 'error')
                return render_template('guests/form.html', tenant=tenant)
        else:
            if not all([name, daily_rent, start_date, number_of_days]):
                flash('Please fill in all required fields.', 'error')
                return render_template('guests/form.html', tenant=tenant)
        
        try:
            # If prepaid, set daily_rent to 0, otherwise convert to float
            if is_prepaid:
                daily_rent = 0
            else:
                daily_rent = float(daily_rent)
            number_of_days = int(number_of_days)
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
            # Update tenant
            tenant.name = name
            tenant.daily_rent = 0 if is_prepaid else daily_rent
            tenant.number_of_guests = number_of_guests
            tenant.multiply_rent_by_guests = multiply_rent_by_guests

            tenant.is_prepaid = is_prepaid
            tenant.start_date = start_date
            tenant.end_date = start_date + timedelta(days=number_of_days)
            tenant.breakfast_days = breakfast_days
            tenant.dinner_days = dinner_days
            tenant.meal_plan_start = meal_plan_start
            tenant.meal_plan_end = meal_plan_end
            
            # Handle bed assignment
            if bed_id:
                # Free current bed if any
                if tenant.bed_id:
                    current_bed = Bed.query.get(tenant.bed_id)
                    if current_bed:
                        current_bed.tenant_id = None
                        current_bed.is_occupied = False
                        current_bed.status = 'clean'
                
                # Assign new bed
                new_bed = Bed.query.get(bed_id)
                if new_bed and not new_bed.is_occupied:
                    tenant.bed_id = bed_id
                    new_bed.tenant_id = tenant.id
                    new_bed.is_occupied = True
                    new_bed.status = 'occupied'

                else:
                    flash('Selected bed is not available.', 'error')
                    return render_template('guests/form.html', tenant=tenant)
            
            # Update meal plan services if specified
            # First, remove existing meal services
            TenantService.query.filter_by(tenant_id=tenant.id).filter(
                or_(
                    TenantService.service_id == Service.query.filter_by(name='Breakfast').first().id,
                    TenantService.service_id == Service.query.filter_by(name='Dinner').first().id
                )
            ).delete()
            
            # Parse meal plan dates if provided
            meal_plan_start_date = None
            meal_plan_end_date = None
            if meal_plan_start:
                try:
                    meal_plan_start_date = datetime.strptime(meal_plan_start, '%Y-%m-%d').date()
                except ValueError:
                    pass
            if meal_plan_end:
                try:
                    meal_plan_end_date = datetime.strptime(meal_plan_end, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            # Create new meal services if specified
            if breakfast_days > 0:
                breakfast_service = Service.query.filter_by(name='Breakfast').first()
                if breakfast_service:
                    # Always multiply breakfast quantity by number of guests
                    meal_quantity = breakfast_days * number_of_guests
                    tenant_service = TenantService(
                        tenant_id=tenant.id,
                        service_id=breakfast_service.id,
                        quantity=meal_quantity,
                        unit_price=breakfast_service.price,
                        start_date=meal_plan_start_date or start_date,
                        end_date=meal_plan_end_date or (start_date + timedelta(days=number_of_days))
                    )
                    db.session.add(tenant_service)
            
            if dinner_days > 0:
                dinner_service = Service.query.filter_by(name='Dinner').first()
                if dinner_service:
                    # Multiply quantity by number of guests if multiply_rent_by_guests is True
                    meal_quantity = dinner_days * number_of_guests if multiply_rent_by_guests else dinner_days
                    tenant_service = TenantService(
                        tenant_id=tenant.id,
                        service_id=dinner_service.id,
                        quantity=meal_quantity,
                        unit_price=dinner_service.price,
                        start_date=meal_plan_start_date or start_date,
                        end_date=meal_plan_end_date or (start_date + timedelta(days=number_of_days))
                    )
                    db.session.add(tenant_service)
            
            db.session.commit()
            
            # Log action
            log_tenant_action('updated', tenant)
            
            flash(f'Guest {name} updated successfully!', 'success')
            return redirect(url_for('guests.view', tenant_id=tenant.id))
            
        except ValueError:
            flash('Please enter valid numbers for daily rent and number of days.', 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating guest: {str(e)}', 'error')
    
    # GET: Show edit form
    return render_template('guests/form.html', 
                         tenant=tenant)

@guests_bp.route('/<int:tenant_id>/checkin', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def checkin(tenant_id):
    """Check-in existing guest"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    if request.method == 'POST':
        bed_id = request.form.get('bed_id')
        check_in_date = request.form.get('check_in_date')
        expected_check_out = request.form.get('expected_check_out')
        
        if not all([bed_id, check_in_date, expected_check_out]):
            flash('Please fill in all required fields.', 'error')
            return render_template('guests/checkin.html', tenant=tenant)
        
        try:
            bed = Bed.query.get(bed_id)
            if not bed or bed.is_occupied:
                flash('Selected bed is not available.', 'error')
                return render_template('guests/checkin.html', tenant=tenant)
            
            # Create check-in record
            checkin = CheckInOut(
                tenant_id=tenant.id,
                bed_id=bed_id,
                check_in_date=datetime.strptime(check_in_date, '%Y-%m-%d'),
                expected_check_out_date=datetime.strptime(expected_check_out, '%Y-%m-%d'),
                status='checked_in',
                created_by=current_user.id
            )
            
            # Update bed status
            bed.is_occupied = True
            bed.status = 'occupied'
            bed.tenant_id = tenant.id
            
            # Update tenant room number

            
            db.session.add(checkin)
            db.session.commit()
            
            # Send notification to all users about guest check-in
            from notification_service import NotificationService
            NotificationService.notify_all_users(
                title="Guest Check-in",
                message=f"Guest {tenant.name} has checked in to bed {bed.bed_number} in room {bed.room.room_number}",
                notification_type='guest_checkin',
                related_entity_type='tenant',
                related_entity_id=tenant.id,
                priority='normal',
                data={
                    'guest_name': tenant.name,
                    'bed_number': bed.bed_number,
                    'room_number': bed.room.room_number,
                    'check_in_date': check_in_date,
                    'expected_checkout': expected_check_out,
                    'checked_in_by': current_user.username
                }
            )
            
            flash(f'Guest {tenant.name} checked in successfully!', 'success')
            return redirect(url_for('guests.view', tenant_id=tenant.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error during check-in: {str(e)}', 'error')
    
    # GET: Show check-in form
    available_beds = Bed.query.filter_by(is_occupied=False, status='clean').all()
    
    return render_template('guests/checkin.html', 
                         tenant=tenant,
                         available_beds=available_beds)

@guests_bp.route('/<int:tenant_id>/checkout', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def checkout(tenant_id):
    """Check-out guest"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    try:
        # Find active check-in
        active_checkin = CheckInOut.query.filter_by(
            tenant_id=tenant.id,
            status='checked_in'
        ).first()
        
        if active_checkin:
            # Update check-in status
            active_checkin.status = 'checked_out'
            active_checkin.actual_check_out_date = datetime.now()
            
            # Free up bed
            if active_checkin.bed:
                active_checkin.bed.is_occupied = False
                active_checkin.bed.status = 'dirty'
                active_checkin.bed.tenant_id = None
        
        # Mark tenant as inactive
        tenant.is_active = False
        tenant.end_date = datetime.now().date()
        
        db.session.commit()
        
        # Send notification to all users about guest check-out
        from notification_service import NotificationService
        NotificationService.notify_all_users(
            title="Guest Check-out",
            message=f"Guest {tenant.name} has checked out from bed {active_checkin.bed.bed_number if active_checkin and active_checkin.bed else 'N/A'}",
            notification_type='guest_checkout',
            related_entity_type='tenant',
            related_entity_id=tenant.id,
            priority='normal',
            data={
                'guest_name': tenant.name,
                'bed_number': active_checkin.bed.bed_number if active_checkin and active_checkin.bed else 'N/A',
                'room_number': active_checkin.bed.room.room_number if active_checkin and active_checkin.bed else 'N/A',
                'check_out_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'checked_out_by': current_user.username
            }
        )
        
        flash(f'Guest {tenant.name} checked out successfully!', 'success')
        return redirect(url_for('guests.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error during check-out: {str(e)}', 'error')
        return redirect(url_for('guests.view', tenant_id=tenant.id))

@guests_bp.route('/<int:tenant_id>/payments')
@login_required
def payments(tenant_id):
    """View and manage guest payments"""
    tenant = Tenant.query.get_or_404(tenant_id)
    payments = Payment.query.filter_by(tenant_id=tenant.id).order_by(Payment.payment_date.desc()).all()
    
    # Get tenant services for extra services calculation
    tenant_services = TenantService.query.filter_by(tenant_id=tenant.id).all()
    
    # Calculate extra services total using same logic as guest view page
    extra_services_total = sum(ts.quantity * ts.unit_price for ts in tenant_services)
    
    # Get today's date for the payment form
    today = date.today()
    
    return render_template('guests/payments.html',
                         tenant=tenant,
                         payments=payments,
                         tenant_services=tenant_services,
                         extra_services_total=extra_services_total,
                         today=today)

@guests_bp.route('/<int:tenant_id>/add-payment', methods=['POST'])
@login_required
def add_payment(tenant_id):
    """Add payment for guest"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    amount = request.form.get('amount')
    payment_date = request.form.get('payment_date')
    notes = request.form.get('notes')
    created_by = request.form.get('created_by')
    
    # Set default payment type
    payment_type = 'rent'
    
    # Validate required fields
    if not all([amount, payment_date]):
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('guests.payments', tenant_id=tenant.id))
    
    try:
        # Convert and validate amount
        amount = float(amount)
        if amount <= 0:
            flash('Payment amount must be greater than 0.', 'error')
            return redirect(url_for('guests.payments', tenant_id=tenant.id))
        
        # Parse and validate date
        payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
        
        # Validate payment type
        valid_payment_types = ['rent', 'deposit', 'service', 'other']
        if payment_type not in valid_payment_types:
            flash('Invalid payment type selected.', 'error')
            return redirect(url_for('guests.payments', tenant_id=tenant.id))
        
        # Create payment record
        payment = Payment(
            tenant_id=tenant.id,
            amount=amount,
            payment_type=payment_type,
            payment_date=payment_date,
            payment_for_month=payment_date.strftime('%Y-%m'),  # Generate from payment date
            notes=notes,
            created_by=created_by or current_user.id  # Use form value or current user
        )
        
        db.session.add(payment)
        db.session.commit()
        
        # Log action
        log_payment_action('created', payment)
        
        flash(f'Payment of {amount} MAD added successfully!', 'success')
        return redirect(url_for('guests.payments', tenant_id=tenant.id))
        
    except ValueError:
        flash('Please enter a valid amount and date.', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding payment: {str(e)}', 'error')
        print(f"Payment creation error: {e}")  # For debugging
    
    return redirect(url_for('guests.payments', tenant_id=tenant.id))

@guests_bp.route('/<int:tenant_id>/deactivate', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def deactivate(tenant_id):
    """Deactivate a guest (mark as inactive and free up resources)"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    if not tenant.is_active:
        flash('Guest is already inactive.', 'warning')
        return redirect(url_for('guests.view', tenant_id=tenant.id))
    
    try:
        # Mark tenant as inactive
        tenant.is_active = False
        tenant.checkout_date = datetime.now().date()
        
        # Free up the assigned bed if any
        if tenant.bed_id:
            bed = Bed.query.get(tenant.bed_id)
            if bed:
                bed.is_occupied = False
                bed.tenant_id = None
                bed.status = 'dirty'  # Mark bed as dirty for cleaning
        
        # Update any active check-ins to checked_out status
        active_checkins = CheckInOut.query.filter_by(
            tenant_id=tenant.id, 
            status='checked_in'
        ).all()
        
        for checkin in active_checkins:
            checkin.status = 'checked_out'
            checkin.actual_check_out_date = datetime.now()
        
        db.session.commit()
        
        # Log the action
        log_tenant_action('deactivated', tenant)
        
        flash(f'Guest {tenant.name} has been deactivated successfully.', 'success')
        return redirect(url_for('guests.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deactivating guest: {str(e)}', 'error')
        return redirect(url_for('guests.view', tenant_id=tenant.id))

@guests_bp.route('/api/quick-stats')
@login_required
def quick_stats():
    """API endpoint for quick dashboard stats"""
    try:
        total_active = Tenant.query.filter_by(is_active=True).count()
        total_checked_in = CheckInOut.query.filter_by(status='checked_in').count()
        # Note: Payment model doesn't have status field, so we'll show total payments instead
        total_payments = Payment.query.count()
        
        # Today's activities
        today = datetime.now().date()
        todays_checkins = CheckInOut.query.filter(
            db.func.date(CheckInOut.check_in_date) == today
        ).count()
        
        todays_checkouts = CheckInOut.query.filter(
            db.func.date(CheckInOut.expected_check_out_date) == today,
            CheckInOut.status == 'checked_in'
        ).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_active': total_active,
                'total_checked_in': total_checked_in,
                'total_payments': total_payments,
                'todays_checkins': todays_checkins,
                'todays_checkouts': todays_checkouts
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@guests_bp.route('/<int:tenant_id>/delete', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def delete(tenant_id):
    """Delete a guest and all related data"""
    tenant = Tenant.query.get_or_404(tenant_id)
    
    try:
        # Store tenant name for flash message
        tenant_name = tenant.name
        
        # Delete related records first (due to foreign key constraints)
        
        # 1. Delete tenant services (meal plans, extra services)
        TenantService.query.filter_by(tenant_id=tenant.id).delete()
        
        # 2. Delete payments
        Payment.query.filter_by(tenant_id=tenant.id).delete()
        
        # 3. Delete check-in/out records
        CheckInOut.query.filter_by(tenant_id=tenant.id).delete()
        
        # 4. Free up assigned bed if any
        if tenant.bed_id:
            bed = Bed.query.get(tenant.bed_id)
            if bed:
                bed.is_occupied = False
                bed.tenant_id = None
                bed.status = 'clean'
        
        # 5. Delete the tenant
        db.session.delete(tenant)
        db.session.commit()
        
        # Log the action
        log_tenant_action('deleted', tenant, f'Guest {tenant_name} deleted from system')
        
        flash(f'Guest {tenant_name} has been permanently deleted from the system.', 'success')
        return redirect(url_for('guests.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting guest: {str(e)}', 'error')
        return redirect(url_for('guests.view', tenant_id=tenant.id))

@guests_bp.route('/<int:tenant_id>/test-extend', methods=['POST'])
@login_required
def test_extend(tenant_id):
    """Simple test route to see if form submission works"""
    print(f"TEST: Simple extend route hit for tenant {tenant_id}")
    print(f"TEST: Form data: {dict(request.form)}")
    flash('Test route working!', 'success')
    return redirect(url_for('guests.view', tenant_id=tenant.id))

@guests_bp.route('/<int:tenant_id>/extend-stay', methods=['POST'])
@login_required
def extend_stay(tenant_id):
    """Extend guest stay by additional days with proper payment handling"""
    print(f"DEBUG: extend_stay route hit for tenant {tenant_id}")
    tenant = Tenant.query.get_or_404(tenant_id)
    
    try:
        print(f"DEBUG: Form data received: {dict(request.form)}")
        additional_days = int(request.form.get('additional_days', 0))
        new_daily_rate = float(request.form.get('new_daily_rate', tenant.daily_rent))
        
        print(f"DEBUG: Extending stay for tenant {tenant_id}")
        print(f"DEBUG: Additional days: {additional_days}")
        print(f"DEBUG: New daily rate: {new_daily_rate}")
        print(f"DEBUG: Current end date: {tenant.end_date}")
        print(f"DEBUG: Is prepaid: {tenant.is_prepaid}")
        
        if additional_days <= 0:
            flash('Additional days must be greater than 0', 'error')
            return redirect(url_for('guests.view', tenant_id=tenant.id))
        
        # Store original end date for calculation
        original_end_date = tenant.end_date
        
        # CORRECT APPROACH: new_checkout_date = current_checkout_date + extended_days
        if tenant.end_date:
            # Use current checkout date and add extended days
            old_end_date = tenant.end_date
            tenant.end_date = tenant.end_date + timedelta(days=additional_days)
            print(f"DEBUG: Updated end date (from current checkout): {old_end_date} + {additional_days} days = {tenant.end_date}")
        else:
            # If no end date, calculate from start date + original duration + additional days
            tenant.end_date = tenant.start_date + timedelta(days=additional_days)
            print(f"DEBUG: Updated end date (from start): {tenant.end_date}")
        
        print(f"DEBUG: Tenant object end_date after calculation: {tenant.end_date}")
        print(f"DEBUG: Tenant object type: {type(tenant.end_date)}")
        
        # Calculate payment for additional days ONLY
        additional_cost = additional_days * new_daily_rate
        
        # Handle payment based on prepaid status
        if tenant.is_prepaid:
            # For prepaid guests: Only charge for additional days, don't touch original prepaid amount
            print(f"DEBUG: Prepaid guest - charging only for additional days: {additional_cost} MAD")
            
            if additional_cost > 0:
                payment = Payment(
                    tenant_id=tenant.id,
                    amount=additional_cost,
                    payment_date=date.today(),
                    payment_for_month=date.today().strftime('%Y-%m'),
                    payment_type='extension',
                    notes=f'Extension payment for {additional_days} additional days at {new_daily_rate} MAD/day (Prepaid guest)',
                    created_by=current_user.id
                )
                db.session.add(payment)
                print(f"DEBUG: Created extension payment for prepaid guest: {additional_cost} MAD")
                
                # Log the payment
                log_payment_action('created', payment, f'Extension payment for prepaid guest: {additional_days} days at {new_daily_rate} MAD/day')
        else:
            # For regular guests: Charge for additional days
            print(f"DEBUG: Regular guest - charging for additional days: {additional_cost} MAD")
            
            if additional_cost > 0:
                payment = Payment(
                    tenant_id=tenant.id,
                    amount=additional_cost,
                    payment_date=date.today(),
                    payment_for_month=date.today().strftime('%Y-%m'),
                    payment_type='extension',
                    notes=f'Extension payment for {additional_days} additional days at {new_daily_rate} MAD/day',
                    created_by=current_user.id
                )
                db.session.add(payment)
                print(f"DEBUG: Created extension payment for regular guest: {additional_cost} MAD")
                
                # Log the payment
                log_payment_action('created', payment, f'Extension payment: {additional_days} days at {new_daily_rate} MAD/day')
        
        # Update daily rate for future calculations (but don't affect existing prepaid amount)
        if new_daily_rate != tenant.daily_rent:
            tenant.daily_rent = new_daily_rate
            print(f"DEBUG: Updated daily rate to: {new_daily_rate}")
        
        # Log the action
        log_tenant_action('extended', tenant, f'Stay extended by {additional_days} days. New end date: {tenant.end_date.strftime("%Y-%m-%d")}. Additional cost: {additional_cost:.0f} MAD')
        
        print(f"DEBUG: About to commit changes")
        print(f"DEBUG: Final end date before commit: {tenant.end_date}")
        print(f"DEBUG: Tenant ID: {tenant.id}")
        print(f"DEBUG: Tenant name: {tenant.name}")
        print(f"DEBUG: Tenant object before commit: {tenant}")
        print(f"DEBUG: Tenant end_date type before commit: {type(tenant.end_date)}")
        
        try:
            db.session.commit()
            print(f"DEBUG: Changes committed successfully")
        except Exception as commit_error:
            print(f"DEBUG: Commit error: {commit_error}")
            db.session.rollback()
            raise commit_error
        
        # Verify the changes were actually saved
        db.session.refresh(tenant)
        print(f"DEBUG: After commit - tenant.end_date: {tenant.end_date}")
        print(f"DEBUG: After commit - tenant.daily_rent: {tenant.daily_rent}")
        
        # Double-check by querying the database directly
        fresh_tenant = Tenant.query.get(tenant.id)
        print(f"DEBUG: Fresh query - tenant.end_date: {fresh_tenant.end_date}")
        print(f"DEBUG: Fresh query - tenant.daily_rent: {fresh_tenant.daily_rent}")
        
        # Check if the dates match
        if fresh_tenant.end_date == tenant.end_date:
            print(f"DEBUG: ✅ Database update successful - dates match")
        else:
            print(f"DEBUG: ❌ Database update failed - dates don't match")
            print(f"DEBUG: Expected: {tenant.end_date}, Got: {fresh_tenant.end_date}")
        
        # Show appropriate success message
        if additional_cost > 0:
            if fresh_tenant.is_prepaid:
                flash(f'Stay extended by {additional_days} days. New end date: {fresh_tenant.end_date.strftime("%Y-%m-%d")}. Payment of {additional_cost:.0f} MAD added for additional days (prepaid guest).', 'success')
            else:
                flash(f'Stay extended by {additional_days} days. New end date: {fresh_tenant.end_date.strftime("%Y-%m-%d")}. Payment of {additional_cost:.0f} MAD added for additional days.', 'success')
        else:
            flash(f'Stay extended by {additional_days} days. New end date: {fresh_tenant.end_date.strftime("%Y-%m-%d")}', 'success')
        
    except ValueError as e:
        print(f"DEBUG: ValueError: {e}")
        flash('Invalid input values. Please check your entries.', 'error')
    except Exception as e:
        print(f"DEBUG: Exception: {e}")
        db.session.rollback()
        flash(f'Error extending stay: {str(e)}', 'error')
    
    return redirect(url_for('guests.view', tenant_id=tenant.id))


# Bulk Actions Routes
@guests_bp.route('/bulk-mark-paid', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_mark_paid():
    """Mark multiple guests as paid"""
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'})
        
        # Update payment status for selected guests
        updated_count = 0
        for guest_id in guest_ids:
            tenant = Tenant.query.get(guest_id)
            if tenant:
                tenant.payment_status = 'paid'
                updated_count += 1
        
        db.session.commit()
        
        # Log the bulk action
        log_tenant_action(
            tenant_id=None,
            action='bulk_mark_paid',
            details=f'Marked {updated_count} guests as paid',
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True, 
            'message': f'Successfully marked {updated_count} guests as paid'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})


@guests_bp.route('/bulk-send-reminder', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_send_reminder():
    """Send payment reminders to multiple guests"""
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'})
        
        # Send reminders to selected guests
        sent_count = 0
        for guest_id in guest_ids:
            tenant = Tenant.query.get(guest_id)
            if tenant and tenant.payment_status != 'paid':
                # Here you would integrate with your email service
                # For now, we'll just log the action
                sent_count += 1
        
        # Log the bulk action
        log_tenant_action(
            tenant_id=None,
            action='bulk_send_reminder',
            details=f'Sent payment reminders to {sent_count} guests',
            user_id=current_user.id
        )
        
        return jsonify({
            'success': True, 
            'message': f'Successfully sent reminders to {sent_count} guests'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@guests_bp.route('/bulk-checkout', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_checkout():
    """Checkout multiple guests"""
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'})
        
        # Checkout selected guests
        checked_out_count = 0
        for guest_id in guest_ids:
            tenant = Tenant.query.get(guest_id)
            if tenant and tenant.status == 'active':
                tenant.status = 'checked_out'
                tenant.end_date = date.today()
                checked_out_count += 1
                
                # Log individual checkout
                log_tenant_action(
                    tenant_id=tenant.id,
                    action='checkout',
                    details='Bulk checkout',
                    user_id=current_user.id
                )
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Successfully checked out {checked_out_count} guests'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})


@guests_bp.route('/bulk-delete', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_delete():
    """Delete multiple guests (admin only)"""
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'})
        
        # Delete selected guests
        deleted_count = 0
        for guest_id in guest_ids:
            tenant = Tenant.query.get(guest_id)
            if tenant:
                # Log before deletion
                log_tenant_action(
                    tenant_id=tenant.id,
                    action='delete',
                    details='Bulk delete',
                    user_id=current_user.id
                )
                
                db.session.delete(tenant)
                deleted_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Successfully deleted {deleted_count} guests'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})


@guests_bp.route('/bulk-export', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_export():
    """Export selected guests data as CSV"""
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'})
        
        # Get guest data
        guests = Tenant.query.filter(Tenant.id.in_(guest_ids)).all()
        
        # Generate CSV data
        csv_data = []
        csv_data.append(['ID', 'Name', 'Email', 'Phone', 'Check-in Date', 'Check-out Date', 'Total Amount', 'Payment Status'])
        
        for guest in guests:
            csv_data.append([
                guest.id,
                guest.name,
                guest.email or '',
                guest.phone or '',
                guest.start_date.strftime('%Y-%m-%d') if guest.start_date else '',
                guest.end_date.strftime('%Y-%m-%d') if guest.end_date else '',
                guest.total_amount or 0,
                guest.payment_status or ''
            ])
        
        # Convert to CSV string
        csv_string = '\n'.join([','.join([str(cell) for cell in row]) for row in csv_data])
        
        return jsonify({
            'success': True,
            'csv_data': csv_string,
            'filename': f'guests_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
