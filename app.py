import os
import logging
from flask import Flask, redirect, send_from_directory, Response
from extensions import db, login_manager
from datetime import date, timedelta
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash
from models import User, Service, TenantService, Bed, Tenant

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# db and login_manager are defined in extensions.py

# create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure session settings for persistent login
app.config['PERMANENT_SESSION_LIFETIME'] = 30 * 24 * 60 * 60  # 30 days in seconds
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent XSS attacks
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection

# configure the database - PostgreSQL
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://admin:Prefetch%4010@192.168.1.42:5432/hostel_management"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# initialize extensions
db.init_app(app)
print("✅ Using PostgreSQL database: hostel_management")
print("🌐 Server: 192.168.1.42:5432")
print("👤 User: admin")
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Configure persistent login settings
login_manager.remember_cookie_duration = 30 * 24 * 60 * 60  # 30 days in seconds
login_manager.session_protection = "strong"  # Strong session protection

# Add session refresh on each request to keep users logged in during active use
@app.before_request
def refresh_session():
    from flask import session
    from flask_login import current_user
    
    if current_user.is_authenticated:
        session.permanent = True

# Make permissions available to templates
@app.context_processor
def inject_permissions():
    """Inject permissions and menu functions into template context"""
    from permissions import (
        get_menu_items, 
        can_access_feature, 
        has_any_permission, 
        has_any_role, 
        get_user_role_names
    )
    
    # Create a wrapper function that automatically passes current_user
    def get_dynamic_menu_items():
        from flask_login import current_user
        if current_user.is_authenticated:
            return get_menu_items(current_user)
        return {}
    
    return {
        'get_dynamic_menu_items': get_dynamic_menu_items,  # Wrapper function for backward compatibility
        'get_menu_items': get_menu_items,
        'can_access_feature': can_access_feature,
        'has_any_permission': has_any_permission,
        'has_any_role': has_any_role,
        'get_user_role_names': get_user_role_names
    }

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Register blueprints
from auth import auth_bp
from blueprints.dashboard import dashboard_bp
from blueprints.expenses import expenses_bp
from blueprints.guests import guests_bp
from blueprints.inventory import inventory_bp
from blueprints.reports import reports_bp
from blueprints.checkin import checkin_bp

from blueprints.user_management import user_management_bp
from blueprints.food_extras import food_extras_bp
from blueprints.finance_suppliers import finance_suppliers_bp
from blueprints.staff_tasks import staff_tasks_bp
from blueprints.audit import audit_bp
from blueprints.staff_dashboard import staff_dashboard_bp
from blueprints.restaurant_orders import restaurant_orders_bp

# Add root route redirect to dashboard
@app.route('/')
def root():
    from flask_login import current_user
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect('/dashboard')
        else:
            return redirect('/staff-dashboard')
    else:
        return redirect('/auth/login')

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(expenses_bp)
app.register_blueprint(guests_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(checkin_bp)

app.register_blueprint(user_management_bp)
app.register_blueprint(food_extras_bp)
app.register_blueprint(finance_suppliers_bp)
app.register_blueprint(staff_tasks_bp)
app.register_blueprint(audit_bp)
app.register_blueprint(staff_dashboard_bp)
app.register_blueprint(restaurant_orders_bp)

# Import and register employee salaries blueprint
from blueprints.employee_salaries import employee_salaries_bp
app.register_blueprint(employee_salaries_bp)

# Import and register notifications blueprint
from blueprints.notifications import notifications_bp
app.register_blueprint(notifications_bp)

# Import and register realtime notifications blueprint
from blueprints.realtime_notifications import realtime_bp
app.register_blueprint(realtime_bp)

# Breakfast auto-generation is now integrated into restaurant_orders blueprint

with app.app_context():
    # Import models to ensure tables are created
    import models
    
    # Create all tables
    print("Creating database tables...")
    db.create_all()
    print("✅ All tables created successfully!")
    
    # Seed initial data for role-based access control
    try:
        # Check if we need to seed data
        if db.session.query(models.Role).count() == 0:
            print("Seeding initial roles and permissions...")
            
            # Create comprehensive permissions for all application features
            permissions = [
                # User Management Module
                models.Permission(name='view_users', description='View user list and details', module='users'),
                models.Permission(name='create_users', description='Create new users', module='users'),
                models.Permission(name='edit_users', description='Edit existing users', module='users'),
                models.Permission(name='delete_users', description='Delete users', module='users'),
                models.Permission(name='manage_roles', description='Manage user roles', module='roles'),
                models.Permission(name='manage_permissions', description='Manage system permissions', module='permissions'),
                models.Permission(name='toggle_user_status', description='Toggle user active/inactive status', module='users'),
                models.Permission(name='view_user_roles', description='View user role assignments', module='users'),
                
                # Dashboard Module
                models.Permission(name='view_dashboard', description='Access dashboard', module='dashboard'),
                models.Permission(name='view_analytics', description='View analytics and charts', module='dashboard'),
                models.Permission(name='view_statistics', description='View system statistics', module='dashboard'),
                models.Permission(name='view_revenue_charts', description='View revenue charts and data', module='dashboard'),
                models.Permission(name='view_occupancy_charts', description='View occupancy charts and data', module='dashboard'),
                models.Permission(name='view_chart_data', description='View chart data and analytics', module='dashboard'),
                
                # Guest Management Module
                models.Permission(name='view_tenants', description='View guest information', module='guests'),
                models.Permission(name='create_tenants', description='Create new guests', module='guests'),
                models.Permission(name='edit_tenants', description='Edit guest information', module='guests'),
                models.Permission(name='delete_tenants', description='Delete guests', module='guests'),
                models.Permission(name='view_tenant_history', description='View guest history', module='guests'),
                models.Permission(name='view_tenant_details', description='View detailed guest information', module='guests'),
                models.Permission(name='manage_tenant_services', description='Manage guest services and packages', module='guests'),
                models.Permission(name='view_tenant_payments', description='View guest payment information', module='guests'),
                models.Permission(name='create_tenant_payments', description='Create payment records for guests', module='guests'),
                models.Permission(name='edit_tenant_payments', description='Edit guest payment records', module='guests'),
                models.Permission(name='delete_tenant_payments', description='Delete guest payment records', module='guests'),
                models.Permission(name='deactivate_tenants', description='Deactivate guest accounts', module='guests'),
                
                # Check-In/Out Module
                models.Permission(name='view_checkins', description='View check-in/out records', module='checkin'),
                models.Permission(name='create_checkins', description='Process check-ins', module='checkin'),
                models.Permission(name='edit_checkins', description='Edit check-in records', module='checkin'),
                models.Permission(name='extend_stays', description='Extend guest stays', module='checkin'),
                models.Permission(name='process_checkouts', description='Process check-outs', module='checkin'),
                models.Permission(name='view_checkin_history', description='View check-in/out history', module='checkin'),
                models.Permission(name='view_active_stays', description='View currently active stays', module='checkin'),
                models.Permission(name='checkout_guests', description='Process guest checkouts', module='checkin'),
                

                
                # Inventory Management Module
                models.Permission(name='view_inventory', description='View inventory items', module='inventory'),
                models.Permission(name='create_inventory', description='Create inventory items', module='inventory'),
                models.Permission(name='edit_inventory', description='Edit inventory items', module='inventory'),
                models.Permission(name='delete_inventory', description='Delete inventory items', module='inventory'),
                models.Permission(name='manage_transactions', description='Manage inventory transactions', module='inventory'),
                models.Permission(name='view_transactions', description='View transaction history', module='inventory'),
                models.Permission(name='view_low_stock', description='View low stock alerts', module='inventory'),
                models.Permission(name='view_global_transactions', description='View all inventory transactions', module='inventory'),
                models.Permission(name='add_transactions', description='Add inventory transactions', module='inventory'),
                
                # Meal Management Module
                models.Permission(name='view_meals', description='View meal plans', module='meals'),
                models.Permission(name='create_meals', description='Create meal plans', module='meals'),
                models.Permission(name='edit_meals', description='Edit meal plans', module='meals'),
                models.Permission(name='delete_meals', description='Delete meal plans', module='meals'),
                models.Permission(name='assign_meals', description='Assign meals to guests', module='meals'),
                models.Permission(name='view_daily_meals', description='View daily meal schedules', module='meals'),
                models.Permission(name='bulk_meal_operations', description='Perform bulk meal operations', module='meals'),
                models.Permission(name='view_meal_services', description='View meal service configurations', module='meals'),
                models.Permission(name='view_guest_meal_preferences', description='View guest meal preferences', module='meals'),
                models.Permission(name='view_meal_statistics', description='View meal service statistics', module='meals'),
                models.Permission(name='add_meals', description='Add meals for guests', module='meals'),
                models.Permission(name='remove_meals', description='Remove meals from guests', module='meals'),
                models.Permission(name='bulk_add_meals', description='Bulk add meals for multiple guests', module='meals'),
                models.Permission(name='bulk_remove_meals', description='Bulk remove meals from multiple guests', module='meals'),
                models.Permission(name='view_guest_meals_api', description='Access guest meals API', module='meals'),
                
                # Financial Management Module
                models.Permission(name='view_expenses', description='View expenses', module='financial'),
                models.Permission(name='create_expenses', description='Create expense records', module='financial'),
                models.Permission(name='edit_expenses', description='Edit expense records', module='financial'),
                models.Permission(name='delete_expenses', description='Delete expense records', module='financial'),
                models.Permission(name='view_payments', description='View payment records', module='financial'),
                models.Permission(name='create_payments', description='Create payment records', module='financial'),
                models.Permission(name='edit_payments', description='Edit payment records', module='financial'),
                models.Permission(name='delete_payments', description='Delete payment records', module='financial'),
                models.Permission(name='view_income', description='View income records', module='financial'),
                models.Permission(name='create_income', description='Create income records', module='financial'),
                models.Permission(name='edit_income', description='Edit income records', module='financial'),
                models.Permission(name='delete_income', description='Delete income records', module='financial'),
                models.Permission(name='manage_payment_links', description='Manage payment links', module='financial'),
                models.Permission(name='view_payment_links', description='View payment link information', module='financial'),
                models.Permission(name='create_payment_links', description='Create payment links', module='financial'),
                models.Permission(name='edit_payment_links', description='Edit payment links', module='financial'),
                models.Permission(name='delete_payment_links', description='Delete payment links', module='financial'),
                models.Permission(name='view_financial_dashboard', description='View financial dashboard', module='financial'),
                models.Permission(name='view_revenue_analytics', description='View revenue analytics', module='financial'),
                models.Permission(name='pay_payment_links', description='Process payment link payments', module='financial'),
                models.Permission(name='process_payment_links', description='Process payment link transactions', module='financial'),
                models.Permission(name='resend_payment_links', description='Resend payment links', module='financial'),
                models.Permission(name='cancel_payment_links', description='Cancel payment links', module='financial'),
                
                # Reports Module
                models.Permission(name='view_reports', description='View basic reports', module='reports'),
                models.Permission(name='view_guest_reports', description='View guest reports', module='reports'),
                models.Permission(name='view_inventory_reports', description='View inventory reports', module='reports'),
                models.Permission(name='view_meal_reports', description='View meal service reports', module='reports'),
                models.Permission(name='export_reports', description='Export report data', module='reports'),
                models.Permission(name='export_expenses', description='Export expense reports', module='reports'),
                models.Permission(name='export_payments', description='Export payment reports', module='reports'),
                models.Permission(name='export_inventory_reports', description='Export inventory reports', module='reports'),
                
                # Audit and Security Module
                models.Permission(name='view_audit_logs', description='View audit logs', module='audit'),
                models.Permission(name='view_audit_detail', description='View detailed audit log information', module='audit'),
                
                # Financial Reports Module
                models.Permission(name='view_financial_reports', description='View financial reports', module='financial_reports'),
                models.Permission(name='view_profit_loss_reports', description='View profit and loss reports', module='financial_reports'),
                models.Permission(name='view_revenue_analysis_reports', description='View detailed revenue analysis', module='financial_reports'),
                models.Permission(name='view_expense_analysis_reports', description='View detailed expense analysis', module='financial_reports'),
                models.Permission(name='view_cash_flow_reports', description='View cash flow reports', module='financial_reports'),
                models.Permission(name='access_monthly_comparison_api', description='Access monthly comparison API', module='financial_reports'),
                
                # Employee Salaries Module
                models.Permission(name='view_employee_salaries', description='View employee salaries and information', module='employee_salaries'),
                models.Permission(name='create_employee_salaries', description='Create new employee records', module='employee_salaries'),
                models.Permission(name='edit_employee_salaries', description='Edit employee information and salary records', module='employee_salaries'),
                models.Permission(name='delete_employee_salaries', description='Delete employee records', module='employee_salaries'),
                models.Permission(name='manage_employee_salaries', description='Manage employee salary calculations and payments', module='employee_salaries'),
                models.Permission(name='export_employee_salaries', description='Export employee salary data', module='employee_salaries'),
                models.Permission(name='bulk_pay_employee_salaries', description='Process bulk salary payments', module='employee_salaries'),
                
                # Finance Suppliers Module
                models.Permission(name='view_finance_suppliers', description='View finance suppliers and transactions', module='finance_suppliers'),
                models.Permission(name='create_finance_suppliers', description='Create new finance supplier records', module='finance_suppliers'),
                models.Permission(name='edit_finance_suppliers', description='Edit finance supplier information', module='finance_suppliers'),
                models.Permission(name='delete_finance_suppliers', description='Delete finance supplier records', module='finance_suppliers'),
                models.Permission(name='manage_finance_suppliers', description='Manage finance supplier operations', module='finance_suppliers'),
                models.Permission(name='view_supplier_expenses', description='View supplier expense records', module='finance_suppliers'),
                models.Permission(name='create_supplier_expenses', description='Create supplier expense records', module='finance_suppliers'),
                models.Permission(name='edit_supplier_expenses', description='Edit supplier expense records', module='finance_suppliers'),
                models.Permission(name='delete_supplier_expenses', description='Delete supplier expense records', module='finance_suppliers'),
                models.Permission(name='view_supplier_income', description='View supplier income records', module='finance_suppliers'),
                models.Permission(name='create_supplier_income', description='Create supplier income records', module='finance_suppliers'),
                models.Permission(name='edit_supplier_income', description='Edit supplier income records', module='finance_suppliers'),
                models.Permission(name='delete_supplier_income', description='Delete supplier income records', module='finance_suppliers'),
                models.Permission(name='view_supplier_reports', description='View supplier reports', module='finance_suppliers'),
                models.Permission(name='export_supplier_data', description='Export supplier data', module='finance_suppliers')
            ]
            
            for permission in permissions:
                db.session.add(permission)
            
            # Create basic roles
            admin_role = models.Role(name='Administrator', description='Full system access')
            super_user_role = models.Role(name='Super User', description='Full system access (alternative to Administrator)')
            staff_role = models.Role(name='Staff', description='General staff access')
            frontdesk_role = models.Role(name='Front Desk', description='Front desk operations')
            
            db.session.add(admin_role)
            db.session.add(super_user_role)
            db.session.add(staff_role)
            db.session.add(frontdesk_role)
            
            db.session.flush()  # Get IDs
            
            # Assign comprehensive permissions to different roles
            # Admin role gets all permissions
            for permission in permissions:
                admin_role.permissions.append(permission)
            
            # Super User role gets all permissions (alternative to Administrator)
            for permission in permissions:
                super_user_role.permissions.append(permission)
            
            # Staff role gets operational permissions
            staff_permissions = [
                'view_dashboard', 'view_analytics', 'view_statistics', 'view_revenue_charts', 'view_occupancy_charts', 'view_chart_data',
                'view_tenants', 'create_tenants', 'edit_tenants', 'view_tenant_history', 'view_tenant_details', 'manage_tenant_services', 'deactivate_tenants',
                'view_checkins', 'create_checkins', 'edit_checkins', 'extend_stays', 'process_checkouts', 'view_checkin_history', 'view_active_stays', 'checkout_guests',

                'view_inventory', 'view_transactions', 'view_low_stock', 'view_global_transactions', 'add_transactions',
                'view_meals', 'create_meals', 'edit_meals', 'assign_meals', 'view_daily_meals', 'bulk_meal_operations', 'view_meal_services', 'view_guest_meal_preferences', 'view_meal_statistics', 'add_meals', 'remove_meals', 'bulk_add_meals', 'bulk_remove_meals', 'view_guest_meals_api',
                'view_expenses', 'create_expenses', 'edit_expenses',
                'view_payments', 'create_payments', 'edit_payments',
                'view_reports', 'view_guest_reports', 'view_inventory_reports', 'view_meal_reports', 'export_expenses', 'export_payments', 'export_inventory_reports',
                'view_audit_logs', 'view_audit_detail',
                'view_financial_reports', 'view_profit_loss_reports', 'view_revenue_analysis_reports', 'view_expense_analysis_reports', 'view_cash_flow_reports', 'access_monthly_comparison_api',
                'view_employee_salaries', 'create_employee_salaries', 'edit_employee_salaries', 'manage_employee_salaries', 'export_employee_salaries', 'bulk_pay_employee_salaries',
                'view_finance_suppliers', 'create_finance_suppliers', 'edit_finance_suppliers', 'manage_finance_suppliers', 'view_supplier_expenses', 'create_supplier_expenses', 'edit_supplier_expenses', 'view_supplier_income', 'create_supplier_income', 'edit_supplier_income', 'view_supplier_reports', 'export_supplier_data'
            ]
            for permission in permissions:
                if permission.name in staff_permissions:
                    staff_role.permissions.append(permission)
            
            # Front desk role gets guest-facing permissions
            frontdesk_permissions = [
                'view_dashboard', 'view_statistics', 'view_revenue_charts',
                'view_tenants', 'create_tenants', 'edit_tenants', 'view_tenant_history', 'view_tenant_details', 'view_tenant_payments',
                'view_checkins', 'create_checkins', 'edit_checkins', 'extend_stays', 'process_checkouts', 'view_checkin_history', 'view_active_stays',

                'view_meals', 'view_daily_meals', 'view_meal_services', 'view_guest_meal_preferences',
                'view_payments', 'create_payments', 'edit_payments',
                'view_reports', 'view_guest_reports', 'view_meal_reports'
            ]
            for permission in permissions:
                if permission.name in frontdesk_permissions:
                    frontdesk_role.permissions.append(permission)
            
            # Create additional specialized roles
            inventory_role = models.Role(name='Inventory Manager', description='Inventory management')
            financial_role = models.Role(name='Financial Manager', description='Financial operations')
            kitchen_role = models.Role(name='Kitchen Staff', description='Kitchen and meal operations')
            reception_role = models.Role(name='Reception', description='Reception and guest services')
            
            db.session.add(inventory_role)
            db.session.add(financial_role)
            db.session.add(kitchen_role)
            db.session.add(reception_role)
            
            # Inventory manager role permissions
            inventory_permissions = [
                'view_dashboard', 'view_statistics',
                'view_inventory', 'create_inventory', 'edit_inventory', 'delete_inventory',
                'manage_transactions', 'view_transactions', 'view_global_transactions',
                'view_low_stock',
                'view_inventory_reports', 'export_reports'
            ]
            for permission in permissions:
                if permission.name in inventory_permissions:
                    inventory_role.permissions.append(permission)
            
            # Financial manager role permissions
            financial_permissions = [
                'view_dashboard', 'view_analytics', 'view_statistics', 'view_revenue_charts', 'view_occupancy_charts',
                'view_expenses', 'create_expenses', 'edit_expenses', 'delete_expenses',
                'view_payments', 'create_payments', 'edit_payments', 'delete_payments',
                'view_income', 'create_income', 'edit_income', 'delete_income',
                'view_financial_reports', 'view_financial_dashboard', 'view_revenue_analytics',
                'view_reports', 'export_reports'
            ]
            for permission in permissions:
                if permission.name in financial_permissions:
                    financial_role.permissions.append(permission)
            
            # Kitchen staff role permissions
            kitchen_permissions = [
                'view_dashboard', 'view_statistics',
                'view_meals', 'create_meals', 'edit_meals', 'delete_meals', 'assign_meals', 'view_daily_meals', 'bulk_meal_operations', 'view_meal_services', 'view_guest_meal_preferences', 'view_meal_statistics',

                'view_tenant_details', 'view_tenant_history',
                'view_meal_reports'
            ]
            for permission in permissions:
                if permission.name in kitchen_permissions:
                    kitchen_role.permissions.append(permission)
            
            # Reception role permissions
            reception_permissions = [
                'view_dashboard', 'view_statistics', 'view_revenue_charts',
                'view_tenants', 'create_tenants', 'edit_tenants', 'view_tenant_history', 'view_tenant_details', 'view_tenant_payments', 'manage_tenant_services',
                'view_checkins', 'create_checkins', 'edit_checkins', 'extend_stays', 'process_checkouts', 'view_checkin_history', 'view_active_stays',

                'view_meals', 'view_daily_meals', 'view_meal_services', 'view_guest_meal_preferences',
                'view_payments', 'create_payments', 'edit_payments',
                'view_reports', 'view_guest_reports', 'view_meal_reports'
            ]
            for permission in permissions:
                if permission.name in reception_permissions:
                    reception_role.permissions.append(permission)
            
            # Make existing users administrators (for backward compatibility)
            existing_users = models.User.query.all()
            for user in existing_users:
                user.is_admin = True
                user_role = models.UserRole(user_id=user.id, role_id=admin_role.id)
                db.session.add(user_role)
            
            db.session.commit()
            print("Initial roles and permissions seeded successfully")
            
    except Exception as e:
        print(f"Error seeding initial data: {e}")
        db.session.rollback()
    
    # Create default admin user if none exists
    try:
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                email='admin@hostel.com',
                password_hash=generate_password_hash('admin123'),
                full_name='System Administrator',
                is_admin=True,
                is_active=True
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Default admin user created: admin/admin123")
    except Exception as e:
        print(f"Could not create admin user: {e}")
        db.session.rollback()

    # Seed default services if none exist
    if Service.query.count() == 0:
        default_services = [
            Service(name='Surfing', description='Surf lessons and board rental', price=50.0),
            Service(name='Other', description='Custom service specified per tenant', price=0.0),
            Service(name='Breakfast', description='Daily breakfast meal', price=30.0),
            Service(name='Dinner', description='Daily dinner meal', price=0.0),
        ]
        db.session.add_all(default_services)
        db.session.commit()
        print("Seeded default extra services")
    

    
    # Seed sample tenant services for testing meal tracking
    # Temporarily commented out for migration
    # if TenantService.query.count() == 0:
    #     # Create a sample tenant if none exists
    #     if Tenant.query.count() == 0:
    #         sample_tenant = Tenant(
    #         name='Sample Guest',
    #         room_number='1',
    #         daily_rent=25.0,
    #         start_date=date.today(),
    #         end_date=date.today() + timedelta(days=7)
    #     )
    #         db.session.add(sample_tenant)
    #         db.session.commit()
    #         print("Created sample tenant for testing")
    #     
    #     # Get the first tenant and services
    #     tenant = Tenant.query.first()
    #     breakfast_service = Service.query.filter_by(name='Breakfast').first()
    #     dinner_service = Service.query.filter_by(name='Dinner').first()
    #     
    #     if tenant and breakfast_service and dinner_service:
    #         # Add breakfast service
    #         tenant_breakfast = TenantService(
    #         tenant_id=tenant.id,
    #         service_id=breakfast_service.id,
    #         quantity=1,
    #         unit_price=30.0,
    #         start_date=date.today(),
    #         end_date=date.today() + timedelta(days=7)
    #     )
    #         
    #         # Add dinner service
    #         tenant_dinner = TenantService(
    #         tenant_id=tenant.id,
    #         service_id=dinner_service.id,
    #         quantity=1,
    #         unit_price=45.0,
    #         start_date=date.today(),
    #         end_date=date.today() + timedelta(days=7)
    #     )
    #         
    #         db.session.add_all([tenant_breakfast, tenant_dinner])
    #         db.session.commit()
    #         print("Seeded sample tenant services for meal tracking")
    #         
    #         # Create a Stay record for the tenant
    #         from models import Stay
    #         tenant_stay = Stay(
    #         tenant_id=tenant.id,
    #         stay_type='daily',
    #         daily_rate=25.0,
    #         start_date=date.today(),
    #         end_date=date.today() + timedelta(days=7),
    #         is_active=True
    #     )
    #         db.session.add(tenant_stay)
    #         db.session.commit()
    #         print("Created sample stay record for meal tracking")
    
    # Ensure Breakfast and Dinner services always exist
    # Temporarily commented out for migration
    # breakfast = Service.query.filter_by(name='Breakfast').first()
    # dinner = Service.query.filter_by(name='Dinner').first()
    # 
    # if not breakfast:
    #     breakfast_service = Service(name='Breakfast', description='Daily breakfast meal', price=30.0)
    #         db.session.add(breakfast_service)
    #         print("Added Breakfast service")
    # 
    # if not dinner:
    #         dinner_service = Service(name='Dinner', description='Daily dinner meal', price=0.0)
    #         db.session.add(dinner_service)
    #         print("Added Dinner service")
    # 
    # if not breakfast or not dinner:
    #         db.session.commit()

# Service Worker route
@app.route('/sw.js')
def service_worker():
    response = send_from_directory('.', 'sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
