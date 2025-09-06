#!/usr/bin/env python3
"""
Test script to verify guest creation notifications
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import User, Tenant, Notification, db
from notification_service import NotificationService
from datetime import datetime, date, timedelta

def test_guest_notification():
    """Test guest creation notification functionality"""
    
    with app.app_context():
        print("🔔 Testing Guest Creation Notifications")
        print("=" * 50)
        
        # Check if there are any existing notifications
        existing_notifications = Notification.query.count()
        print(f"Existing notifications in database: {existing_notifications}")
        
        # Get a test user
        test_user = User.query.first()
        if not test_user:
            print("❌ No users found. Please create a user first.")
            return False
        
        print(f"Using test user: {test_user.username}")
        
        # Test notification creation
        print("\nTesting notification creation...")
        notification = NotificationService.notify_all_users(
            title="Test Guest Added",
            message="Test guest John Doe has been added to the system for 3 days",
            notification_type='guest_added',
            related_entity_type='tenant',
            related_entity_id=1,
            priority='normal',
            data={
                'guest_name': 'John Doe',
                'number_of_days': 3,
                'start_date': '2025-01-15',
                'end_date': '2025-01-18',
                'daily_rent': 100.0,
                'number_of_guests': 1,
                'is_prepaid': False,
                'hostel_name': 'Olas',
                'created_by': test_user.username
            }
        )
        
        if notification:
            print(f"✅ Test notification created successfully with ID: {notification.id}")
            print(f"   Title: {notification.title}")
            print(f"   Message: {notification.message}")
            print(f"   Type: {notification.notification_type}")
            print(f"   Priority: {notification.priority}")
        else:
            print("❌ Failed to create test notification")
            return False
        
        # Check if notification was saved to database
        new_notification_count = Notification.query.count()
        print(f"\nNotification count after test: {new_notification_count}")
        
        if new_notification_count > existing_notifications:
            print("✅ Notification was saved to database")
        else:
            print("❌ Notification was not saved to database")
            return False
        
        # Test getting notifications for user
        print("\nTesting notification retrieval...")
        user_notifications = NotificationService.get_notifications_for_user(
            user_id=test_user.id,
            limit=10
        )
        
        print(f"Notifications for user {test_user.username}: {len(user_notifications)}")
        for i, notif in enumerate(user_notifications, 1):
            print(f"  {i}. {notif['title']} - {notif['message']}")
        
        print("\n🎉 Guest notification test completed successfully!")
        print("The notification system is working properly.")
        
        return True

if __name__ == "__main__":
    try:
        success = test_guest_notification()
        if success:
            print("\n✅ Test Results: PASSED")
            sys.exit(0)
        else:
            print("\n❌ Test Results: FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
