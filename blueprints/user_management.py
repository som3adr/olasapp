from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import User, Role, Permission, UserRole, db
from sqlalchemy import and_, or_
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from functools import wraps
from permissions import require_admin

user_management_bp = Blueprint('user_management', __name__, url_prefix='/user-management')

# Permission decorator
def require_permission(permission_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.has_permission(permission_name):
                flash('Access denied. You do not have permission to perform this action.', 'danger')
                return redirect(url_for('user_management.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@user_management_bp.route('/')
@login_required
@require_admin
def index():
    """User management dashboard"""
    users = User.query.all()
    roles = Role.query.all()
    permissions = Permission.query.all()
    
    return render_template('user_management/index.html',
                         users=users,
                         roles=roles,
                         permissions=permissions)

@user_management_bp.route('/users')
@login_required
@require_admin
def users_list():
    """List all users with pagination and search"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.full_name.ilike(f'%{search}%')
            )
        )
    
    if role_filter:
        query = query.join(UserRole).join(Role).filter(Role.name == role_filter)
    
    users = query.paginate(page=page, per_page=20, error_out=False)
    roles = Role.query.all()
    
    return render_template('user_management/users_list.html',
                         users=users,
                         roles=roles,
                         search=search,
                         role_filter=role_filter)

@user_management_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
# @require_permission('create_users')  # Temporarily commented out for testing
def add_user():
    """Add new user"""
    print(f"DEBUG: add_user route called, method: {request.method}")
    
    if request.method == 'POST':
        print(f"DEBUG: Processing POST request")
        print(f"DEBUG: Form data: {request.form}")
        try:
            data = request.form
            
            # Check if username or email already exists
            if User.query.filter_by(username=data['username']).first():
                print(f"DEBUG: Username already exists: {data['username']}")
                flash('Username already exists.', 'danger')
                return render_template('user_management/add_user.html', roles=Role.query.all())
            
            if User.query.filter_by(email=data['email']).first():
                print(f"DEBUG: Email already exists: {data['email']}")
                flash('Email already exists.', 'danger')
                return render_template('user_management/add_user.html', roles=Role.query.all())
            
            print(f"DEBUG: Creating new user: {data['username']}")
            # Create new user
            user = User(
                username=data['username'],
                email=data['email'],
                full_name=data['full_name'],
                password_hash=generate_password_hash(data['password']),
                is_active=data.get('is_active') == 'on',  # Convert checkbox value to boolean
                created_at=datetime.utcnow()
            )
            
            db.session.add(user)
            db.session.flush()  # Get user ID
            print(f"DEBUG: User created with ID: {user.id}")
            
            # Assign roles
            if data.get('roles'):
                role_ids = [int(rid) for rid in data.getlist('roles')]
                print(f"DEBUG: Assigning roles: {role_ids}")
                for role_id in role_ids:
                    user_role = UserRole(user_id=user.id, role_id=role_id)
                    db.session.add(user_role)
            else:
                print(f"DEBUG: No roles selected")
            
            db.session.commit()
            print(f"DEBUG: User committed to database successfully")
            flash('User created successfully!', 'success')
            return redirect(url_for('user_management.users_list'))
            
        except Exception as e:
            print(f"DEBUG: Error creating user: {str(e)}")
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
    
    print(f"DEBUG: Rendering add_user template")
    return render_template('user_management/add_user.html', roles=Role.query.all())

@user_management_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@require_admin
def edit_user(user_id):
    """Edit existing user"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        try:
            data = request.form
            
            # Check if username or email already exists (excluding current user)
            existing_user = User.query.filter_by(username=data['username']).first()
            if existing_user and existing_user.id != user.id:
                flash('Username already exists.', 'danger')
                return render_template('user_management/edit_user.html', user=user, roles=Role.query.all())
            
            existing_user = User.query.filter_by(email=data['email']).first()
            if existing_user and existing_user.id != user.id:
                flash('Email already exists.', 'danger')
                return render_template('user_management/edit_user.html', user=user, roles=Role.query.all())
            
            # Update user data
            user.username = data['username']
            user.email = data['email']
            user.full_name = data['full_name']
            # Convert checkbox value to boolean
            user.is_active = data.get('is_active') == 'on'
            user.updated_at = datetime.utcnow()
            
            # Update password if provided
            if data.get('password'):
                user.password_hash = generate_password_hash(data['password'])
            
            # Update roles
            UserRole.query.filter_by(user_id=user.id).delete()
            if data.get('roles'):
                role_ids = [int(rid) for rid in data.getlist('roles')]
                for role_id in role_ids:
                    user_role = UserRole(user_id=user.id, role_id=role_id)
                    db.session.add(user_role)
            
            db.session.commit()
            flash('User updated successfully!', 'success')
            return redirect(url_for('user_management.users_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')
    
    return render_template('user_management/edit_user.html', user=user, roles=Role.query.all())

@user_management_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@require_admin
def delete_user(user_id):
    """Delete user"""
    if current_user.id == user_id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('user_management.users_list'))
    
    user = User.query.get_or_404(user_id)
    
    try:
        # Delete user roles first
        UserRole.query.filter_by(user_id=user.id).delete()
        
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        flash('User deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'danger')
    
    return redirect(url_for('user_management.users_list'))

@user_management_bp.route('/roles')
@login_required
@require_admin
def roles_list():
    """List all roles"""
    roles = Role.query.all()
    return render_template('user_management/roles_list.html', roles=roles)

@user_management_bp.route('/roles/add', methods=['GET', 'POST'])
@login_required
@require_admin
def add_role():
    """Add new role"""
    if request.method == 'POST':
        try:
            data = request.form
            
            # Check if role name already exists
            if Role.query.filter_by(name=data['name']).first():
                flash('Role name already exists.', 'danger')
                return render_template('user_management/add_role.html', permissions=Permission.query.all())
            
            # Create new role
            role = Role(
                name=data['name'],
                description=data['description'],
                created_at=datetime.utcnow()
            )
            
            db.session.add(role)
            db.session.flush()  # Get role ID
            
            # Assign permissions
            if data.get('permissions'):
                permission_ids = [int(pid) for pid in data.getlist('permissions')]
                for permission_id in permission_ids:
                    permission = Permission.query.get(permission_id)
                    if permission:
                        role.permissions.append(permission)
            
            db.session.commit()
            flash('Role created successfully!', 'success')
            return redirect(url_for('user_management.roles_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating role: {str(e)}', 'danger')
    
    return render_template('user_management/add_role.html', permissions=Permission.query.all())

@user_management_bp.route('/roles/add-all-permissions', methods=['GET', 'POST'])
@login_required
@require_admin
def add_role_all_permissions():
    """Add new role with ALL permissions (for testing)"""
    if request.method == 'POST':
        try:
            data = request.form
            
            # Check if role name already exists
            if Role.query.filter_by(name=data['name']).first():
                flash('Role name already exists.', 'danger')
                return render_template('user_management/add_role.html', permissions=Permission.query.all())
            
            # Create new role
            role = Role(
                name=data['name'],
                description=data.get('description', 'Role with all permissions')
            )
            
            db.session.add(role)
            db.session.flush()  # Get ID
            
            # Assign ALL permissions to this role
            all_permissions = Permission.query.all()
            for permission in all_permissions:
                role.permissions.append(permission)
            
            db.session.commit()
            flash(f'Role "{role.name}" created successfully with ALL permissions!', 'success')
            return redirect(url_for('user_management.roles_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating role: {str(e)}', 'danger')
            return render_template('user_management/add_role.html', permissions=Permission.query.all())
    
    return render_template('user_management/add_role.html', permissions=Permission.query.all())

@user_management_bp.route('/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
@require_admin
def edit_role(role_id):
    """Edit existing role"""
    role = Role.query.get_or_404(role_id)
    
    if request.method == 'POST':
        try:
            data = request.form
            
            # Check if role name already exists (excluding current role)
            existing_role = Role.query.filter_by(name=data['name']).first()
            if existing_role and existing_role.id != role.id:
                flash('Role name already exists.', 'danger')
                return render_template('user_management/edit_role.html', role=role, permissions=Permission.query.all())
            
            # Update role data
            role.name = data['name']
            role.description = data['description']
            role.updated_at = datetime.utcnow()
            
            # Update permissions
            role.permissions.clear()
            if data.get('permissions'):
                permission_ids = [int(pid) for pid in data.getlist('permissions')]
                for permission_id in permission_ids:
                    permission = Permission.query.get(permission_id)
                    if permission:
                        role.permissions.append(permission)
            
            db.session.commit()
            flash('Role updated successfully!', 'success')
            return redirect(url_for('user_management.roles_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating role: {str(e)}', 'danger')
    
    return render_template('user_management/edit_role.html', role=role, permissions=Permission.query.all())

@user_management_bp.route('/roles/<int:role_id>/delete', methods=['POST'])
@login_required
@require_admin
def delete_role(role_id):
    """Delete role"""
    role = Role.query.get_or_404(role_id)
    
    # Check if role is assigned to any users
    if UserRole.query.filter_by(role_id=role.id).first():
        flash('Cannot delete role that is assigned to users.', 'danger')
        return redirect(url_for('user_management.roles_list'))
    
    try:
        db.session.delete(role)
        db.session.commit()
        flash('Role deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting role: {str(e)}', 'danger')
    
    return redirect(url_for('user_management.roles_list'))

@user_management_bp.route('/permissions')
@login_required
@require_admin
def permissions_list():
    """List all permissions"""
    permissions = Permission.query.all()
    return render_template('user_management/permissions_list.html', permissions=permissions)

@user_management_bp.route('/permissions/add', methods=['GET', 'POST'])
@login_required
@require_admin
def add_permission():
    """Add new permission"""
    if request.method == 'POST':
        try:
            data = request.form
            
            # Check if permission name already exists
            if Permission.query.filter_by(name=data['name']).first():
                flash('Permission name already exists.', 'danger')
                return render_template('user_management/add_permission.html')
            
            # Create new permission
            permission = Permission(
                name=data['name'],
                description=data['description'],
                module=data['module'],
                created_at=datetime.utcnow()
            )
            
            db.session.add(permission)
            db.session.commit()
            
            flash('Permission created successfully!', 'success')
            return redirect(url_for('user_management.permissions_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating permission: {str(e)}', 'danger')
    
    return render_template('user_management/add_permission.html')

@user_management_bp.route('/permissions/<int:permission_id>/edit', methods=['GET', 'POST'])
@login_required
@require_admin
def edit_permission(permission_id):
    """Edit existing permission"""
    permission = Permission.query.get_or_404(permission_id)
    
    if request.method == 'POST':
        try:
            data = request.form
            
            # Check if permission name already exists (excluding current permission)
            existing_permission = Permission.query.filter_by(name=data['name']).first()
            if existing_permission and existing_permission.id != permission.id:
                flash('Permission name already exists.', 'danger')
                return render_template('user_management/edit_permission.html', permission=permission)
            
            # Update permission data
            permission.name = data['name']
            permission.description = data['description']
            permission.module = data['module']
            permission.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash('Permission updated successfully!', 'success')
            return redirect(url_for('user_management.permissions_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating permission: {str(e)}', 'danger')
    
    return render_template('user_management/edit_permission.html', permission=permission)

@user_management_bp.route('/permissions/<int:permission_id>/delete', methods=['POST'])
@login_required
@require_admin
def delete_permission(permission_id):
    """Delete permission"""
    permission = Permission.query.get_or_404(permission_id)
    
    try:
        db.session.delete(permission)
        db.session.commit()
        flash('Permission deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting permission: {str(e)}', 'danger')
    
    return redirect(url_for('user_management.permissions_list'))

# API endpoints for AJAX operations
@user_management_bp.route('/api/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@require_admin
def toggle_user_status(user_id):
    """Toggle user active status"""
    if current_user.id == user_id:
        return jsonify({'success': False, 'error': 'You cannot deactivate your own account'})
    
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    user.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'is_active': user.is_active,
            'message': f'User {"activated" if user.is_active else "deactivated"} successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@user_management_bp.route('/api/users/<int:user_id>/roles', methods=['GET'])
@login_required
@require_admin
def get_user_roles(user_id):
    """Get user roles for AJAX"""
    user = User.query.get_or_404(user_id)
    roles = [{'id': role.id, 'name': role.name} for role in user.roles]
    return jsonify({'success': True, 'roles': roles})
