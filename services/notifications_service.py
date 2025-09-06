"""
Centralized Notifications Service

Provides unified notification management across all modules including:
- Real-time notifications via SSE/WebSocket
- Email and SMS notifications
- Topic-based subscriptions
- Role-scoped notifications
- Notification preferences and settings
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from flask import current_app
from extensions import db
from models import User, Notification
from sqlalchemy import and_, or_, desc
import json
import asyncio
from collections import defaultdict


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationType(Enum):
    SYSTEM = "system"
    GUEST = "guest"
    PAYMENT = "payment"
    MAINTENANCE = "maintenance"
    INVENTORY = "inventory"
    STAFF = "staff"
    SECURITY = "security"


@dataclass
class NotificationChannel:
    """Represents a notification delivery channel"""
    name: str
    enabled: bool
    config: Dict[str, Any]


@dataclass
class NotificationTemplate:
    """Represents a notification template"""
    id: str
    name: str
    subject: str
    body: str
    channels: List[str]
    variables: List[str]


class NotificationsService:
    """Centralized notification management service"""
    
    def __init__(self):
        self.channels = {
            'sse': NotificationChannel('sse', True, {}),
            'email': NotificationChannel('email', True, {}),
            'sms': NotificationChannel('sms', True, {}),
            'push': NotificationChannel('push', True, {})
        }
        self.templates = self._load_templates()
        self.subscribers = defaultdict(set)  # topic -> set of user_ids
        self.active_connections = {}  # user_id -> connection_info
    
    def _load_templates(self) -> Dict[str, NotificationTemplate]:
        """Load notification templates from database or config"""
        return {
            'guest_checkin': NotificationTemplate(
                id='guest_checkin',
                name='Guest Check-in',
                subject='New Guest Check-in: {guest_name}',
                body='Guest {guest_name} has checked in to bed {bed_number}',
                channels=['sse', 'email', 'push'],
                variables=['guest_name', 'bed_number']
            ),
            'payment_received': NotificationTemplate(
                id='payment_received',
                name='Payment Received',
                subject='Payment Received: {amount} MAD',
                body='Payment of {amount} MAD received from {guest_name}',
                channels=['sse', 'email'],
                variables=['amount', 'guest_name']
            ),
            'low_stock_alert': NotificationTemplate(
                id='low_stock_alert',
                name='Low Stock Alert',
                subject='Low Stock Alert: {item_name}',
                body='Item {item_name} is running low. Current stock: {current_stock}',
                channels=['sse', 'email'],
                variables=['item_name', 'current_stock']
            ),
            'maintenance_request': NotificationTemplate(
                id='maintenance_request',
                name='Maintenance Request',
                subject='New Maintenance Request: {room_number}',
                body='Maintenance request for {room_number}: {description}',
                channels=['sse', 'email'],
                variables=['room_number', 'description']
            )
        }
    
    def send_notification(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.SYSTEM,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        target_users: Optional[List[int]] = None,
        target_roles: Optional[List[str]] = None,
        target_topic: Optional[str] = None,
        channels: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
        template_variables: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send notification to specified targets
        
        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            priority: Notification priority
            target_users: Specific user IDs to notify
            target_roles: Role names to notify
            target_topic: Topic to notify subscribers of
            channels: Delivery channels to use
            data: Additional data payload
            template_id: Template to use for formatting
            template_variables: Variables for template formatting
            
        Returns:
            bool: True if notification was sent successfully
        """
        try:
            # Determine target users
            user_ids = self._get_target_users(target_users, target_roles, target_topic)
            
            if not user_ids:
                current_app.logger.warning("No target users found for notification")
                return False
            
            # Use template if specified
            if template_id and template_id in self.templates:
                template = self.templates[template_id]
                if template_variables:
                    title = template.subject.format(**template_variables)
                    message = template.body.format(**template_variables)
                channels = channels or template.channels
            
            # Default channels
            if not channels:
                channels = ['sse']
            
            # Create notification records
            notifications_created = 0
            for user_id in user_ids:
                notification = Notification(
                    title=title,
                    message=message,
                    notification_type=notification_type.value,
                    priority=priority.value,
                    target_user_id=user_id,
                    target_role=None,  # Will be set based on user's roles
                    is_read=False,
                    data=json.dumps(data) if data else None,
                    created_at=datetime.utcnow()
                )
                
                db.session.add(notification)
                notifications_created += 1
                
                # Send via specified channels
                self._deliver_notification(notification, channels)
            
            db.session.commit()
            
            # Log audit event
            self._log_notification_sent(
                title, message, notification_type, priority, 
                len(user_ids), channels
            )
            
            current_app.logger.info(
                f"Notification sent to {notifications_created} users: {title}"
            )
            return True
            
        except Exception as e:
            current_app.logger.error(f"Error sending notification: {str(e)}")
            db.session.rollback()
            return False
    
    def _get_target_users(
        self, 
        target_users: Optional[List[int]], 
        target_roles: Optional[List[str]], 
        target_topic: Optional[str]
    ) -> List[int]:
        """Get list of user IDs based on targeting criteria"""
        user_ids = set()
        
        # Specific users
        if target_users:
            user_ids.update(target_users)
        
        # Users with specific roles
        if target_roles:
            role_users = db.session.query(User.id).join(
                User.user_roles
            ).join(
                UserRole.role
            ).filter(
                Role.name.in_(target_roles)
            ).all()
            user_ids.update([user.id for user in role_users])
        
        # Topic subscribers
        if target_topic and target_topic in self.subscribers:
            user_ids.update(self.subscribers[target_topic])
        
        # If no specific targeting, notify all users (for system notifications)
        if not target_users and not target_roles and not target_topic:
            all_users = db.session.query(User.id).filter(User.is_active == True).all()
            user_ids.update([user.id for user in all_users])
        
        return list(user_ids)
    
    def _deliver_notification(self, notification: Notification, channels: List[str]):
        """Deliver notification via specified channels"""
        for channel in channels:
            if channel in self.channels and self.channels[channel].enabled:
                try:
                    if channel == 'sse':
                        self._deliver_sse(notification)
                    elif channel == 'email':
                        self._deliver_email(notification)
                    elif channel == 'sms':
                        self._deliver_sms(notification)
                    elif channel == 'push':
                        self._deliver_push(notification)
                except Exception as e:
                    current_app.logger.error(f"Error delivering via {channel}: {str(e)}")
    
    def _deliver_sse(self, notification: Notification):
        """Deliver notification via Server-Sent Events"""
        if notification.target_user_id in self.active_connections:
            connection_info = self.active_connections[notification.target_user_id]
            # Send SSE event to active connection
            # This would be implemented with actual SSE delivery
            pass
    
    def _deliver_email(self, notification: Notification):
        """Deliver notification via email"""
        # Implementation would integrate with email service
        pass
    
    def _deliver_sms(self, notification: Notification):
        """Deliver notification via SMS"""
        # Implementation would integrate with SMS service
        pass
    
    def _deliver_push(self, notification: Notification):
        """Deliver notification via push notification"""
        # Implementation would integrate with push notification service
        pass
    
    def get_notifications_for_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        priority: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get notifications for a specific user with filtering and pagination"""
        try:
            query = Notification.query.filter(
                or_(
                    Notification.target_user_id == user_id,
                    and_(
                        Notification.target_user_id.is_(None),
                        Notification.target_role.in_(
                            db.session.query(Role.name).join(
                                UserRole, UserRole.role_id == Role.id
                            ).filter(UserRole.user_id == user_id)
                        )
                    )
                )
            )
            
            # Apply filters
            if unread_only:
                query = query.filter(Notification.is_read == False)
            
            if notification_type:
                query = query.filter(Notification.notification_type == notification_type)
            
            if priority:
                query = query.filter(Notification.priority == priority)
            
            # Get total count
            total_count = query.count()
            
            # Apply pagination and ordering
            notifications = query.order_by(desc(Notification.created_at)).offset(offset).limit(limit).all()
            
            # Convert to dict format
            notifications_data = []
            for notification in notifications:
                notifications_data.append({
                    'id': notification.id,
                    'title': notification.title,
                    'message': notification.message,
                    'notification_type': notification.notification_type,
                    'priority': notification.priority,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at.isoformat(),
                    'read_at': notification.read_at.isoformat() if notification.read_at else None,
                    'data': json.loads(notification.data) if notification.data else None
                })
            
            return {
                'notifications': notifications_data,
                'total_count': total_count,
                'has_more': offset + len(notifications) < total_count
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting notifications for user {user_id}: {str(e)}")
            return {'notifications': [], 'total_count': 0, 'has_more': False}
    
    def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read for a specific user"""
        try:
            notification = Notification.query.filter(
                Notification.id == notification_id,
                or_(
                    Notification.target_user_id == user_id,
                    and_(
                        Notification.target_user_id.is_(None),
                        Notification.target_role.in_(
                            db.session.query(Role.name).join(
                                UserRole, UserRole.role_id == Role.id
                            ).filter(UserRole.user_id == user_id)
                        )
                    )
                )
            ).first()
            
            if notification:
                notification.is_read = True
                notification.read_at = datetime.utcnow()
                db.session.commit()
                return True
            
            return False
            
        except Exception as e:
            current_app.logger.error(f"Error marking notification as read: {str(e)}")
            db.session.rollback()
            return False
    
    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read for a specific user"""
        try:
            count = Notification.query.filter(
                or_(
                    Notification.target_user_id == user_id,
                    and_(
                        Notification.target_user_id.is_(None),
                        Notification.target_role.in_(
                            db.session.query(Role.name).join(
                                UserRole, UserRole.role_id == Role.id
                            ).filter(UserRole.user_id == user_id)
                        )
                    )
                ),
                Notification.is_read == False
            ).update({
                'is_read': True,
                'read_at': datetime.utcnow()
            })
            
            db.session.commit()
            return count
            
        except Exception as e:
            current_app.logger.error(f"Error marking all notifications as read: {str(e)}")
            db.session.rollback()
            return 0
    
    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user"""
        try:
            return Notification.query.filter(
                or_(
                    Notification.target_user_id == user_id,
                    and_(
                        Notification.target_user_id.is_(None),
                        Notification.target_role.in_(
                            db.session.query(Role.name).join(
                                UserRole, UserRole.role_id == Role.id
                            ).filter(UserRole.user_id == user_id)
                        )
                    )
                ),
                Notification.is_read == False
            ).count()
            
        except Exception as e:
            current_app.logger.error(f"Error getting unread count: {str(e)}")
            return 0
    
    def subscribe_to_topic(self, user_id: int, topic: str) -> bool:
        """Subscribe user to a notification topic"""
        try:
            self.subscribers[topic].add(user_id)
            return True
        except Exception as e:
            current_app.logger.error(f"Error subscribing to topic: {str(e)}")
            return False
    
    def unsubscribe_from_topic(self, user_id: int, topic: str) -> bool:
        """Unsubscribe user from a notification topic"""
        try:
            if topic in self.subscribers:
                self.subscribers[topic].discard(user_id)
            return True
        except Exception as e:
            current_app.logger.error(f"Error unsubscribing from topic: {str(e)}")
            return False
    
    def register_connection(self, user_id: int, connection_info: Dict[str, Any]):
        """Register an active SSE/WebSocket connection"""
        self.active_connections[user_id] = connection_info
    
    def unregister_connection(self, user_id: int):
        """Unregister an active connection"""
        self.active_connections.pop(user_id, None)
    
    def _log_notification_sent(
        self, 
        title: str, 
        message: str, 
        notification_type: NotificationType,
        priority: NotificationPriority,
        user_count: int,
        channels: List[str]
    ):
        """Log notification sent event for audit"""
        # This would integrate with the audit service
        pass


# Global instance
notifications_service = NotificationsService()
