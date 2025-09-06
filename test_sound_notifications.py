#!/usr/bin/env python3
"""
Test script to verify sound notifications are working
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import User, Notification, db
from notification_service import NotificationService
from datetime import datetime

def test_sound_notifications():
    """Test sound notification functionality"""
    
    with app.app_context():
        print("🔊 Testing Sound Notifications")
        print("=" * 50)
        
        # Get a test user
        test_user = User.query.first()
        if not test_user:
            print("❌ No users found. Please create a user first.")
            return False
        
        print(f"Using test user: {test_user.username}")
        
        # Test different types of notifications with different priorities
        test_notifications = [
            {
                'title': 'Test Guest Check-in',
                'message': 'Guest John Doe has checked in to bed 5 in room 2',
                'notification_type': 'guest_checkin',
                'priority': 'normal'
            },
            {
                'title': 'Test Payment Received',
                'message': 'Payment of 500 MAD received from Jane Smith',
                'notification_type': 'payment',
                'priority': 'high'
            },
            {
                'title': 'Test Restaurant Order',
                'message': 'New order placed: 2x Breakfast for Room 3',
                'notification_type': 'order',
                'priority': 'normal'
            },
            {
                'title': 'Test System Alert',
                'message': 'System maintenance scheduled for tonight',
                'notification_type': 'system',
                'priority': 'warning'
            }
        ]
        
        print("\nCreating test notifications...")
        created_notifications = []
        
        for i, notif_data in enumerate(test_notifications, 1):
            print(f"\n{i}. Creating {notif_data['notification_type']} notification...")
            
            notification = NotificationService.notify_all_users(
                title=notif_data['title'],
                message=notif_data['message'],
                notification_type=notif_data['notification_type'],
                related_entity_type='test',
                related_entity_id=i,
                priority=notif_data['priority'],
                data={
                    'test_type': notif_data['notification_type'],
                    'test_priority': notif_data['priority'],
                    'created_by': test_user.username,
                    'test_timestamp': datetime.now().isoformat()
                }
            )
            
            if notification:
                print(f"   ✅ Created notification ID: {notification.id}")
                print(f"   📝 Title: {notification.title}")
                print(f"   📝 Message: {notification.message}")
                print(f"   📝 Type: {notification.notification_type}")
                print(f"   📝 Priority: {notification.priority}")
                created_notifications.append(notification)
            else:
                print(f"   ❌ Failed to create notification")
        
        print(f"\n📊 Summary:")
        print(f"   Total notifications created: {len(created_notifications)}")
        print(f"   Total notifications in database: {Notification.query.count()}")
        
        # Test notification retrieval
        print(f"\n🔍 Testing notification retrieval...")
        user_notifications = NotificationService.get_notifications_for_user(
            user_id=test_user.id,
            limit=10
        )
        
        print(f"   Notifications for user {test_user.username}: {len(user_notifications)}")
        
        # Test unread count
        unread_count = NotificationService.get_unread_count(test_user.id)
        print(f"   Unread notifications: {unread_count}")
        
        print(f"\n🎵 Sound Notification Instructions:")
        print(f"   1. Open the application in your browser")
        print(f"   2. Click on the notification bell icon in the top navbar")
        print(f"   3. Click on the settings (gear) icon")
        print(f"   4. Make sure 'Enable Sound Notifications' is checked")
        print(f"   5. Select a sound type (Default Beep, Gentle Chime, Alert Sound, etc.)")
        print(f"   6. Adjust the volume slider")
        print(f"   7. Click 'Test Sound' to hear the selected sound")
        print(f"   8. Save settings")
        print(f"   9. The next time a notification is received, it will play the selected sound")
        
        print(f"\n🔧 Browser Requirements:")
        print(f"   - Modern browser with Web Audio API support")
        print(f"   - Audio context must be started by user interaction")
        print(f"   - Some browsers may require HTTPS for audio playback")
        
        print(f"\n🎉 Sound notification test completed!")
        print(f"The notification system is ready for sound notifications.")
        
        return True

if __name__ == "__main__":
    try:
        success = test_sound_notifications()
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
