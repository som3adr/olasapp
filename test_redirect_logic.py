#!/usr/bin/env python3

from app import app
from models import User

with app.app_context():
    # Test both users
    admin_user = User.query.filter_by(username='admin').first()
    staff_user = User.query.filter_by(username='staff').first()
    
    print("=== ADMIN USER ===")
    if admin_user:
        print(f'Username: {admin_user.username}')
        print(f'Is admin: {admin_user.is_admin}')
        print(f'Is active: {admin_user.is_active}')
        
        # Test redirect logic
        if admin_user.is_admin:
            redirect_url = '/dashboard'
            print(f'Redirect URL: {redirect_url}')
        else:
            redirect_url = '/staff-dashboard'
            print(f'Redirect URL: {redirect_url}')
    
    print("\n=== STAFF USER ===")
    if staff_user:
        print(f'Username: {staff_user.username}')
        print(f'Is admin: {staff_user.is_admin}')
        print(f'Is active: {staff_user.is_active}')
        
        # Test redirect logic
        if staff_user.is_admin:
            redirect_url = '/dashboard'
            print(f'Redirect URL: {redirect_url}')
        else:
            redirect_url = '/staff-dashboard'
            print(f'Redirect URL: {redirect_url}')
    
    # Check if there are any other users that might be causing confusion
    print("\n=== ALL USERS ===")
    all_users = User.query.all()
    for user in all_users:
        print(f'User: {user.username}, Is admin: {user.is_admin}, Is active: {user.is_active}')
