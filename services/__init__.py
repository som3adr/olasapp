# Shared Services Package
"""
Centralized services for HostelFlow application.

This package contains shared services that provide cross-cutting functionality
across all domain modules, reducing duplication and ensuring consistency.
"""

from .notifications_service import NotificationsService
from .bulk_actions_service import BulkActionsService
from .reporting_service import ReportingService
from .audit_service import AuditService

__all__ = [
    'NotificationsService',
    'BulkActionsService', 
    'ReportingService',
    'AuditService'
]
