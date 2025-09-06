#!/usr/bin/env python3

# Test script to check for duplicate permission names
permissions = [
    # User Management Module
    ('view_users', 'View user list and details', 'users'),
    ('create_users', 'Create new users', 'users'),
    ('edit_users', 'Edit existing users', 'users'),
    ('delete_users', 'Delete users', 'users'),
    ('manage_roles', 'Manage user roles', 'roles'),
    ('manage_permissions', 'Manage system permissions', 'permissions'),
    ('toggle_user_status', 'Toggle user active/inactive status', 'users'),
    ('view_user_roles', 'View user role assignments', 'users'),
    
    # Dashboard Module
    ('view_dashboard', 'Access dashboard', 'dashboard'),
    ('view_analytics', 'View analytics and charts', 'dashboard'),
    ('view_statistics', 'View system statistics', 'dashboard'),
    ('view_revenue_charts', 'View revenue charts and data', 'dashboard'),
    ('view_occupancy_charts', 'View occupancy charts and data', 'dashboard'),
    ('view_chart_data', 'View chart data and analytics', 'dashboard'),
    
    # Guest Management Module
    ('view_tenants', 'View guest information', 'guests'),
    ('create_tenants', 'Create new guests', 'guests'),
    ('edit_tenants', 'Edit guest information', 'guests'),
    ('delete_tenants', 'Delete guests', 'guests'),
    ('view_tenant_history', 'View guest history', 'guests'),
    ('view_tenant_details', 'View detailed guest information', 'guests'),
    ('manage_tenant_services', 'Manage guest services and packages', 'guests'),
    ('view_tenant_payments', 'View guest payment information', 'guests'),
    ('create_tenant_payments', 'Create payment records for guests', 'guests'),
    ('edit_tenant_payments', 'Edit guest payment records', 'guests'),
    ('delete_tenant_payments', 'Delete guest payment records', 'guests'),
    ('deactivate_tenants', 'Deactivate guest accounts', 'guests'),
    
    # Check-In/Out Module
    ('view_checkins', 'View check-in/out records', 'checkin'),
    ('create_checkins', 'Process check-ins', 'checkin'),
    ('edit_checkins', 'Edit check-in records', 'checkin'),
    ('extend_stays', 'Extend guest stays', 'checkin'),
    ('process_checkouts', 'Process check-outs', 'checkin'),
    ('view_checkin_history', 'View check-in/out history', 'checkin'),
    ('view_active_stays', 'View currently active stays', 'checkin'),
    ('checkout_guests', 'Process guest checkouts', 'checkin'),
    
    # Room Management Module
    ('view_rooms', 'View rooms and beds', 'rooms'),
    ('create_rooms', 'Create new rooms', 'rooms'),
    ('edit_rooms', 'Edit room information', 'rooms'),
    ('delete_rooms', 'Delete rooms', 'rooms'),
    ('manage_beds', 'Manage bed assignments', 'rooms'),
    ('view_room_status', 'View room availability', 'rooms'),
    ('view_room_details', 'View detailed room information', 'rooms'),
    ('view_room_assignments', 'View room and bed assignments', 'rooms'),
    ('add_beds', 'Add beds to rooms', 'rooms'),
    ('edit_beds', 'Edit bed information', 'rooms'),
    ('delete_beds', 'Delete beds', 'rooms'),
    ('rent_beds', 'Rent beds to guests', 'rooms'),
    ('vacate_beds', 'Vacate beds from guests', 'rooms'),
    ('view_room_calendar', 'View room calendar and availability', 'rooms'),
    ('view_occupancy_report', 'View room occupancy reports', 'rooms'),
    
    # Booking Calendar Module
    ('view_calendar', 'View booking calendar', 'booking'),
    ('create_bookings', 'Create new bookings', 'booking'),
    ('edit_bookings', 'Edit existing bookings', 'booking'),
    ('cancel_bookings', 'Cancel bookings', 'booking'),
    ('view_booking_details', 'View detailed booking information', 'booking'),
    ('view_availability', 'View room availability calendar', 'booking'),
    ('quick_book', 'Perform quick bookings', 'booking'),
    
    # Inventory Management Module
    ('view_inventory', 'View inventory items', 'inventory'),
    ('create_inventory', 'Create inventory items', 'inventory'),
    ('edit_inventory', 'Edit inventory items', 'inventory'),
    ('delete_inventory', 'Delete inventory items', 'inventory'),
    ('manage_categories', 'Manage inventory categories', 'inventory'),
    ('manage_transactions', 'Manage inventory transactions', 'inventory'),
    ('view_transactions', 'View transaction history', 'inventory'),
    ('export_inventory', 'Export inventory data', 'inventory'),
    ('view_low_stock', 'View low stock alerts', 'inventory'),
    ('manage_suppliers', 'Manage suppliers', 'inventory'),
    ('view_global_transactions', 'View all inventory transactions', 'inventory'),
    ('add_transactions', 'Add inventory transactions', 'inventory'),
    
    # Maintenance Module
    ('view_maintenance', 'View maintenance requests', 'maintenance'),
    ('create_requests', 'Create maintenance requests', 'maintenance'),
    ('edit_requests', 'Edit maintenance requests', 'maintenance'),
    ('delete_requests', 'Delete maintenance requests', 'maintenance'),
    ('assign_requests', 'Assign maintenance tasks', 'maintenance'),
    ('update_request_status', 'Update request status', 'maintenance'),
    ('view_maintenance_history', 'View maintenance history', 'maintenance'),
    ('view_room_beds_api', 'Access room beds API', 'maintenance'),
    
    # Meal Management Module
    ('view_meals', 'View meal plans', 'meals'),
    ('create_meals', 'Create meal plans', 'meals'),
    ('edit_meals', 'Edit meal plans', 'meals'),
    ('delete_meals', 'Delete meal plans', 'meals'),
    ('assign_meals', 'Assign meals to guests', 'meals'),
    ('view_daily_meals', 'View daily meal schedules', 'meals'),
    ('bulk_meal_operations', 'Perform bulk meal operations', 'meals'),
    ('view_meal_services', 'View meal service configurations', 'meals'),
    ('view_guest_meal_preferences', 'View guest meal preferences', 'meals'),
    ('view_meal_statistics', 'View meal service statistics', 'meals'),
    ('add_meals', 'Add meals for guests', 'meals'),
    ('remove_meals', 'Remove meals from guests', 'meals'),
    ('bulk_add_meals', 'Bulk add meals for multiple guests', 'meals'),
    ('bulk_remove_meals', 'Bulk remove meals from multiple guests', 'meals'),
    ('view_guest_meals_api', 'Access guest meals API', 'meals'),
    
    # Financial Management Module
    ('view_expenses', 'View expenses', 'financial'),
    ('create_expenses', 'Create expense records', 'financial'),
    ('edit_expenses', 'Edit expense records', 'financial'),
    ('delete_expenses', 'Delete expense records', 'financial'),
    ('view_payments', 'View payment records', 'financial'),
    ('create_payments', 'Create payment records', 'financial'),
    ('edit_payments', 'Edit payment records', 'financial'),
    ('delete_payments', 'Delete payment records', 'financial'),
    ('view_income', 'View income records', 'financial'),
    ('create_income', 'Create income records', 'financial'),
    ('edit_income', 'Edit income records', 'financial'),
    ('delete_income', 'Delete income records', 'financial'),
    ('manage_payment_links', 'Manage payment links', 'financial'),
    ('view_payment_links', 'View payment link information', 'financial'),
    ('create_payment_links', 'Create payment links', 'financial'),
    ('edit_payment_links', 'Edit payment links', 'financial'),
    ('delete_payment_links', 'Delete payment links', 'financial'),
    ('view_financial_dashboard', 'View financial dashboard', 'financial'),
    ('view_revenue_analytics', 'View revenue analytics', 'financial'),
    ('pay_payment_links', 'Process payment link payments', 'financial'),
    ('process_payment_links', 'Process payment link transactions', 'financial'),
    ('resend_payment_links', 'Resend payment links', 'financial'),
    ('cancel_payment_links', 'Cancel payment links', 'financial'),
    
    # Reports Module
    ('view_reports', 'View basic reports', 'reports'),
    ('view_guest_reports', 'View guest reports', 'reports'),
    ('view_inventory_reports', 'View inventory reports', 'reports'),
    ('view_maintenance_reports', 'View maintenance reports', 'reports'),
    ('view_meal_reports', 'View meal service reports', 'reports'),
    ('export_reports', 'Export report data', 'reports'),
    ('export_expenses', 'Export expense reports', 'reports'),
    ('export_payments', 'Export payment reports', 'reports'),
    ('export_inventory_reports', 'Export inventory reports', 'reports'),
    
    # Audit and Security Module
    ('view_audit_logs', 'View audit logs', 'audit'),
    ('view_audit_detail', 'View detailed audit log information', 'audit'),
    
    # Communication Module
    ('view_communications', 'View guest communications', 'communications'),
    ('send_messages', 'Send messages to guests', 'communications'),
    ('view_communication_history', 'View communication history', 'communications'),
    ('send_email', 'Send emails to guests', 'communications'),
    ('send_sms', 'Send SMS to guests', 'communications'),
    ('view_templates', 'View communication templates', 'communications'),
    
    # Feedback Module
    ('view_feedback', 'View guest feedback', 'feedback'),
    ('respond_feedback', 'Respond to guest feedback', 'feedback'),
    ('view_feedback_analytics', 'View feedback analytics and trends', 'feedback'),
    ('view_all_feedback', 'View all feedback with filtering', 'feedback'),
    ('view_feedback_detail', 'View detailed feedback information', 'feedback'),
    ('submit_feedback', 'Submit feedback for guests', 'feedback'),
    ('access_feedback_api', 'Access feedback API endpoints', 'feedback'),
    
    # Financial Reports Module
    ('view_financial_reports', 'View financial reports', 'financial_reports'),
    ('view_profit_loss_reports', 'View profit and loss reports', 'financial_reports'),
    ('view_revenue_analysis_reports', 'View detailed revenue analysis', 'financial_reports'),
    ('view_expense_analysis_reports', 'View detailed expense analysis', 'financial_reports'),
    ('view_cash_flow_reports', 'View cash flow reports', 'financial_reports'),
    ('access_monthly_comparison_api', 'Access monthly comparison API', 'financial_reports')
]

# Check for duplicates
permission_names = [p[0] for p in permissions]
duplicates = []
seen = set()

for name in permission_names:
    if name in seen:
        duplicates.append(name)
    else:
        seen.add(name)

if duplicates:
    print(f"Found {len(duplicates)} duplicate permission names:")
    for dup in duplicates:
        print(f"  - {dup}")
else:
    print("No duplicate permission names found!")
    print(f"Total unique permissions: {len(permission_names)}")

# Group by module
modules = {}
for name, desc, module in permissions:
    if module not in modules:
        modules[module] = []
    modules[module].append(name)

print(f"\nPermissions by module:")
for module, perms in modules.items():
    print(f"  {module}: {len(perms)} permissions")
