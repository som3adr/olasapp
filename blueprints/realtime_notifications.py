from flask import Blueprint, Response, request, jsonify
from flask_login import login_required, current_user
from notification_service import NotificationService
import json
import time
from threading import Lock
from collections import defaultdict

realtime_bp = Blueprint('realtime_notifications', __name__, url_prefix='/api/realtime')

# Store active connections
active_connections = defaultdict(list)
connection_lock = Lock()

@realtime_bp.route('/notifications/stream')
@login_required
def notification_stream():
    """Server-Sent Events stream for real-time notifications"""
    
    def event_stream():
        # Add this connection to the active connections
        with connection_lock:
            active_connections[current_user.id].append({
                'timestamp': time.time(),
                'last_notification_id': 0
            })
        
        try:
            last_notification_id = 0
            
            while True:
                # Check for new notifications
                notifications = NotificationService.get_notifications_for_user_enhanced(
                    user_id=current_user.id,
                    limit=10,
                    offset=0,
                    unread_only=True
                )
                
                # Send new notifications
                for notification in notifications['notifications']:
                    if notification.id > last_notification_id:
                        event_data = {
                            'type': 'notification',
                            'data': {
                                'id': notification.id,
                                'title': notification.title,
                                'message': notification.message,
                                'notification_type': notification.notification_type,
                                'priority': notification.priority,
                                'created_at': notification.created_at.isoformat()
                            }
                        }
                        
                        yield f"data: {json.dumps(event_data)}\n\n"
                        last_notification_id = notification.id
                
                # Send heartbeat every 30 seconds
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
                
                time.sleep(5)  # Check every 5 seconds
                
        except GeneratorExit:
            # Clean up connection when client disconnects
            with connection_lock:
                if current_user.id in active_connections:
                    # Remove this connection
                    active_connections[current_user.id] = [
                        conn for conn in active_connections[current_user.id]
                        if conn.get('timestamp', 0) != time.time()
                    ]
                    if not active_connections[current_user.id]:
                        del active_connections[current_user.id]
        except Exception as e:
            print(f"Error in notification stream: {e}")
    
    return Response(event_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Cache-Control'
    })

@realtime_bp.route('/notifications/push', methods=['POST'])
@login_required
def push_notification():
    """Push a notification to all connected clients"""
    try:
        data = request.get_json()
        
        # Create the notification
        notification = NotificationService.create_notification(
            title=data.get('title', 'New Notification'),
            message=data.get('message', ''),
            notification_type=data.get('type', 'system'),
            target_role=data.get('target_role', 'all'),
            priority=data.get('priority', 'normal'),
            data=data.get('data', {})
        )
        
        if notification:
            # Send to all active connections for the target role
            target_role = data.get('target_role', 'all')
            if target_role == 'all':
                # Send to all users
                with connection_lock:
                    for user_id, connections in active_connections.items():
                        for connection in connections:
                            # In a real implementation, you would send this via WebSocket
                            # For now, we'll just log it
                            print(f"Would send notification to user {user_id}")
            else:
                # Send to specific role
                # This would require looking up users by role
                pass
            
            return jsonify({
                'success': True,
                'message': 'Notification pushed successfully',
                'notification_id': notification.id
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to create notification'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@realtime_bp.route('/notifications/test', methods=['POST'])
@login_required
def test_notification():
    """Test endpoint to send a test notification"""
    try:
        # Create a test notification
        notification = NotificationService.create_notification(
            title='Test Notification',
            message='This is a test notification sent at ' + time.strftime('%Y-%m-%d %H:%M:%S'),
            notification_type='system',
            target_role='all',
            priority='normal'
        )
        
        if notification:
            return jsonify({
                'success': True,
                'message': 'Test notification sent successfully',
                'notification_id': notification.id
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send test notification'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@realtime_bp.route('/connections/status')
@login_required
def connection_status():
    """Get status of active connections"""
    try:
        with connection_lock:
            total_connections = sum(len(connections) for connections in active_connections.values())
            user_connections = len(active_connections.get(current_user.id, []))
            
            return jsonify({
                'success': True,
                'total_connections': total_connections,
                'user_connections': user_connections,
                'active_users': len(active_connections)
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
