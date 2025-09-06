"""
Example: Consolidated Guests Blueprint using Shared Services

This example shows how the guests blueprint would look after consolidation,
demonstrating the use of shared services and UI components.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Tenant, Payment, Stay
from permissions import require_frontdesk_or_admin
from services import NotificationsService, BulkActionsService, ReportingService, AuditService
from services.bulk_actions_service import BulkActionType
from services.notifications_service import NotificationType, NotificationPriority
from services.audit_service import EventType, EventSeverity
from datetime import datetime, timedelta
import json

# Initialize shared services
notifications_service = NotificationsService()
bulk_actions_service = BulkActionsService()
reporting_service = ReportingService()
audit_service = AuditService()

guests_bp = Blueprint('guests', __name__, url_prefix='/guests')

@guests_bp.route('/')
@login_required
def index():
    """
    Unified guest management dashboard using shared DataTable component
    """
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
    
    # Apply filters
    if search:
        query = query.filter(Tenant.name.ilike(f'%{search}%'))
    
    if status == 'active':
        query = query.filter(Tenant.is_active == True)
    elif status == 'inactive':
        query = query.filter(Tenant.is_active == False)
    
    if hostel:
        query = query.filter(Tenant.hostel_name == hostel)
    
    # Apply date range filter
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Tenant.start_date >= from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Tenant.start_date <= to_date)
        except ValueError:
            pass
    
    # Apply sorting
    if sort == 'check_in':
        query = query.order_by(Tenant.start_date.desc())
    elif sort == 'name':
        query = query.order_by(Tenant.name.asc())
    elif sort == 'payment_status':
        query = query.order_by(Tenant.payment_status.asc())
    
    # Get guests
    guests = query.all()
    
    # Configure DataTable component
    data_table_config = {
        'title': 'Guest Management',
        'subtitle': 'Manage guest check-ins, payments, and services',
        'data': [
            {
                'id': guest.id,
                'name': guest.name,
                'email': guest.email or '',
                'phone': guest.phone or '',
                'start_date': guest.start_date.strftime('%Y-%m-%d') if guest.start_date else '',
                'end_date': guest.end_date.strftime('%Y-%m-%d') if guest.end_date else '',
                'status': 'Active' if guest.is_active else 'Inactive',
                'payment_status': guest.payment_status or 'Pending',
                'hostel': guest.hostel_name or 'General'
            }
            for guest in guests
        ],
        'columns': [
            {'key': 'name', 'label': 'Name', 'type': 'text'},
            {'key': 'email', 'label': 'Email', 'type': 'text'},
            {'key': 'phone', 'label': 'Phone', 'type': 'text'},
            {'key': 'start_date', 'label': 'Check-in', 'type': 'date'},
            {'key': 'end_date', 'label': 'Check-out', 'type': 'date'},
            {'key': 'status', 'label': 'Status', 'type': 'status'},
            {'key': 'payment_status', 'label': 'Payment', 'type': 'status'},
            {'key': 'hostel', 'label': 'Hostel', 'type': 'text'}
        ],
        'itemsPerPage': 25,
        'searchable': True,
        'filterable': True,
        'sortable': True,
        'exportable': True
    }
    
    # Configure BulkToolbar component
    bulk_toolbar_config = {
        'actions': [
            {
                'id': 'mark_paid',
                'label': 'Mark as Paid',
                'icon': 'fas fa-check-circle',
                'handler': lambda: bulk_mark_paid()
            },
            {
                'id': 'send_reminder',
                'label': 'Send Payment Reminder',
                'icon': 'fas fa-bell',
                'handler': lambda: bulk_send_reminder()
            },
            {
                'id': 'checkout',
                'label': 'Bulk Checkout',
                'icon': 'fas fa-sign-out-alt',
                'handler': lambda: bulk_checkout()
            },
            {
                'id': 'export',
                'label': 'Export Selected',
                'icon': 'fas fa-download',
                'handler': lambda: bulk_export()
            },
            {
                'id': 'delete',
                'label': 'Delete Selected',
                'icon': 'fas fa-trash',
                'handler': lambda: bulk_delete(),
                'danger': True
            }
        ]
    }
    
    # Log audit event
    audit_service.log_event(
        event_type=EventType.GUEST_VIEW,
        user_id=current_user.id,
        entity_type='guest_list',
        action='view_guest_list',
        description=f'Viewed guest list with {len(guests)} guests',
        metadata={'filter_status': status, 'search_term': search},
        severity=EventSeverity.LOW
    )
    
    return render_template('guests/index_consolidated.html',
                         data_table_config=data_table_config,
                         bulk_toolbar_config=bulk_toolbar_config,
                         current_filters={
                             'search': search,
                             'status': status,
                             'sort': sort,
                             'payment_status': payment_status,
                             'hostel': hostel,
                             'date_from': date_from,
                             'date_to': date_to
                         })

@guests_bp.route('/api/bulk-mark-paid', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_mark_paid():
    """
    Bulk mark guests as paid using BulkActionsService
    """
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'}), 400
        
        # Execute bulk action
        job_id = bulk_actions_service.execute_bulk_action(
            action_type=BulkActionType.GUEST_MARK_PAID,
            user_id=current_user.id,
            item_ids=guest_ids,
            parameters={'marked_by': current_user.username}
        )
        
        if job_id:
            # Send notification
            notifications_service.send_notification(
                title='Bulk Payment Update',
                message=f'Bulk payment update initiated for {len(guest_ids)} guests',
                notification_type=NotificationType.SYSTEM,
                priority=NotificationPriority.MEDIUM,
                target_users=[current_user.id],
                metadata={'job_id': job_id, 'guest_count': len(guest_ids)}
            )
            
            # Log audit event
            audit_service.log_event(
                event_type=EventType.BULK_ACTION,
                user_id=current_user.id,
                entity_type='guest',
                action='bulk_mark_paid',
                description=f'Bulk marked {len(guest_ids)} guests as paid',
                metadata={'guest_ids': guest_ids, 'job_id': job_id},
                severity=EventSeverity.MEDIUM
            )
            
            return jsonify({
                'success': True,
                'message': f'Bulk payment update initiated for {len(guest_ids)} guests',
                'job_id': job_id
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to initiate bulk action'}), 500
            
    except Exception as e:
        # Log error
        audit_service.log_event(
            event_type=EventType.SYSTEM_EVENT,
            user_id=current_user.id,
            entity_type='error',
            action='bulk_mark_paid_error',
            description=f'Error in bulk mark paid: {str(e)}',
            metadata={'error': str(e), 'guest_ids': data.get('guest_ids', [])},
            severity=EventSeverity.HIGH
        )
        
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/bulk-send-reminder', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_send_reminder():
    """
    Bulk send payment reminders using NotificationsService
    """
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'}), 400
        
        # Get guest details
        guests = Tenant.query.filter(Tenant.id.in_(guest_ids)).all()
        
        # Send notifications to guests
        for guest in guests:
            if guest.email:
                notifications_service.send_notification(
                    title='Payment Reminder',
                    message=f'Dear {guest.name}, this is a reminder about your pending payment.',
                    notification_type=NotificationType.GUEST,
                    priority=NotificationPriority.MEDIUM,
                    target_users=[guest.id],
                    channels=['email'],
                    template_id='payment_reminder',
                    template_variables={
                        'guest_name': guest.name,
                        'amount': guest.daily_rent,
                        'due_date': guest.end_date.strftime('%Y-%m-%d') if guest.end_date else 'N/A'
                    }
                )
        
        # Log audit event
        audit_service.log_event(
            event_type=EventType.NOTIFICATION_SEND,
            user_id=current_user.id,
            entity_type='guest',
            action='bulk_send_reminder',
            description=f'Sent payment reminders to {len(guests)} guests',
            metadata={'guest_ids': guest_ids, 'guest_count': len(guests)},
            severity=EventSeverity.MEDIUM
        )
        
        return jsonify({
            'success': True,
            'message': f'Payment reminders sent to {len(guests)} guests'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/bulk-checkout', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_checkout():
    """
    Bulk checkout guests using BulkActionsService
    """
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'}), 400
        
        # Execute bulk action
        job_id = bulk_actions_service.execute_bulk_action(
            action_type=BulkActionType.GUEST_CHECKOUT,
            user_id=current_user.id,
            item_ids=guest_ids,
            parameters={'checked_out_by': current_user.username}
        )
        
        if job_id:
            # Send notification
            notifications_service.send_notification(
                title='Bulk Checkout',
                message=f'Bulk checkout initiated for {len(guest_ids)} guests',
                notification_type=NotificationType.SYSTEM,
                priority=NotificationPriority.MEDIUM,
                target_users=[current_user.id],
                metadata={'job_id': job_id, 'guest_count': len(guest_ids)}
            )
            
            return jsonify({
                'success': True,
                'message': f'Bulk checkout initiated for {len(guest_ids)} guests',
                'job_id': job_id
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to initiate bulk action'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/bulk-export', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_export():
    """
    Bulk export guests using BulkActionsService
    """
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        export_format = data.get('format', 'csv')
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'}), 400
        
        # Execute bulk action
        job_id = bulk_actions_service.execute_bulk_action(
            action_type=BulkActionType.GUEST_EXPORT,
            user_id=current_user.id,
            item_ids=guest_ids,
            parameters={'format': export_format, 'exported_by': current_user.username}
        )
        
        if job_id:
            return jsonify({
                'success': True,
                'message': f'Export initiated for {len(guest_ids)} guests',
                'job_id': job_id
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to initiate export'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/bulk-delete', methods=['POST'])
@login_required
@require_frontdesk_or_admin
def bulk_delete():
    """
    Bulk delete guests using BulkActionsService
    """
    try:
        data = request.get_json()
        guest_ids = data.get('guest_ids', [])
        
        if not guest_ids:
            return jsonify({'success': False, 'message': 'No guests selected'}), 400
        
        # Execute bulk action
        job_id = bulk_actions_service.execute_bulk_action(
            action_type=BulkActionType.GUEST_DELETE,
            user_id=current_user.id,
            item_ids=guest_ids,
            parameters={'deleted_by': current_user.username}
        )
        
        if job_id:
            # Send notification
            notifications_service.send_notification(
                title='Bulk Delete',
                message=f'Bulk delete initiated for {len(guest_ids)} guests',
                notification_type=NotificationType.SYSTEM,
                priority=NotificationPriority.HIGH,
                target_users=[current_user.id],
                metadata={'job_id': job_id, 'guest_count': len(guest_ids)}
            )
            
            return jsonify({
                'success': True,
                'message': f'Bulk delete initiated for {len(guest_ids)} guests',
                'job_id': job_id
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to initiate bulk action'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/job-status/<job_id>')
@login_required
def get_job_status(job_id):
    """
    Get status of a bulk action job
    """
    try:
        status = bulk_actions_service.get_job_status(job_id)
        
        if status:
            return jsonify({'success': True, 'status': status})
        else:
            return jsonify({'success': False, 'message': 'Job not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/reports')
@login_required
def reports():
    """
    Guest reports using ReportingService
    """
    try:
        # Get report configuration
        report_config = {
            'report_type': 'guest_analytics',
            'widgets': ['guest_occupancy_chart', 'guest_status_metric'],
            'filters': {
                'date_range': request.args.get('date_range', '30_days'),
                'hostel': request.args.get('hostel', ''),
                'status': request.args.get('status', 'all')
            }
        }
        
        # Generate report
        report_data = reporting_service.generate_report(
            report_type=report_config['report_type'],
            user_id=current_user.id,
            filters=report_config['filters'],
            widgets=report_config['widgets']
        )
        
        # Log audit event
        audit_service.log_event(
            event_type=EventType.REPORT_GENERATE,
            user_id=current_user.id,
            entity_type='guest_report',
            action='generate_guest_report',
            description='Generated guest analytics report',
            metadata=report_config,
            severity=EventSeverity.LOW
        )
        
        return render_template('guests/reports_consolidated.html',
                             report_data=report_data,
                             report_config=report_config)
        
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'error')
        return redirect(url_for('guests.index'))

@guests_bp.route('/api/notifications')
@login_required
def get_notifications():
    """
    Get notifications for guest management
    """
    try:
        filter_type = request.args.get('filter', 'all')
        limit = int(request.args.get('limit', 10))
        offset = int(request.args.get('offset', 0))
        
        # Get notifications using NotificationsService
        result = notifications_service.get_notifications_for_user(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            unread_only=(filter_type == 'unread'),
            notification_type='guest'
        )
        
        return jsonify({
            'success': True,
            'notifications': result['notifications'],
            'total_count': result['total_count'],
            'has_more': result['has_more']
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/notifications/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """
    Mark a notification as read
    """
    try:
        success = notifications_service.mark_as_read(notification_id, current_user.id)
        
        if success:
            return jsonify({'success': True, 'message': 'Notification marked as read'})
        else:
            return jsonify({'success': False, 'message': 'Notification not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """
    Mark all notifications as read
    """
    try:
        count = notifications_service.mark_all_as_read(current_user.id)
        
        return jsonify({
            'success': True,
            'message': f'{count} notifications marked as read'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@guests_bp.route('/api/audit-timeline')
@login_required
def get_audit_timeline():
    """
    Get audit timeline for guest management
    """
    try:
        # Get audit timeline using AuditService
        timeline = audit_service.get_activity_timeline(
            user_id=current_user.id,
            entity_type='guest',
            limit=50
        )
        
        return jsonify({
            'success': True,
            'timeline': timeline
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
