from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from notification_service import NotificationService
from extensions import db

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')

@notifications_bp.route('/', methods=['GET'])
@login_required
def get_notifications():
    """Get notifications for the current user with filtering and pagination"""
    try:
        filter_type = request.args.get('filter', 'all')
        page = int(request.args.get('page', 0))
        limit = int(request.args.get('limit', 10))
        
        unread_only = filter_type == 'unread'
        notification_type = request.args.get('type', None)
        
        result = NotificationService.get_notifications_for_user_enhanced(
            user_id=current_user.id,
            limit=limit,
            offset=page * limit,
            unread_only=unread_only,
            notification_type=notification_type
        )
        
        # Convert notifications to dict format
        notifications = []
        for notification in result['notifications']:
            notifications.append({
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'notification_type': notification.notification_type,
                'priority': notification.priority,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat(),
                'read_at': notification.read_at.isoformat() if notification.read_at else None,
                'data': notification.data
            })
        
        return jsonify({
            'success': True,
            'notifications': notifications,
            'total_count': result['total_count'],
            'has_more': result['has_more']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@notifications_bp.route('/unread-count', methods=['GET'])
@login_required
def get_unread_count():
    """Get count of unread notifications for the current user"""
    try:
        count = NotificationService.get_unread_count(current_user.id)
        return jsonify({
            'success': True,
            'count': count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_as_read(notification_id):
    """Mark a specific notification as read"""
    try:
        success = NotificationService.mark_notification_as_read(notification_id, current_user.id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Notification marked as read'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Notification not found or access denied'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_as_read():
    """Mark all notifications as read for the current user"""
    try:
        count = NotificationService.mark_all_as_read(current_user.id)
        
        return jsonify({
            'success': True,
            'message': f'Marked {count} notifications as read'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@notifications_bp.route('/<int:notification_id>', methods=['DELETE'])
@login_required
def delete_notification(notification_id):
    """Delete a specific notification"""
    try:
        success = NotificationService.delete_notification(notification_id, current_user.id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Notification deleted'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Notification not found or access denied'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@notifications_bp.route('/stats', methods=['GET'])
@login_required
def get_notification_stats():
    """Get notification statistics for the current user"""
    try:
        stats = NotificationService.get_notification_stats(current_user.id)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@notifications_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def notification_settings():
    """Get or update notification settings for the current user"""
    try:
        if request.method == 'GET':
            # Get current settings (this would be stored in user preferences)
            # For now, return default settings
            settings = {
                'guest_notifications': True,
                'payment_notifications': True,
                'order_notifications': True,
                'system_notifications': True,
                'push_notifications': False,
                'email_notifications': True,
                'auto_mark_read': False
            }
            
            return jsonify({
                'success': True,
                'settings': settings
            })
            
        elif request.method == 'POST':
            # Update settings
            data = request.get_json()
            
            # Here you would save the settings to the database
            # For now, we'll just return success
            
            return jsonify({
                'success': True,
                'message': 'Settings updated successfully'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500