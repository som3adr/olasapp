"""
Centralized Reporting & Analytics Service

Provides unified reporting capabilities across all modules including:
- Central datasets and widgets
- Role-filtered widgets
- Saved views and schedules
- Export capabilities
- Real-time data updates
"""

from typing import List, Dict, Optional, Any, Union
from datetime import datetime, timedelta, date
from enum import Enum
from dataclasses import dataclass
from flask import current_app
from extensions import db
from models import User, Tenant, Payment, Expense, InventoryItem, InventoryTransaction
from sqlalchemy import and_, or_, desc, func, extract
import json
import csv
import io
from collections import defaultdict


class ReportType(Enum):
    GUEST_ANALYTICS = "guest_analytics"
    FINANCIAL_SUMMARY = "financial_summary"
    INVENTORY_REPORT = "inventory_report"
    OCCUPANCY_REPORT = "occupancy_report"
    PAYMENT_ANALYSIS = "payment_analysis"
    EXPENSE_BREAKDOWN = "expense_breakdown"
    STAFF_PERFORMANCE = "staff_performance"
    CUSTOM = "custom"


class WidgetType(Enum):
    CHART = "chart"
    TABLE = "table"
    METRIC = "metric"
    KPI = "kpi"
    TREND = "trend"


class ExportFormat(Enum):
    CSV = "csv"
    PDF = "pdf"
    EXCEL = "excel"
    JSON = "json"


@dataclass
class ReportWidget:
    """Represents a report widget"""
    id: str
    name: str
    widget_type: WidgetType
    report_type: ReportType
    data_source: str
    config: Dict[str, Any]
    filters: Dict[str, Any]
    permissions: List[str]  # Required permissions to view
    refresh_interval: int  # Seconds


@dataclass
class SavedView:
    """Represents a saved report view"""
    id: str
    name: str
    user_id: int
    report_type: ReportType
    widgets: List[str]  # Widget IDs
    filters: Dict[str, Any]
    layout: Dict[str, Any]
    is_public: bool
    created_at: datetime


@dataclass
class ScheduledReport:
    """Represents a scheduled report"""
    id: str
    name: str
    user_id: int
    report_type: ReportType
    schedule: str  # Cron expression
    recipients: List[str]  # Email addresses
    format: ExportFormat
    filters: Dict[str, Any]
    is_active: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]


class ReportingService:
    """Centralized reporting and analytics service"""
    
    def __init__(self):
        self.widgets = self._load_default_widgets()
        self.saved_views = {}  # In production, this would be in database
        self.scheduled_reports = {}  # In production, this would be in database
        self.data_sources = self._register_data_sources()
    
    def _load_default_widgets(self) -> Dict[str, ReportWidget]:
        """Load default report widgets"""
        return {
            'guest_occupancy_chart': ReportWidget(
                id='guest_occupancy_chart',
                name='Guest Occupancy Trend',
                widget_type=WidgetType.CHART,
                report_type=ReportType.GUEST_ANALYTICS,
                data_source='guest_occupancy',
                config={'chart_type': 'line', 'x_axis': 'date', 'y_axis': 'occupancy_rate'},
                filters={'date_range': '30_days'},
                permissions=['view_guests'],
                refresh_interval=300
            ),
            'revenue_metric': ReportWidget(
                id='revenue_metric',
                name='Total Revenue',
                widget_type=WidgetType.METRIC,
                report_type=ReportType.FINANCIAL_SUMMARY,
                data_source='revenue_summary',
                config={'format': 'currency', 'currency': 'MAD'},
                filters={'date_range': 'current_month'},
                permissions=['view_finance'],
                refresh_interval=60
            ),
            'expense_breakdown_chart': ReportWidget(
                id='expense_breakdown_chart',
                name='Expense Breakdown',
                widget_type=WidgetType.CHART,
                report_type=ReportType.EXPENSE_BREAKDOWN,
                data_source='expense_breakdown',
                config={'chart_type': 'pie', 'group_by': 'category'},
                filters={'date_range': 'current_month'},
                permissions=['view_finance'],
                refresh_interval=300
            ),
            'inventory_low_stock_table': ReportWidget(
                id='inventory_low_stock_table',
                name='Low Stock Items',
                widget_type=WidgetType.TABLE,
                report_type=ReportType.INVENTORY_REPORT,
                data_source='low_stock_items',
                config={'columns': ['name', 'current_stock', 'reorder_point', 'status']},
                filters={'threshold': 10},
                permissions=['view_inventory'],
                refresh_interval=600
            )
        }
    
    def _register_data_sources(self) -> Dict[str, callable]:
        """Register data source functions"""
        return {
            'guest_occupancy': self._get_guest_occupancy_data,
            'revenue_summary': self._get_revenue_summary_data,
            'expense_breakdown': self._get_expense_breakdown_data,
            'low_stock_items': self._get_low_stock_items_data,
            'payment_analysis': self._get_payment_analysis_data,
            'staff_performance': self._get_staff_performance_data
        }
    
    def generate_report(
        self,
        report_type: ReportType,
        user_id: int,
        filters: Optional[Dict[str, Any]] = None,
        widgets: Optional[List[str]] = None,
        date_range: Optional[Dict[str, date]] = None
    ) -> Dict[str, Any]:
        """
        Generate a report with specified parameters
        
        Args:
            report_type: Type of report to generate
            user_id: ID of user requesting the report
            filters: Additional filters to apply
            widgets: Specific widgets to include (None for all)
            date_range: Date range for the report
            
        Returns:
            Dict containing report data and metadata
        """
        try:
            # Get user permissions
            user_permissions = self._get_user_permissions(user_id)
            
            # Filter widgets by permissions and report type
            available_widgets = self._get_available_widgets(report_type, user_permissions)
            
            if widgets:
                available_widgets = [w for w in available_widgets if w.id in widgets]
            
            # Generate widget data
            report_data = {}
            for widget in available_widgets:
                try:
                    widget_data = self._generate_widget_data(widget, filters, date_range)
                    report_data[widget.id] = {
                        'widget': widget,
                        'data': widget_data,
                        'generated_at': datetime.utcnow().isoformat()
                    }
                except Exception as e:
                    current_app.logger.error(f"Error generating widget {widget.id}: {str(e)}")
                    report_data[widget.id] = {
                        'widget': widget,
                        'data': None,
                        'error': str(e),
                        'generated_at': datetime.utcnow().isoformat()
                    }
            
            return {
                'report_type': report_type.value,
                'generated_at': datetime.utcnow().isoformat(),
                'filters': filters or {},
                'date_range': date_range or {},
                'widgets': report_data,
                'metadata': {
                    'total_widgets': len(available_widgets),
                    'successful_widgets': len([w for w in report_data.values() if w.get('data') is not None]),
                    'failed_widgets': len([w for w in report_data.values() if w.get('error') is not None])
                }
            }
            
        except Exception as e:
            current_app.logger.error(f"Error generating report: {str(e)}")
            return {
                'error': str(e),
                'report_type': report_type.value,
                'generated_at': datetime.utcnow().isoformat()
            }
    
    def _get_user_permissions(self, user_id: int) -> List[str]:
        """Get permissions for a user"""
        try:
            user = User.query.get(user_id)
            if not user:
                return []
            
            if user.is_admin:
                return ['admin']  # Admins have all permissions
            
            # Get role-based permissions
            permissions = []
            for user_role in user.user_roles:
                for permission in user_role.role.permissions:
                    permissions.append(permission.name)
            
            return permissions
            
        except Exception as e:
            current_app.logger.error(f"Error getting user permissions: {str(e)}")
            return []
    
    def _get_available_widgets(self, report_type: ReportType, permissions: List[str]) -> List[ReportWidget]:
        """Get available widgets for a report type and user permissions"""
        available = []
        
        for widget in self.widgets.values():
            if widget.report_type == report_type:
                # Check if user has required permissions
                if any(perm in permissions or 'admin' in permissions for perm in widget.permissions):
                    available.append(widget)
        
        return available
    
    def _generate_widget_data(self, widget: ReportWidget, filters: Dict[str, Any], date_range: Dict[str, date]) -> Any:
        """Generate data for a specific widget"""
        try:
            data_source = self.data_sources.get(widget.data_source)
            if not data_source:
                raise ValueError(f"Data source {widget.data_source} not found")
            
            # Merge widget filters with provided filters
            merged_filters = {**widget.filters, **(filters or {})}
            
            return data_source(merged_filters, date_range)
            
        except Exception as e:
            current_app.logger.error(f"Error generating widget data for {widget.id}: {str(e)}")
            raise
    
    # Data Source Functions
    
    def _get_guest_occupancy_data(self, filters: Dict[str, Any], date_range: Dict[str, date]) -> Dict[str, Any]:
        """Get guest occupancy data for charts"""
        try:
            # Calculate date range
            end_date = date_range.get('end_date', date.today())
            start_date = date_range.get('start_date', end_date - timedelta(days=30))
            
            # Get occupancy data by date
            occupancy_data = []
            current_date = start_date
            
            while current_date <= end_date:
                # Count active guests on this date
                active_guests = Tenant.query.filter(
                    Tenant.start_date <= current_date,
                    or_(
                        Tenant.end_date.is_(None),
                        Tenant.end_date >= current_date
                    ),
                    Tenant.is_active == True
                ).count()
                
                occupancy_data.append({
                    'date': current_date.isoformat(),
                    'occupancy': active_guests
                })
                
                current_date += timedelta(days=1)
            
            return {
                'type': 'line',
                'data': occupancy_data,
                'x_axis': 'date',
                'y_axis': 'occupancy',
                'title': 'Guest Occupancy Trend'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting guest occupancy data: {str(e)}")
            return {'error': str(e)}
    
    def _get_revenue_summary_data(self, filters: Dict[str, Any], date_range: Dict[str, date]) -> Dict[str, Any]:
        """Get revenue summary data"""
        try:
            # Calculate date range
            end_date = date_range.get('end_date', date.today())
            start_date = date_range.get('start_date', end_date - timedelta(days=30))
            
            # Get total revenue
            total_revenue = db.session.query(func.sum(Payment.amount)).filter(
                Payment.payment_date >= start_date,
                Payment.payment_date <= end_date,
                Payment.status == 'completed'
            ).scalar() or 0
            
            # Get previous period for comparison
            prev_start = start_date - (end_date - start_date)
            prev_end = start_date - timedelta(days=1)
            
            prev_revenue = db.session.query(func.sum(Payment.amount)).filter(
                Payment.payment_date >= prev_start,
                Payment.payment_date <= prev_end,
                Payment.status == 'completed'
            ).scalar() or 0
            
            # Calculate growth
            growth = 0
            if prev_revenue > 0:
                growth = ((total_revenue - prev_revenue) / prev_revenue) * 100
            
            return {
                'value': total_revenue,
                'currency': 'MAD',
                'growth': growth,
                'previous_period': prev_revenue,
                'period': f"{start_date} to {end_date}"
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting revenue summary data: {str(e)}")
            return {'error': str(e)}
    
    def _get_expense_breakdown_data(self, filters: Dict[str, Any], date_range: Dict[str, date]) -> Dict[str, Any]:
        """Get expense breakdown data"""
        try:
            # Calculate date range
            end_date = date_range.get('end_date', date.today())
            start_date = date_range.get('start_date', end_date - timedelta(days=30))
            
            # Get expenses by category
            expenses = db.session.query(
                Expense.category,
                func.sum(Expense.amount).label('total')
            ).filter(
                Expense.date >= start_date,
                Expense.date <= end_date
            ).group_by(Expense.category).all()
            
            breakdown_data = []
            total_expenses = 0
            
            for category, amount in expenses:
                breakdown_data.append({
                    'category': category,
                    'amount': float(amount),
                    'percentage': 0  # Will be calculated below
                })
                total_expenses += float(amount)
            
            # Calculate percentages
            for item in breakdown_data:
                if total_expenses > 0:
                    item['percentage'] = (item['amount'] / total_expenses) * 100
            
            return {
                'type': 'pie',
                'data': breakdown_data,
                'total': total_expenses,
                'title': 'Expense Breakdown'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting expense breakdown data: {str(e)}")
            return {'error': str(e)}
    
    def _get_low_stock_items_data(self, filters: Dict[str, Any], date_range: Dict[str, date]) -> Dict[str, Any]:
        """Get low stock items data"""
        try:
            threshold = filters.get('threshold', 10)
            
            # Get items with low stock
            low_stock_items = InventoryItem.query.filter(
                InventoryItem.current_stock <= threshold
            ).all()
            
            items_data = []
            for item in low_stock_items:
                status = 'Critical' if item.current_stock <= 0 else 'Low'
                items_data.append({
                    'id': item.id,
                    'name': item.name,
                    'current_stock': item.current_stock,
                    'reorder_point': item.reorder_point,
                    'status': status,
                    'category': item.category
                })
            
            return {
                'type': 'table',
                'data': items_data,
                'columns': ['name', 'current_stock', 'reorder_point', 'status'],
                'title': 'Low Stock Items'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting low stock items data: {str(e)}")
            return {'error': str(e)}
    
    def _get_payment_analysis_data(self, filters: Dict[str, Any], date_range: Dict[str, date]) -> Dict[str, Any]:
        """Get payment analysis data"""
        try:
            # Calculate date range
            end_date = date_range.get('end_date', date.today())
            start_date = date_range.get('start_date', end_date - timedelta(days=30))
            
            # Get payment data
            payments = db.session.query(
                extract('day', Payment.payment_date).label('day'),
                func.sum(Payment.amount).label('total')
            ).filter(
                Payment.payment_date >= start_date,
                Payment.payment_date <= end_date,
                Payment.status == 'completed'
            ).group_by(extract('day', Payment.payment_date)).all()
            
            payment_data = []
            for day, amount in payments:
                payment_data.append({
                    'day': int(day),
                    'amount': float(amount)
                })
            
            return {
                'type': 'bar',
                'data': payment_data,
                'x_axis': 'day',
                'y_axis': 'amount',
                'title': 'Daily Payment Analysis'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error getting payment analysis data: {str(e)}")
            return {'error': str(e)}
    
    def _get_staff_performance_data(self, filters: Dict[str, Any], date_range: Dict[str, date]) -> Dict[str, Any]:
        """Get staff performance data"""
        # This would integrate with staff management module
        return {'type': 'table', 'data': [], 'title': 'Staff Performance'}
    
    def save_view(
        self,
        name: str,
        user_id: int,
        report_type: ReportType,
        widgets: List[str],
        filters: Dict[str, Any],
        layout: Dict[str, Any],
        is_public: bool = False
    ) -> str:
        """Save a report view"""
        try:
            view_id = f"view_{user_id}_{int(datetime.utcnow().timestamp())}"
            
            saved_view = SavedView(
                id=view_id,
                name=name,
                user_id=user_id,
                report_type=report_type,
                widgets=widgets,
                filters=filters,
                layout=layout,
                is_public=is_public,
                created_at=datetime.utcnow()
            )
            
            self.saved_views[view_id] = saved_view
            
            return view_id
            
        except Exception as e:
            current_app.logger.error(f"Error saving view: {str(e)}")
            return None
    
    def get_saved_views(self, user_id: int) -> List[Dict[str, Any]]:
        """Get saved views for a user"""
        user_views = [
            view for view in self.saved_views.values()
            if view.user_id == user_id or view.is_public
        ]
        
        return [
            {
                'id': view.id,
                'name': view.name,
                'report_type': view.report_type.value,
                'widgets': view.widgets,
                'filters': view.filters,
                'layout': view.layout,
                'is_public': view.is_public,
                'created_at': view.created_at.isoformat()
            }
            for view in user_views
        ]
    
    def export_report(
        self,
        report_data: Dict[str, Any],
        format: ExportFormat,
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Export report data in specified format"""
        try:
            if not filename:
                filename = f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            if format == ExportFormat.CSV:
                return self._export_csv(report_data, filename)
            elif format == ExportFormat.JSON:
                return self._export_json(report_data, filename)
            else:
                raise ValueError(f"Unsupported export format: {format}")
                
        except Exception as e:
            current_app.logger.error(f"Error exporting report: {str(e)}")
            return {'error': str(e)}
    
    def _export_csv(self, report_data: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """Export report data as CSV"""
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write report metadata
            writer.writerow(['Report Type', report_data.get('report_type', 'Unknown')])
            writer.writerow(['Generated At', report_data.get('generated_at', '')])
            writer.writerow([])
            
            # Write widget data
            for widget_id, widget_data in report_data.get('widgets', {}).items():
                widget = widget_data.get('widget')
                data = widget_data.get('data')
                
                if widget and data:
                    writer.writerow([f"Widget: {widget.name}"])
                    
                    if widget.widget_type == WidgetType.TABLE:
                        # Write table data
                        if 'data' in data and isinstance(data['data'], list):
                            if data['data']:
                                # Write headers
                                writer.writerow(data['data'][0].keys())
                                # Write rows
                                for row in data['data']:
                                    writer.writerow(row.values())
                    
                    writer.writerow([])
            
            csv_data = output.getvalue()
            output.close()
            
            return {
                'data': csv_data,
                'filename': f"{filename}.csv",
                'mime_type': 'text/csv'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error exporting CSV: {str(e)}")
            return {'error': str(e)}
    
    def _export_json(self, report_data: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """Export report data as JSON"""
        try:
            json_data = json.dumps(report_data, indent=2, default=str)
            
            return {
                'data': json_data,
                'filename': f"{filename}.json",
                'mime_type': 'application/json'
            }
            
        except Exception as e:
            current_app.logger.error(f"Error exporting JSON: {str(e)}")
            return {'error': str(e)}


# Global instance
reporting_service = ReportingService()
