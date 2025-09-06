"""
Centralized Audit & Compliance Service

Provides unified audit logging and compliance tracking including:
- Single immutable event log
- Global activity timeline with filters
- Compliance reporting
- Export capabilities
- Real-time audit monitoring
"""

from typing import List, Dict, Optional, Any, Union
from datetime import datetime, timedelta, date
from enum import Enum
from dataclasses import dataclass
from flask import current_app, request
from extensions import db
from models import User
from sqlalchemy import and_, or_, desc, func, extract
import json
import csv
import io
from collections import defaultdict


class EventType(Enum):
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    GUEST_CREATE = "guest_create"
    GUEST_UPDATE = "guest_update"
    GUEST_DELETE = "guest_delete"
    GUEST_CHECKIN = "guest_checkin"
    GUEST_CHECKOUT = "guest_checkout"
    PAYMENT_CREATE = "payment_create"
    PAYMENT_UPDATE = "payment_update"
    PAYMENT_DELETE = "payment_delete"
    EXPENSE_CREATE = "expense_create"
    EXPENSE_UPDATE = "expense_update"
    EXPENSE_DELETE = "expense_delete"
    INVENTORY_UPDATE = "inventory_update"
    INVENTORY_TRANSACTION = "inventory_transaction"
    BULK_ACTION = "bulk_action"
    NOTIFICATION_SEND = "notification_send"
    REPORT_GENERATE = "report_generate"
    SYSTEM_EVENT = "system_event"


class EventSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Represents an audit event"""
    id: str
    event_type: EventType
    user_id: Optional[int]
    user_name: Optional[str]
    entity_type: Optional[str]  # Type of entity affected (e.g., 'guest', 'payment')
    entity_id: Optional[str]    # ID of entity affected
    action: str                 # Action performed
    description: str            # Human-readable description
    old_values: Optional[Dict[str, Any]]  # Previous values
    new_values: Optional[Dict[str, Any]]  # New values
    metadata: Dict[str, Any]    # Additional metadata
    ip_address: Optional[str]   # IP address of user
    user_agent: Optional[str]   # User agent string
    severity: EventSeverity
    created_at: datetime
    session_id: Optional[str]   # Session identifier


@dataclass
class ComplianceRule:
    """Represents a compliance rule"""
    id: str
    name: str
    description: str
    event_types: List[EventType]
    conditions: Dict[str, Any]  # Conditions that trigger the rule
    severity: EventSeverity
    is_active: bool


class AuditService:
    """Centralized audit and compliance service"""
    
    def __init__(self):
        self.events = []  # In production, this would be in database
        self.compliance_rules = self._load_compliance_rules()
        self.event_handlers = self._register_event_handlers()
    
    def _load_compliance_rules(self) -> List[ComplianceRule]:
        """Load compliance rules"""
        return [
            ComplianceRule(
                id='user_failed_login',
                name='Failed Login Attempts',
                description='Multiple failed login attempts',
                event_types=[EventType.USER_LOGIN],
                conditions={'max_attempts': 5, 'time_window': 300},  # 5 attempts in 5 minutes
                severity=EventSeverity.HIGH,
                is_active=True
            ),
            ComplianceRule(
                id='bulk_data_export',
                name='Bulk Data Export',
                description='Large data export operations',
                event_types=[EventType.BULK_ACTION],
                conditions={'min_items': 100},
                severity=EventSeverity.MEDIUM,
                is_active=True
            ),
            ComplianceRule(
                id='financial_data_access',
                name='Financial Data Access',
                description='Access to sensitive financial data',
                event_types=[EventType.REPORT_GENERATE, EventType.PAYMENT_CREATE],
                conditions={'sensitive_data': True},
                severity=EventSeverity.HIGH,
                is_active=True
            )
        ]
    
    def _register_event_handlers(self) -> Dict[EventType, callable]:
        """Register event handlers for different event types"""
        return {
            EventType.USER_LOGIN: self._handle_user_login,
            EventType.USER_LOGOUT: self._handle_user_logout,
            EventType.GUEST_CREATE: self._handle_guest_create,
            EventType.GUEST_UPDATE: self._handle_guest_update,
            EventType.PAYMENT_CREATE: self._handle_payment_create,
            EventType.BULK_ACTION: self._handle_bulk_action,
            EventType.SYSTEM_EVENT: self._handle_system_event
        }
    
    def log_event(
        self,
        event_type: EventType,
        user_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: str = "",
        description: str = "",
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        severity: EventSeverity = EventSeverity.MEDIUM
    ) -> str:
        """
        Log an audit event
        
        Args:
            event_type: Type of event
            user_id: ID of user performing the action
            entity_type: Type of entity affected
            entity_id: ID of entity affected
            action: Action performed
            description: Human-readable description
            old_values: Previous values (for updates)
            new_values: New values (for updates)
            metadata: Additional metadata
            severity: Event severity level
            
        Returns:
            str: Event ID
        """
        try:
            # Get user information
            user_name = None
            if user_id:
                user = User.query.get(user_id)
                if user:
                    user_name = user.username
            
            # Get request information
            ip_address = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent') if request else None
            session_id = request.cookies.get('session') if request else None
            
            # Create event
            event_id = f"event_{int(datetime.utcnow().timestamp() * 1000)}"
            event = AuditEvent(
                id=event_id,
                event_type=event_type,
                user_id=user_id,
                user_name=user_name,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                description=description,
                old_values=old_values or {},
                new_values=new_values or {},
                metadata=metadata or {},
                ip_address=ip_address,
                user_agent=user_agent,
                severity=severity,
                created_at=datetime.utcnow(),
                session_id=session_id
            )
            
            # Store event
            self.events.append(event)
            
            # Check compliance rules
            self._check_compliance_rules(event)
            
            # Call event handler if exists
            handler = self.event_handlers.get(event_type)
            if handler:
                handler(event)
            
            current_app.logger.info(f"Audit event logged: {event_type.value} - {description}")
            
            return event_id
            
        except Exception as e:
            current_app.logger.error(f"Error logging audit event: {str(e)}")
            return None
    
    def _check_compliance_rules(self, event: AuditEvent):
        """Check if event triggers any compliance rules"""
        try:
            for rule in self.compliance_rules:
                if not rule.is_active or event.event_type not in rule.event_types:
                    continue
                
                if self._evaluate_rule_conditions(rule, event):
                    self._handle_compliance_violation(rule, event)
                    
        except Exception as e:
            current_app.logger.error(f"Error checking compliance rules: {str(e)}")
    
    def _evaluate_rule_conditions(self, rule: ComplianceRule, event: AuditEvent) -> bool:
        """Evaluate if event meets rule conditions"""
        try:
            conditions = rule.conditions
            
            if rule.id == 'user_failed_login':
                # Check for multiple failed login attempts
                recent_failed_logins = [
                    e for e in self.events
                    if e.event_type == EventType.USER_LOGIN
                    and e.user_id == event.user_id
                    and e.created_at > datetime.utcnow() - timedelta(seconds=conditions['time_window'])
                    and e.metadata.get('success') == False
                ]
                return len(recent_failed_logins) >= conditions['max_attempts']
            
            elif rule.id == 'bulk_data_export':
                # Check for large bulk operations
                return event.metadata.get('item_count', 0) >= conditions['min_items']
            
            elif rule.id == 'financial_data_access':
                # Check for financial data access
                return conditions['sensitive_data'] in event.metadata.get('data_types', [])
            
            return False
            
        except Exception as e:
            current_app.logger.error(f"Error evaluating rule conditions: {str(e)}")
            return False
    
    def _handle_compliance_violation(self, rule: ComplianceRule, event: AuditEvent):
        """Handle compliance rule violation"""
        try:
            # Log the violation
            violation_event = AuditEvent(
                id=f"violation_{int(datetime.utcnow().timestamp() * 1000)}",
                event_type=EventType.SYSTEM_EVENT,
                user_id=event.user_id,
                user_name=event.user_name,
                entity_type='compliance_rule',
                entity_id=rule.id,
                action='compliance_violation',
                description=f"Compliance rule violation: {rule.name}",
                old_values={},
                new_values={'rule_id': rule.id, 'triggering_event': event.id},
                metadata={'rule': rule.name, 'severity': rule.severity.value},
                ip_address=event.ip_address,
                user_agent=event.user_agent,
                severity=rule.severity,
                created_at=datetime.utcnow(),
                session_id=event.session_id
            )
            
            self.events.append(violation_event)
            
            # Send alert if critical
            if rule.severity in [EventSeverity.HIGH, EventSeverity.CRITICAL]:
                self._send_compliance_alert(rule, event)
            
            current_app.logger.warning(f"Compliance violation: {rule.name} - {event.description}")
            
        except Exception as e:
            current_app.logger.error(f"Error handling compliance violation: {str(e)}")
    
    def _send_compliance_alert(self, rule: ComplianceRule, event: AuditEvent):
        """Send compliance alert"""
        # This would integrate with notification service
        pass
    
    def get_activity_timeline(
        self,
        user_id: Optional[int] = None,
        event_types: Optional[List[EventType]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        severity: Optional[EventSeverity] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get activity timeline with filters
        
        Args:
            user_id: Filter by user ID
            event_types: Filter by event types
            entity_type: Filter by entity type
            entity_id: Filter by entity ID
            start_date: Filter by start date
            end_date: Filter by end date
            severity: Filter by severity
            limit: Maximum number of events
            offset: Offset for pagination
            
        Returns:
            Dict containing events and metadata
        """
        try:
            # Filter events
            filtered_events = self.events.copy()
            
            if user_id is not None:
                filtered_events = [e for e in filtered_events if e.user_id == user_id]
            
            if event_types:
                filtered_events = [e for e in filtered_events if e.event_type in event_types]
            
            if entity_type:
                filtered_events = [e for e in filtered_events if e.entity_type == entity_type]
            
            if entity_id:
                filtered_events = [e for e in filtered_events if e.entity_id == entity_id]
            
            if start_date:
                filtered_events = [e for e in filtered_events if e.created_at >= start_date]
            
            if end_date:
                filtered_events = [e for e in filtered_events if e.created_at <= end_date]
            
            if severity:
                filtered_events = [e for e in filtered_events if e.severity == severity]
            
            # Sort by created_at desc
            filtered_events.sort(key=lambda x: x.created_at, reverse=True)
            
            # Apply pagination
            total_count = len(filtered_events)
            paginated_events = filtered_events[offset:offset + limit]
            
            # Convert to dict format
            events_data = []
            for event in paginated_events:
                events_data.append({
                    'id': event.id,
                    'event_type': event.event_type.value,
                    'user_id': event.user_id,
                    'user_name': event.user_name,
                    'entity_type': event.entity_type,
                    'entity_id': event.entity_id,
                    'action': event.action,
                    'description': event.description,
                    'old_values': event.old_values,
                    'new_values': event.new_values,
                    'metadata': event.metadata,
                    'ip_address': event.ip_address,
                    'user_agent': event.user_agent,
                    'severity': event.severity.value,
                    'created_at': event.created_at.isoformat(),
                    'session_id': event.session_id
                })
            
            return {
                'events': events_data,
                'total_count': total_count,
                'has_more': offset + len(paginated_events) < total_count,
                'filters': {
                    'user_id': user_id,
                    'event_types': [et.value for et in event_types] if event_types else None,
                    'entity_type': entity_type,
                    'entity_id': entity_id,
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None,
                    'severity': severity.value if severity else None
                }
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting activity timeline: {str(e)}")
            return {'events': [], 'total_count': 0, 'has_more': False, 'error': str(e)}
    
    def export_audit_log(
        self,
        format: str = 'csv',
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export audit log in specified format"""
        try:
            # Get filtered events
            timeline_data = self.get_activity_timeline(
                user_id=filters.get('user_id') if filters else None,
                event_types=filters.get('event_types') if filters else None,
                entity_type=filters.get('entity_type') if filters else None,
                start_date=filters.get('start_date') if filters else None,
                end_date=filters.get('end_date') if filters else None,
                severity=filters.get('severity') if filters else None,
                limit=10000  # Large limit for export
            )
            
            if format.lower() == 'csv':
                return self._export_csv(timeline_data['events'])
            elif format.lower() == 'json':
                return self._export_json(timeline_data['events'])
            else:
                raise ValueError(f"Unsupported export format: {format}")
                
        except Exception as e:
            current_app.logger.error(f"Error exporting audit log: {str(e)}")
            return {'error': str(e)}
    
    def _export_csv(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Export events as CSV"""
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            if events:
                writer.writerow(events[0].keys())
                
                # Write data
                for event in events:
                    # Convert complex values to strings
                    row = []
                    for value in event.values():
                        if isinstance(value, (dict, list)):
                            row.append(json.dumps(value))
                        else:
                            row.append(str(value) if value is not None else '')
                    writer.writerow(row)
            
            csv_data = output.getvalue()
            output.close()
            
            return {
                'data': csv_data,
                'filename': f"audit_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
                'mime_type': 'text/csv'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error exporting CSV: {str(e)}")
            return {'error': str(e)}
    
    def _export_json(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Export events as JSON"""
        try:
            json_data = json.dumps(events, indent=2, default=str)
            
            return {
                'data': json_data,
                'filename': f"audit_log_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json",
                'mime_type': 'application/json'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error exporting JSON: {str(e)}")
            return {'error': str(e)}
    
    def get_compliance_report(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Generate compliance report"""
        try:
            if not start_date:
                start_date = datetime.utcnow() - timedelta(days=30)
            if not end_date:
                end_date = datetime.utcnow()
            
            # Get all events in date range
            timeline_data = self.get_activity_timeline(
                start_date=start_date,
                end_date=end_date,
                limit=10000
            )
            
            events = timeline_data['events']
            
            # Analyze compliance
            compliance_stats = {
                'total_events': len(events),
                'violations': 0,
                'high_severity_events': 0,
                'critical_events': 0,
                'user_activity': {},
                'event_type_distribution': {},
                'severity_distribution': {}
            }
            
            for event in events:
                # Count violations
                if 'compliance_violation' in event.get('action', ''):
                    compliance_stats['violations'] += 1
                
                # Count severity levels
                severity = event.get('severity', 'medium')
                compliance_stats['severity_distribution'][severity] = \
                    compliance_stats['severity_distribution'].get(severity, 0) + 1
                
                if severity == 'high':
                    compliance_stats['high_severity_events'] += 1
                elif severity == 'critical':
                    compliance_stats['critical_events'] += 1
                
                # Count event types
                event_type = event.get('event_type', 'unknown')
                compliance_stats['event_type_distribution'][event_type] = \
                    compliance_stats['event_type_distribution'].get(event_type, 0) + 1
                
                # Count user activity
                user_name = event.get('user_name', 'Unknown')
                compliance_stats['user_activity'][user_name] = \
                    compliance_stats['user_activity'].get(user_name, 0) + 1
            
            return {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                },
                'statistics': compliance_stats,
                'recommendations': self._generate_compliance_recommendations(compliance_stats)
            }
            
        except Exception as e:
            current_app.logger.error(f"Error generating compliance report: {str(e)}")
            return {'error': str(e)}
    
    def _generate_compliance_recommendations(self, stats: Dict[str, Any]) -> List[str]:
        """Generate compliance recommendations based on statistics"""
        recommendations = []
        
        if stats['violations'] > 10:
            recommendations.append("High number of compliance violations detected. Review security policies.")
        
        if stats['critical_events'] > 0:
            recommendations.append("Critical events detected. Immediate attention required.")
        
        if stats['high_severity_events'] > stats['total_events'] * 0.1:
            recommendations.append("High percentage of high-severity events. Review system security.")
        
        return recommendations
    
    # Event Handlers
    
    def _handle_user_login(self, event: AuditEvent):
        """Handle user login event"""
        # Additional processing for login events
        pass
    
    def _handle_user_logout(self, event: AuditEvent):
        """Handle user logout event"""
        # Additional processing for logout events
        pass
    
    def _handle_guest_create(self, event: AuditEvent):
        """Handle guest creation event"""
        # Additional processing for guest creation
        pass
    
    def _handle_guest_update(self, event: AuditEvent):
        """Handle guest update event"""
        # Additional processing for guest updates
        pass
    
    def _handle_payment_create(self, event: AuditEvent):
        """Handle payment creation event"""
        # Additional processing for payment creation
        pass
    
    def _handle_bulk_action(self, event: AuditEvent):
        """Handle bulk action event"""
        # Additional processing for bulk actions
        pass
    
    def _handle_system_event(self, event: AuditEvent):
        """Handle system event"""
        # Additional processing for system events
        pass


# Global instance
audit_service = AuditService()
