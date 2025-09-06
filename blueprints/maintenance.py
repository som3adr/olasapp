from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Bed, MaintenanceRequest, User
from permissions import require_frontdesk_or_admin
from audit import log_action
from datetime import datetime, timedelta
import json

maintenance_bp = Blueprint('maintenance', __name__, url_prefix='/maintenance')


@maintenance_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    """Maintenance dashboard"""
    # Filter by status
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    
    query = MaintenanceRequest.query
    
    if status_filter:
        query = query.filter(MaintenanceRequest.status == status_filter)
    
    if priority_filter:
        query = query.filter(MaintenanceRequest.priority == priority_filter)
    
    requests = query.order_by(
        MaintenanceRequest.priority.desc(),
        MaintenanceRequest.created_at.desc()
    ).all()
    
    # Summary statistics
    open_requests = MaintenanceRequest.query.filter_by(status='open').count()
    in_progress_requests = MaintenanceRequest.query.filter_by(status='in_progress').count()
    urgent_requests = MaintenanceRequest.query.filter_by(priority='urgent', status='open').count()
    
    return render_template('maintenance/index.html',
                         requests=requests,
                         open_requests=open_requests,
                         in_progress_requests=in_progress_requests,
                         urgent_requests=urgent_requests,
                         status_filter=status_filter,
                         priority_filter=priority_filter)


@maintenance_bp.route('/add', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def add():
    """Add new maintenance request"""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        priority = request.form.get('priority', 'normal')

        bed_id = request.form.get('bed_id')
        assigned_to = request.form.get('assigned_to')
        estimated_cost = request.form.get('estimated_cost')
        
        if not all([title, description]):
            flash('Title and description are required.', 'error')
            return render_template('maintenance/form.html')
        
        try:
            estimated_cost = float(estimated_cost) if estimated_cost else None
        except ValueError:
            estimated_cost = None
        
        maintenance_request = MaintenanceRequest(
            title=title,
            description=description,
            priority=priority,

            bed_id=int(bed_id) if bed_id else None,
            assigned_to=int(assigned_to) if assigned_to else None,
            estimated_cost=estimated_cost,
            reported_by=current_user.id
        )
        
        try:
            db.session.add(maintenance_request)
            db.session.commit()
            
            # Log the action
            log_action('maintenance_request_created', 'maintenance_request', maintenance_request.id,
                      new_values={'title': title, 'priority': priority})
            
            flash('Maintenance request created successfully.', 'success')
            return redirect(url_for('maintenance.index'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to create maintenance request.', 'error')
    
    # Get staff for form
    # Get users with maintenance or admin roles
    maintenance_staff = []
    for user in User.query.all():
        if user.is_admin or any(role.name == 'Maintenance' for role in user.roles):
            maintenance_staff.append(user)
    
    return render_template('maintenance/form.html', 
 
                         maintenance_staff=maintenance_staff)


@maintenance_bp.route('/<int:request_id>/update', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def update(request_id):
    """Update maintenance request status"""
    maintenance_request = MaintenanceRequest.query.get_or_404(request_id)
    
    new_status = request.form.get('status')
    actual_cost = request.form.get('actual_cost')
    notes = request.form.get('notes')
    
    if new_status not in ['open', 'in_progress', 'completed', 'cancelled']:
        flash('Invalid status.', 'error')
        return redirect(url_for('maintenance.index'))
    
    old_status = maintenance_request.status
    maintenance_request.status = new_status
    
    if new_status == 'completed':
        maintenance_request.completed_at = datetime.utcnow()
    
    if actual_cost:
        try:
            maintenance_request.actual_cost = float(actual_cost)
        except ValueError:
            pass
    
    try:
        db.session.commit()
        
        # Log the action
        log_action('maintenance_request_updated', 'maintenance_request', maintenance_request.id,
                  old_values={'status': old_status},
                  new_values={'status': new_status, 'actual_cost': actual_cost})
        
        flash('Maintenance request updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update maintenance request.', 'error')
    
    return redirect(url_for('maintenance.index'))


@maintenance_bp.route('/<int:request_id>/assign', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def assign(request_id):
    """Assign maintenance request to staff member"""
    maintenance_request = MaintenanceRequest.query.get_or_404(request_id)
    
    assigned_to = request.form.get('assigned_to')
    
    if assigned_to:
        old_assigned = maintenance_request.assigned_to
        maintenance_request.assigned_to = int(assigned_to)
        
        # Auto-set status to in_progress if it was open
        if maintenance_request.status == 'open':
            maintenance_request.status = 'in_progress'
        
        try:
            db.session.commit()
            
            # Log the action
            log_action('maintenance_request_assigned', 'maintenance_request', maintenance_request.id,
                      old_values={'assigned_to': old_assigned},
                      new_values={'assigned_to': assigned_to})
            
            flash('Maintenance request assigned successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Failed to assign maintenance request.', 'error')
    
    return redirect(url_for('maintenance.index'))


@maintenance_bp.route('/api/beds')
@login_required
@require_frontdesk_or_admin
def get_beds():
    """Get all beds (API endpoint)"""
    beds = Bed.query.all()
    return {
        'beds': [{'id': bed.id, 'number': bed.bed_number} for bed in beds]
    }

