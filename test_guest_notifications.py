#!/usr/bin/env python3
"""
Test script for guest check-in/check-out notifications

This script tests the notification functionality when guests check in or out.
Run this script to verify that notifications are being created properly.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from models import User, Tenant, Bed, Room, CheckInOut, Notification
from notification_service import NotificationService
from datetime import datetime, timedelta

def test_guest_notifications():
    """Test guest check-in and check-out notifications"""
    
    # Create Flask app context
    app = create_app()
    
    with app.app_context():
        print("🧪 Testing Guest Check-in/Check-out Notifications")
        print("=" * 50)
        
        # Get or create a test user
        test_user = User.query.filter_by(username='admin').first()
        if not test_user:
            print("❌ No admin user found. Please create an admin user first.")
            return False
        
        # Get or create a test room and bed
        test_room = Room.query.first()
        if not test_room:
            print("❌ No rooms found. Please create a room first.")
            return False
        
        test_bed = Bed.query.filter_by(room_id=test_room.id, is_occupied=False).first()
        if not test_bed:
            print("❌ No available beds found. Please create a bed first.")
            return False
        
        # Get or create a test tenant
        test_tenant = Tenant.query.filter_by(is_active=False).first()
        if not test_tenant:
            print("❌ No inactive tenants found. Creating a test tenant...")
            test_tenant = Tenant(
                name="Test Guest",
                email="test@example.com",
                phone="123456789",
                daily_rent=100.0,
                start_date=datetime.now().date(),
                end_date=datetime.now().date() + timedelta(days=1),
                is_active=False
            )
            db.session.add(test_tenant)
            db.session.commit()
            print("✅ Test tenant created")
        
        print(f"📋 Test Setup:")
        print(f"   - User: {test_user.username}")
        print(f"   - Tenant: {test_tenant.name}")
        print(f"   - Room: {test_room.room_number}")
        print(f"   - Bed: {test_bed.bed_number}")
        print()
        
        # Test 1: Guest Check-in Notification
        print("🔔 Test 1: Guest Check-in Notification")
        print("-" * 30)
        
        # Count notifications before
        notifications_before = Notification.query.count()
        print(f"   Notifications before: {notifications_before}")
        
        # Simulate guest check-in
        checkin = CheckInOut(
            tenant_id=test_tenant.id,
            bed_id=test_bed.id,
            check_in_date=datetime.now(),
            expected_check_out_date=datetime.now() + timedelta(days=1),
            status='checked_in',
            checked_in_by=test_user.id
        )
        
        # Update bed status
        test_bed.is_occupied = True
        test_bed.tenant_id = test_tenant.id
        
        # Update tenant status
        test_tenant.is_active = True
        
        db.session.add(checkin)
        db.session.commit()
        
        # Send notification
        notification = NotificationService.notify_all_users(
            title="Test Guest Check-in",
            message=f"Guest {test_tenant.name} has checked in to bed {test_bed.bed_number} in room {test_room.room_number}",
            notification_type='guest_checkin',
            related_entity_type='tenant',
            related_entity_id=test_tenant.id,
            priority='normal',
            data={
                'guest_name': test_tenant.name,
                'bed_number': test_bed.bed_number,
                'room_number': test_room.room_number,
                'check_in_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'checked_in_by': test_user.username
            }
        )
        
        # Count notifications after
        notifications_after = Notification.query.count()
        print(f"   Notifications after: {notifications_after}")
        
        if notification and notifications_after > notifications_before:
            print("   ✅ Check-in notification created successfully")
            print(f"   📝 Notification ID: {notification.id}")
            print(f"   📝 Title: {notification.title}")
            print(f"   📝 Message: {notification.message}")
        else:
            print("   ❌ Check-in notification failed")
            return False
        
        print()
        
        # Test 2: Guest Check-out Notification
        print("🔔 Test 2: Guest Check-out Notification")
        print("-" * 30)
        
        # Count notifications before
        notifications_before = notifications_after
        print(f"   Notifications before: {notifications_before}")
        
        # Simulate guest check-out
        checkin.status = 'checked_out'
        checkin.actual_check_out_date = datetime.now()
        
        # Update bed status
        test_bed.is_occupied = False
        test_bed.tenant_id = None
        test_bed.status = 'dirty'
        
        # Update tenant status
        test_tenant.is_active = False
        test_tenant.end_date = datetime.now().date()
        
        db.session.commit()
        
        # Send notification
        notification = NotificationService.notify_all_users(
            title="Test Guest Check-out",
            message=f"Guest {test_tenant.name} has checked out from bed {test_bed.bed_number}",
            notification_type='guest_checkout',
            related_entity_type='tenant',
            related_entity_id=test_tenant.id,
            priority='normal',
            data={
                'guest_name': test_tenant.name,
                'bed_number': test_bed.bed_number,
                'room_number': test_room.room_number,
                'check_out_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'checked_out_by': test_user.username
            }
        )
        
        # Count notifications after
        notifications_after = Notification.query.count()
        print(f"   Notifications after: {notifications_after}")
        
        if notification and notifications_after > notifications_before:
            print("   ✅ Check-out notification created successfully")
            print(f"   📝 Notification ID: {notification.id}")
            print(f"   📝 Title: {notification.title}")
            print(f"   📝 Message: {notification.message}")
        else:
            print("   ❌ Check-out notification failed")
            return False
        
        print()
        
        # Test 3: Verify Notification Data
        print("🔍 Test 3: Verify Notification Data")
        print("-" * 30)
        
        # Get all notifications for the test tenant
        tenant_notifications = Notification.query.filter(
            Notification.related_entity_type == 'tenant',
            Notification.related_entity_id == test_tenant.id
        ).order_by(Notification.created_at.desc()).all()
        
        print(f"   Total notifications for tenant: {len(tenant_notifications)}")
        
        for i, notif in enumerate(tenant_notifications, 1):
            print(f"   Notification {i}:")
            print(f"     - Type: {notif.notification_type}")
            print(f"     - Title: {notif.title}")
            print(f"     - Priority: {notif.priority}")
            print(f"     - Created: {notif.created_at}")
            if notif.data:
                print(f"     - Data: {notif.data}")
        
        print()
        
        # Test 4: Test Notification Retrieval
        print("🔍 Test 4: Test Notification Retrieval")
        print("-" * 30)
        
        # Test getting notifications for user
        user_notifications = NotificationService.get_notifications_for_user(
            user_id=test_user.id,
            limit=10
        )
        
        print(f"   Notifications for user {test_user.username}: {len(user_notifications)}")
        
        for i, notif in enumerate(user_notifications, 1):
            print(f"   Notification {i}: {notif['title']} - {notif['message']}")
        
        print()
        print("🎉 All tests completed successfully!")
        print("✅ Guest check-in/check-out notifications are working properly")
        
        return True

if __name__ == "__main__":
    try:
        success = test_guest_notifications()
        if success:
            print("\n🎯 Test Results: PASSED")
            sys.exit(0)
        else:
            print("\n❌ Test Results: FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test Error: {str(e)}")
        sys.exit(1)
