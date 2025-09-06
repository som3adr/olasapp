#!/usr/bin/env python3
"""
Test script to check user permissions and user management functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import User, Role, Permission, UserRole, db
from flask_login import current_user

def test_user_permissions():
    """Test user permissions and user management functionality"""
    
    with app.app_context():
        print("🔍 Testing User Management Permissions")
        print("=" * 50)
        
        # Check if permissions exist
        permissions = Permission.query.all()
        print(f"Available permissions ({len(permissions)}):")
        for p in permissions:
            print(f"  - {p.name}: {p.description}")
        
        print("\nChecking users and their permissions:")
        users = User.query.all()
        for user in users:
            print(f"User: {user.username} (ID: {user.id})")
            print(f"  - is_admin: {user.is_admin}")
            print(f"  - is_active: {user.is_active}")
            print(f"  - roles: {[role.name for role in user.roles]}")
            print(f"  - permissions: {[perm.name for perm in user.permissions]}")
            print()
        
        # Check if edit_users permission exists
        edit_permission = Permission.query.filter_by(name='edit_users').first()
        if edit_permission:
            print(f"✅ 'edit_users' permission exists (ID: {edit_permission.id})")
        else:
            print("❌ 'edit_users' permission does not exist")
            
        # Check if view_users permission exists
        view_permission = Permission.query.filter_by(name='view_users').first()
        if view_permission:
            print(f"✅ 'view_users' permission exists (ID: {view_permission.id})")
        else:
            print("❌ 'view_users' permission does not exist")
        
        # Check if any user has edit_users permission
        users_with_edit = User.query.join(UserRole).join(Role).join(Permission).filter(
            Permission.name == 'edit_users'
        ).all()
        
        if users_with_edit:
            print(f"✅ Users with 'edit_users' permission: {[u.username for u in users_with_edit]}")
        else:
            print("❌ No users have 'edit_users' permission")
            
        # Check if any user has view_users permission
        users_with_view = User.query.join(UserRole).join(Role).join(Permission).filter(
            Permission.name == 'view_users'
        ).all()
        
        if users_with_view:
            print(f"✅ Users with 'view_users' permission: {[u.username for u in users_with_view]}")
        else:
            print("❌ No users have 'view_users' permission")

if __name__ == "__main__":
    try:
        test_user_permissions()
    except Exception as e:
        print(f"💥 Error: {str(e)}")
        import traceback
        traceback.print_exc()
