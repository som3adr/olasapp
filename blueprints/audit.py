from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from extensions import db
from models import AuditLog, User
from datetime import datetime, timedelta
import json

audit_bp = Blueprint('audit', __name__, url_prefix='/audit')


@audit_bp.route('/')
@login_required
def index():
    # Only allow admin users to view audit logs
    if not current_user.is_admin:
        return render_template('errors/403.html'), 403
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filters
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    query = AuditLog.query
    
    # Apply filters
    if action_filter:
        query = query.filter(AuditLog.action.contains(action_filter))
    
    if user_filter:
        query = query.filter(AuditLog.user_id == int(user_filter))
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AuditLog.created_at < date_to_obj)
        except ValueError:
            pass
    
    # Order by most recent first
    query = query.order_by(AuditLog.created_at.desc())
    
    # Paginate
    audit_logs = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get users for filter dropdown
    users = User.query.order_by(User.username).all()
    
    # Get unique actions for filter
    unique_actions = db.session.query(AuditLog.action).distinct().all()
    actions = [action[0] for action in unique_actions]
    
    return render_template('audit/index.html',
                         audit_logs=audit_logs,
                         users=users,
                         actions=actions,
                         action_filter=action_filter,
                         user_filter=user_filter,
                         date_from=date_from,
                         date_to=date_to)


@audit_bp.route('/detail/<int:log_id>')
@login_required
def detail(log_id):
    # Only allow admin users to view audit log details
    if not current_user.is_admin:
        return render_template('errors/403.html'), 403
    
    log_entry = AuditLog.query.get_or_404(log_id)
    
    # Parse JSON values
    old_values = json.loads(log_entry.old_values) if log_entry.old_values else {}
    new_values = json.loads(log_entry.new_values) if log_entry.new_values else {}
    
    return render_template('audit/detail.html',
                         log_entry=log_entry,
                         old_values=old_values,
                         new_values=new_values)


