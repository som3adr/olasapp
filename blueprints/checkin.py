from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import CheckInOut, Tenant, Bed, Payment, Stay, Service, TenantService
from permissions import require_frontdesk_or_admin
from audit import log_action
from datetime import datetime, timedelta
import json
from audit import log_tenant_action

checkin_bp = Blueprint('checkin', __name__, url_prefix='/checkin')


@checkin_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    """Check-in/check-out dashboard"""
    # Current check-ins
    current_checkins = CheckInOut.query.filter_by(status='checked_in').order_by(CheckInOut.check_in_date.desc()).all()
    
    # Today's expected check-outs
    today = datetime.now().date()
    todays_checkouts = CheckInOut.query.filter(
        CheckInOut.status == 'checked_in',
        db.func.date(CheckInOut.expected_check_out_date) == today
    ).all()
    
    # Overdue check-outs
    overdue_checkouts = CheckInOut.query.filter(
        CheckInOut.status == 'checked_in',
        CheckInOut.expected_check_out_date < datetime.now()
    ).all()
    
    # Available beds
    available_beds = Bed.query.filter_by(is_occupied=False, status='clean').all()
    
    # Summary stats
    total_occupied = Bed.query.filter_by(is_occupied=True).count()
    total_beds = Bed.query.count()
    occupancy_rate = (total_occupied / total_beds * 100) if total_beds > 0 else 0
    
    return render_template('checkin/index.html',
                         current_checkins=current_checkins,
                         todays_checkouts=todays_checkouts,
                         overdue_checkouts=overdue_checkouts,
                         available_beds=available_beds,
                         occupancy_rate=occupancy_rate,
                         total_occupied=total_occupied,
                         total_beds=total_beds,
                         current_time=datetime.now())


@checkin_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def new_checkin():
    """Create new check-in with option to create new guest"""
    if request.method == 'POST':
        check_in_mode = request.form.get('check_in_mode', 'existing')
        
        if check_in_mode == 'new_guest':
            # Handle new guest creation + check-in
            return handle_new_guest_checkin(request)
        else:
            # Handle existing guest check-in
            return handle_existing_guest_checkin(request)
    
    # Get available beds and active tenants for form
    # Include both available beds and beds currently occupied by active tenants
    available_beds = Bed.query.filter_by(is_occupied=False, status='clean').all()
    
    # Get active tenants
    tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    
    # Also get beds that are currently occupied by active tenants (for existing guest check-ins)
    occupied_beds = []
    for tenant in tenants:
        # Check if tenant has an active check-in (for check-in/check-out workflow)
        active_checkin = CheckInOut.query.filter_by(tenant_id=tenant.id, status='checked_in').first()
        if active_checkin and active_checkin.bed:
            occupied_beds.append(active_checkin.bed)
        
        # Also check if tenant has a bed directly assigned (from tenants system)
        assigned_bed = Bed.query.filter_by(tenant_id=tenant.id, is_occupied=True).first()
        if assigned_bed and assigned_bed not in occupied_beds:
            occupied_beds.append(assigned_bed)
    
    # Combine available and occupied beds, removing duplicates
    all_beds = available_beds + occupied_beds
    # Remove duplicates based on bed ID
    seen_bed_ids = set()
    unique_beds = []
    for bed in all_beds:
        if bed.id not in seen_bed_ids:
            seen_bed_ids.add(bed.id)
            unique_beds.append(bed)
    
    # Get available services for new guests
    services = Service.query.filter_by(is_active=True).order_by(Service.name).all()
    
    return render_template('checkin/new.html', 
                         available_beds=unique_beds, 
                         tenants=tenants,
                         services=services)


def handle_new_guest_checkin(request):
    """Handle check-in for a new guest (create guest + check-in)"""
    # Extract guest creation data
    guest_name = request.form.get('guest_name')
    daily_rent = request.form.get('daily_rent')
    number_of_days = request.form.get('number_of_days')
    bed_id = request.form.get('new_guest_bed_id') or request.form.get('bed_id')
    check_in_date = request.form.get('check_in_date')
    deposit_paid = request.form.get('deposit_paid', 0)
    notes = request.form.get('notes', '')
    
    # Validation
    if not all([guest_name, daily_rent, number_of_days, bed_id, check_in_date]):
        flash('Please fill in all required fields for new guest.', 'error')
        return redirect(url_for('checkin.new_checkin'))
    
    try:
        daily_rent = float(daily_rent)
        number_of_days = int(number_of_days)
        check_in_date = datetime.strptime(check_in_date, '%Y-%m-%dT%H:%M')
        deposit_paid = float(deposit_paid) if deposit_paid else 0.0
    except ValueError:
        flash('Invalid number or date format.', 'error')
        return redirect(url_for('checkin.new_checkin'))
    
    # Check if bed is available
    bed = Bed.query.get(bed_id)
    if not bed or bed.is_occupied:
        flash('Selected bed is not available.', 'error')
        return redirect(url_for('checkin.new_checkin'))
    
    # Calculate end date based on number of days
    from datetime import timedelta
    end_date = check_in_date.date() + timedelta(days=number_of_days - 1)
    expected_check_out_date = datetime.combine(end_date, datetime.min.time())
    expected_check_out_date = expected_check_out_date.replace(hour=11, minute=0)  # 11:00 AM checkout
    
    try:
        # Create new tenant
        tenant = Tenant(
            name=guest_name,
            room_number=bed.room.room_number,
            daily_rent=daily_rent,
            start_date=check_in_date.date(),
            end_date=end_date
        )
        db.session.add(tenant)
        db.session.flush()  # Get tenant ID
        
        # Create Stay record
        stay = Stay(
            tenant_id=tenant.id,
            stay_type='daily',
            daily_rate=daily_rent,
            start_date=check_in_date.date(),
            end_date=end_date,
            is_active=True
        )
        db.session.add(stay)
        
        # Create check-in record
        checkin = CheckInOut(
            tenant_id=tenant.id,
            bed_id=bed_id,
            check_in_date=check_in_date,
            expected_check_out_date=expected_check_out_date,
            deposit_paid=deposit_paid,
            notes=notes,
            checked_in_by=current_user.id
        )
        db.session.add(checkin)
        
        # Mark bed as occupied and assign tenant
        bed.is_occupied = True
        bed.tenant_id = tenant.id
        
        # Create initial payment record for deposit if any
        if deposit_paid > 0:
            payment = Payment(
                tenant_id=tenant.id,
                amount=deposit_paid,
                payment_type='deposit',
                payment_date=check_in_date.date(),
                notes=f'Deposit paid during check-in'
            )
            db.session.add(payment)
        
        # Handle extra services assignments
        selected_ids = request.form.getlist('service_ids')
        if selected_ids:
            services = Service.query.filter(Service.id.in_(selected_ids)).all()
            for svc in services:
                qty_raw = request.form.get(f'service_qty_{svc.id}', '1')
                price_raw = request.form.get(f'service_price_{svc.id}', '')
                custom_name = request.form.get(f'service_custom_name_{svc.id}', '').strip()
                try:
                    qty = max(1, int(qty_raw))
                except ValueError:
                    qty = 1
                try:
                    unit_price = float(price_raw) if price_raw != '' else svc.price
                except ValueError:
                    unit_price = svc.price
                assignment = TenantService(
                    tenant_id=tenant.id,
                    service_id=svc.id,
                    quantity=qty,
                    unit_price=unit_price,
                    custom_name=custom_name if custom_name else None,
                    start_date=check_in_date.date()
                )
                db.session.add(assignment)
                
                # Create notification for kitchen staff if it's a food service
                print(f"🍽️ DEBUG: Checking service for notification during checkin - service_type: {svc.service_type}, service_name: {svc.name}")
                is_food_service = (svc.service_type in ['restaurant', 'meal'] or 
                                 'food' in svc.name.lower() or 
                                 'meal' in svc.name.lower())
                print(f"🍽️ DEBUG: Is food service: {is_food_service}")
                
                if is_food_service:
                    print(f"🍽️ DEBUG: Creating notification for food order during checkin - Service: {svc.name}, Guest: {tenant.name}")
                    from notification_service import NotificationService
                    notification = NotificationService.notify_all_users(
                        title="New Food Order",
                        message=f"New order: {svc.name} x{qty} for guest {tenant.name}. Total: {unit_price * qty:.2f} MAD",
                        notification_type='food_order',
                        related_entity_type='tenant_service',
                        related_entity_id=assignment.id,
                        priority='high',
                        data={
                            'guest_name': tenant.name,
                            'service_name': svc.name,
                            'quantity': qty,
                            'unit_price': unit_price,
                            'total_price': unit_price * qty,
                            'notes': custom_name,
                            'order_date': check_in_date.date().isoformat()
                        }
                    )
                    if notification:
                        print(f"✅ DEBUG: Food order notification created successfully with ID: {notification.id}")
                    else:
                        print("❌ DEBUG: Failed to create food order notification")
                else:
                    print("🍽️ DEBUG: Service is not a food service, skipping notification")
        
        db.session.commit()
        
        # Send notification to all users about guest check-in
        from notification_service import NotificationService
        NotificationService.notify_all_users(
            title="New Guest Check-in",
            message=f"Guest {guest_name} has checked in to bed {bed.bed_number} in room {bed.room.room_number} for {number_of_days} days",
            notification_type='guest_checkin',
            related_entity_type='tenant',
            related_entity_id=tenant.id,
            priority='normal',
            data={
                'guest_name': guest_name,
                'bed_number': bed.bed_number,
                'room_number': bed.room.room_number,
                'check_in_date': check_in_date.strftime('%Y-%m-%d %H:%M'),
                'expected_checkout': expected_check_out_date.strftime('%Y-%m-%d %H:%M'),
                'daily_rent': daily_rent,
                'number_of_days': number_of_days,
                'deposit_paid': deposit_paid,
                'checked_in_by': current_user.username
            }
        )
        
        # Log the actions
        from audit import log_tenant_action
        log_tenant_action('guest_added', tenant)
        log_action('guest_checked_in', 'check_in_out', checkin.id, 
                  new_values={'tenant_id': tenant.id, 'bed_id': bed_id, 'check_in_date': check_in_date.isoformat()})
        
        flash(f'New guest {guest_name} created and checked in successfully to Bed {bed.bed_number} in Room {bed.room.room_number}.', 'success')
        return redirect(url_for('checkin.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to create guest and process check-in: {str(e)}', 'error')
        return redirect(url_for('checkin.new_checkin'))


def handle_existing_guest_checkin(request):
    """Handle check-in for an existing guest"""
    tenant_id = request.form.get('tenant_id')
    bed_id = request.form.get('bed_id')
    check_in_date = request.form.get('check_in_date')
    expected_check_out_date = request.form.get('expected_check_out_date')
    deposit_paid = request.form.get('deposit_paid', 0)
    notes = request.form.get('notes', '')
    
    # Validation
    if not all([tenant_id, bed_id, check_in_date, expected_check_out_date]):
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('checkin.new_checkin'))
    
    try:
        check_in_date = datetime.strptime(check_in_date, '%Y-%m-%dT%H:%M')
        expected_check_out_date = datetime.strptime(expected_check_out_date, '%Y-%m-%dT%H:%M')
        deposit_paid = float(deposit_paid) if deposit_paid else 0.0
    except ValueError:
        flash('Invalid date or deposit amount.', 'error')
        return redirect(url_for('checkin.new_checkin'))
    
    # Check if bed is available
    bed = Bed.query.get(bed_id)
    if not bed or bed.is_occupied:
        flash('Selected bed is not available.', 'error')
        return redirect(url_for('checkin.new_checkin'))
    
    # Check if tenant already has an active check-in
    existing_checkin = CheckInOut.query.filter_by(tenant_id=tenant_id, status='checked_in').first()
    if existing_checkin:
        flash('Guest already has an active check-in.', 'error')
        return redirect(url_for('checkin.new_checkin'))
    
    # Create check-in record
    checkin = CheckInOut(
        tenant_id=tenant_id,
        bed_id=bed_id,
        check_in_date=check_in_date,
        expected_check_out_date=expected_check_out_date,
        deposit_paid=deposit_paid,
        notes=notes,
        checked_in_by=current_user.id
    )
    
    # Update bed status
    bed.is_occupied = True
    bed.tenant_id = tenant_id
    
    # Update tenant status
    tenant = Tenant.query.get(tenant_id)
    tenant.is_active = True
    
    try:
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
                'check_in_date': check_in_date.strftime('%Y-%m-%d %H:%M'),
                'expected_checkout': expected_check_out_date.strftime('%Y-%m-%d %H:%M'),
                'deposit_paid': deposit_paid,
                'checked_in_by': current_user.username
            }
        )
        
        # Log the action
        log_action('guest_checked_in', 'check_in_out', checkin.id, 
                  new_values={'tenant_id': tenant_id, 'bed_id': bed_id, 'check_in_date': check_in_date.isoformat()})
        
        flash(f'Guest {tenant.name} checked in successfully to Bed {bed.bed_number} in Room {bed.room.room_number}.', 'success')
        return redirect(url_for('checkin.index'))
        
    except Exception as e:
        db.session.rollback()
        flash('Failed to process check-in.', 'error')
        return redirect(url_for('checkin.new_checkin'))


@checkin_bp.route('/api/guest-current-room/<int:tenant_id>')
@login_required
@require_frontdesk_or_admin
def get_guest_current_room(tenant_id):
    """Get the current room assignment for a guest"""
    try:
        # First check if guest has an active check-in (for check-in/check-out workflow)
        active_checkin = CheckInOut.query.filter_by(tenant_id=tenant_id, status='checked_in').first()
        
        if active_checkin and active_checkin.bed:
            bed = active_checkin.bed
            room = bed.room
            
            return jsonify({
                'success': True,
                'current_room': {
                    'room_number': room.room_number,
                    'bed_number': bed.bed_number,
                    'bed_id': bed.id
                }
            })
        else:
            # Check if guest has a bed directly assigned (from tenants system)
            assigned_bed = Bed.query.filter_by(tenant_id=tenant_id, is_occupied=True).first()
            
            if assigned_bed:
                room = assigned_bed.room
                
                return jsonify({
                    'success': True,
                    'current_room': {
                        'room_number': room.room_number,
                        'bed_number': assigned_bed.bed_number,
                        'bed_id': assigned_bed.id
                    }
                })
            else:
                # No bed assignment found
                return jsonify({
                    'success': True,
                    'current_room': None
                })
                
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@checkin_bp.route('/checkout/<int:checkin_id>', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def checkout(checkin_id):
    """Process check-out"""
    checkin = CheckInOut.query.get_or_404(checkin_id)
    
    if checkin.status != 'checked_in':
        flash('This guest is not currently checked in.', 'error')
        return redirect(url_for('checkin.index'))
    
    if request.method == 'POST':
        actual_check_out_date = request.form.get('actual_check_out_date')
        deposit_returned = request.form.get('deposit_returned', 0)
        checkout_notes = request.form.get('checkout_notes', '')
        
        try:
            actual_check_out_date = datetime.strptime(actual_check_out_date, '%Y-%m-%dT%H:%M')
            deposit_returned = float(deposit_returned) if deposit_returned else 0.0
        except ValueError:
            flash('Invalid check-out date or deposit amount.', 'error')
            return render_template('checkin/checkout.html', checkin=checkin)
        
        # Update check-in record
        checkin.status = 'checked_out'
        checkin.actual_check_out_date = actual_check_out_date
        checkin.deposit_returned = deposit_returned
        checkin.checked_out_by = current_user.id
        if checkout_notes:
            checkin.notes = (checkin.notes or '') + f'\nCheck-out notes: {checkout_notes}'
        
        # Update bed status
        if checkin.bed:
            checkin.bed.is_occupied = False
            checkin.bed.tenant_id = None
            checkin.bed.status = 'dirty'  # Needs cleaning after checkout
        
        # Check if tenant has other active check-ins
        other_checkins = CheckInOut.query.filter_by(tenant_id=checkin.tenant_id, status='checked_in').count()
        if other_checkins == 0:
            checkin.tenant.is_active = False
        
        try:
            db.session.commit()
            
            # Send notification to all users about guest check-out
            from notification_service import NotificationService
            NotificationService.notify_all_users(
                title="Guest Check-out",
                message=f"Guest {checkin.tenant.name} has checked out from bed {checkin.bed.bed_number if checkin.bed else 'N/A'}",
                notification_type='guest_checkout',
                related_entity_type='tenant',
                related_entity_id=checkin.tenant_id,
                priority='normal',
                data={
                    'guest_name': checkin.tenant.name,
                    'bed_number': checkin.bed.bed_number if checkin.bed else 'N/A',
                    'room_number': checkin.bed.room.room_number if checkin.bed else 'N/A',
                    'check_out_date': actual_check_out_date.strftime('%Y-%m-%d %H:%M'),
                    'deposit_returned': deposit_returned,
                    'checked_out_by': current_user.username
                }
            )
            
            # Log the action
            log_action('guest_checked_out', 'check_in_out', checkin.id,
                      new_values={'actual_check_out_date': actual_check_out_date.isoformat(), 
                                'deposit_returned': deposit_returned})
            
            flash(f'Guest {checkin.tenant.name} checked out successfully.', 'success')
            return redirect(url_for('checkin.index'))
            
        except Exception as e:
            db.session.rollback()
            flash('Failed to process check-out.', 'error')
    
    return render_template('checkin/checkout.html', checkin=checkin)


@checkin_bp.route('/extend/<int:checkin_id>', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def extend_stay(checkin_id):
    """Extend guest's stay"""
    checkin = CheckInOut.query.get_or_404(checkin_id)
    
    if checkin.status != 'checked_in':
        flash('This guest is not currently checked in.', 'error')
        return redirect(url_for('checkin.index'))
    
    new_checkout_date = request.form.get('new_checkout_date')
    extension_notes = request.form.get('extension_notes', '')
    
    try:
        new_checkout_date = datetime.strptime(new_checkout_date, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Invalid date format.', 'error')
        return redirect(url_for('checkin.index'))
    
    old_date = checkin.expected_check_out_date
    checkin.expected_check_out_date = new_checkout_date
    checkin.status = 'extended'
    
    if extension_notes:
        checkin.notes = (checkin.notes or '') + f'\nExtension: {extension_notes}'
    
    try:
        db.session.commit()
        
        # Log the action
        log_action('stay_extended', 'check_in_out', checkin.id,
                  old_values={'expected_check_out_date': old_date.isoformat()},
                  new_values={'expected_check_out_date': new_checkout_date.isoformat()})
        
        flash(f'Stay extended until {new_checkout_date.strftime("%Y-%m-%d %H:%M")}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to extend stay.', 'error')
    
    return redirect(url_for('checkin.index'))


@checkin_bp.route('/history')
@login_required
@require_frontdesk_or_admin
def history():
    """Check-in/check-out history"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    tenant_filter = request.args.get('tenant_id', '')
    
    query = CheckInOut.query
    
    if status_filter:
        query = query.filter(CheckInOut.status == status_filter)
    
    if tenant_filter:
        query = query.filter(CheckInOut.tenant_id == int(tenant_filter))
    
    checkins = query.order_by(CheckInOut.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    tenants = Tenant.query.order_by(Tenant.name).all()
    
    return render_template('checkin/history.html',
                         checkins=checkins,
                         tenants=tenants,
                         status_filter=status_filter,
                         tenant_filter=tenant_filter)
