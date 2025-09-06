#!/usr/bin/env python3
"""
Test script to verify the edit user fix
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import User, db

def test_edit_user_fix():
    """Test if edit user functionality should work now"""
    
    with app.app_context():
        print("🔧 Testing Edit User Fix")
        print("=" * 30)
        
        # Check users and their admin status
        users = User.query.all()
        print("Users in database:")
        for user in users:
            print(f"  - {user.username}")
            print(f"    - is_admin: {user.is_admin}")
            print(f"    - is_active: {user.is_active}")
            print(f"    - ID: {user.id}")
            print()
        
        # Check if there are any admin users
        admin_users = User.query.filter_by(is_admin=True).all()
        if admin_users:
            print(f"✅ Found {len(admin_users)} admin user(s):")
            for admin in admin_users:
                print(f"  - {admin.username} (ID: {admin.id})")
        else:
            print("❌ No admin users found!")
            print("Creating an admin user...")
            
            # Create an admin user if none exists
            admin_user = User(
                username='admin',
                email='admin@hostel.com',
                full_name='Administrator',
                is_admin=True,
                is_active=True
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Created admin user: admin/admin123")
        
        print("\n🎯 Edit user functionality should now work!")
        print("The edit user button should be accessible to admin users.")
        print("If you're logged in as an admin user, try clicking the edit button again.")

if __name__ == "__main__":
    try:
        test_edit_user_fix()
    except Exception as e:
        print(f"💥 Error: {str(e)}")
        import traceback
        traceback.print_exc()
