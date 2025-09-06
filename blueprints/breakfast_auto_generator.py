"""
Automated Breakfast Order Generation System
Generates breakfast orders for guests with breakfast included in their bookings
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import Tenant, TenantService, Service, RestaurantOrder, DailyMealService, db
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_
import logging

breakfast_auto_bp = Blueprint('breakfast_auto', __name__, url_prefix='/breakfast-auto')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BreakfastOrderGenerator:
    """Handles automatic generation of breakfast orders for guests"""
    
    def __init__(self):
        self.breakfast_service = None
        self._load_breakfast_service()
    
    def _load_breakfast_service(self):
        """Load the breakfast service from database"""
        self.breakfast_service = Service.query.filter_by(
            name='Breakfast',
            meal_category='breakfast',
            is_active=True
        ).first()
        
        if not self.breakfast_service:
            logger.warning("Breakfast service not found in database")
    
    def get_guests_with_breakfast(self, start_date=None, end_date=None):
        """
        Retrieve all guests with breakfast included in their booking
        
        Args:
            start_date (date): Filter guests by booking start date
            end_date (date): Filter guests by booking end date
            
        Returns:
            list: List of tenant objects with breakfast services
        """
        if not self.breakfast_service:
            return []
        
        # Base query for tenants with breakfast services
        query = Tenant.query.join(TenantService).filter(
            and_(
                Tenant.is_active == True,
                TenantService.service_id == self.breakfast_service.id,
                TenantService.quantity > 0
            )
        )
        
        # Apply date filters if provided
        if start_date:
            query = query.filter(Tenant.start_date <= end_date or date.today())
        if end_date:
            query = query.filter(Tenant.end_date >= start_date or date.today())
        
        return query.distinct().all()
    
    def calculate_breakfast_days(self, tenant):
        """
        Calculate the number of breakfast days for a tenant
        
        Args:
            tenant (Tenant): Tenant object
            
        Returns:
            int: Number of breakfast days
        """
        if not self.breakfast_service:
            return 0
        
        # Get the tenant's breakfast service
        breakfast_service = TenantService.query.filter_by(
            tenant_id=tenant.id,
            service_id=self.breakfast_service.id
        ).first()
        
        if not breakfast_service:
            return 0
        
        # Calculate days based on service period
        service_start = breakfast_service.start_date or tenant.start_date
        service_end = breakfast_service.end_date or tenant.end_date
        
        if not service_start or not service_end:
            return 0
        
        return (service_end - service_start).days + 1
    
    def generate_breakfast_orders(self, tenant, target_date=None, preview_mode=False):
        """
        Generate breakfast orders for a specific tenant
        
        Args:
            tenant (Tenant): Tenant object
            target_date (date): Specific date to generate orders for (default: today)
            preview_mode (bool): If True, don't save to database
            
        Returns:
            dict: Generation results with success/error information
        """
        if not self.breakfast_service:
            return {
                'success': False,
                'error': 'Breakfast service not found',
                'orders_generated': 0
            }
        
        if target_date is None:
            target_date = date.today()
        
        # Get tenant's breakfast service details
        breakfast_service = TenantService.query.filter_by(
            tenant_id=tenant.id,
            service_id=self.breakfast_service.id
        ).first()
        
        if not breakfast_service:
            return {
                'success': False,
                'error': f'No breakfast service found for guest {tenant.name}',
                'orders_generated': 0
            }
        
        # Determine the date range for order generation
        service_start = breakfast_service.start_date or tenant.start_date
        service_end = breakfast_service.end_date or tenant.end_date
        
        if not service_start or not service_end:
            return {
                'success': False,
                'error': f'Invalid date range for guest {tenant.name}',
                'orders_generated': 0
            }
        
        # Check if target date falls within the service period
        if not (service_start <= target_date <= service_end):
            return {
                'success': False,
                'error': f'Target date {target_date} not within service period for {tenant.name}',
                'orders_generated': 0
            }
        
        # Check for existing orders to prevent duplicates
        existing_order = RestaurantOrder.query.filter_by(
            tenant_id=tenant.id,
            service_id=self.breakfast_service.id,
            order_date=target_date,
            meal_time='breakfast'
        ).first()
        
        if existing_order:
            return {
                'success': False,
                'error': f'Breakfast order already exists for {tenant.name} on {target_date}',
                'orders_generated': 0
            }
        
        # Calculate quantity (considering number of guests)
        quantity = tenant.number_of_guests
        
        if preview_mode:
            return {
                'success': True,
                'preview': True,
                'orders_generated': 1,
                'order_details': {
                    'tenant_name': tenant.name,
                    'tenant_id': tenant.id,
                    'order_date': target_date,
                    'quantity': quantity,
                    'service_name': self.breakfast_service.name,
                    'unit_price': self.breakfast_service.price
                }
            }
        
        # Create the restaurant order
        try:
            order = RestaurantOrder(
                tenant_id=tenant.id,
                service_id=self.breakfast_service.id,
                order_date=target_date,
                meal_time='breakfast',
                quantity=quantity,
                special_requests=f'Auto-generated for {tenant.name}',
                status='pending',
                created_by=current_user.id
            )
            
            db.session.add(order)
            db.session.commit()
            
            logger.info(f"Generated breakfast order for {tenant.name} on {target_date}")
            
            return {
                'success': True,
                'orders_generated': 1,
                'order_id': order.id
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error generating breakfast order for {tenant.name}: {str(e)}")
            return {
                'success': False,
                'error': f'Database error: {str(e)}',
                'orders_generated': 0
            }
    
    def generate_orders_for_date_range(self, start_date, end_date, preview_mode=False):
        """
        Generate breakfast orders for all eligible guests in a date range
        
        Args:
            start_date (date): Start date for order generation
            end_date (date): End date for order generation
            preview_mode (bool): If True, don't save to database
            
        Returns:
            dict: Summary of generation results
        """
        results = {
            'total_guests_processed': 0,
            'total_orders_generated': 0,
            'successful_guests': [],
            'failed_guests': [],
            'preview_orders': [] if preview_mode else None
        }
        
        # Get all guests with breakfast services
        guests = self.get_guests_with_breakfast(start_date, end_date)
        results['total_guests_processed'] = len(guests)
        
        # Generate orders for each day in the range
        current_date = start_date
        while current_date <= end_date:
            for guest in guests:
                result = self.generate_breakfast_orders(
                    guest, 
                    current_date, 
                    preview_mode=preview_mode
                )
                
                if result['success']:
                    results['total_orders_generated'] += result['orders_generated']
                    results['successful_guests'].append({
                        'guest_name': guest.name,
                        'guest_id': guest.id,
                        'date': current_date,
                        'order_id': result.get('order_id'),
                        'order_details': result.get('order_details')
                    })
                else:
                    results['failed_guests'].append({
                        'guest_name': guest.name,
                        'guest_id': guest.id,
                        'date': current_date,
                        'error': result['error']
                    })
            
            current_date += timedelta(days=1)
        
        return results

# Initialize the generator (will be created when needed)
generator = None

def get_generator():
    """Get or create the breakfast order generator"""
    global generator
    if generator is None:
        generator = BreakfastOrderGenerator()
    return generator

@breakfast_auto_bp.route('/')
@login_required
def index():
    """Main interface for breakfast order auto-generation"""
    # Get today's date and next 7 days for preview
    today = date.today()
    next_week = today + timedelta(days=7)
    
    # Get guests with breakfast services
    gen = get_generator()
    guests_with_breakfast = gen.get_guests_with_breakfast(today, next_week)
    
    # Get existing orders for the next week
    existing_orders = RestaurantOrder.query.join(Service).filter(
        and_(
            RestaurantOrder.order_date >= today,
            RestaurantOrder.order_date <= next_week,
            Service.meal_category == 'breakfast'
        )
    ).all()
    
    return render_template('breakfast_auto/index.html',
                         guests_with_breakfast=guests_with_breakfast,
                         existing_orders=existing_orders,
                         today=today,
                         next_week=next_week)

@breakfast_auto_bp.route('/preview', methods=['POST'])
@login_required
def preview_orders():
    """Preview breakfast orders that would be generated"""
    try:
        start_date = datetime.strptime(request.json.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.json.get('end_date'), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date format'}), 400
    
    # Generate preview
    gen = get_generator()
    results = gen.generate_orders_for_date_range(
        start_date, 
        end_date, 
        preview_mode=True
    )
    
    return jsonify(results)

@breakfast_auto_bp.route('/generate', methods=['POST'])
@login_required
def generate_orders():
    """Generate breakfast orders for the specified date range"""
    try:
        start_date = datetime.strptime(request.json.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.json.get('end_date'), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date format'}), 400
    
    # Generate orders
    gen = get_generator()
    results = gen.generate_orders_for_date_range(
        start_date, 
        end_date, 
        preview_mode=False
    )
    
    # Log the generation
    logger.info(f"Generated {results['total_orders_generated']} breakfast orders "
               f"for {results['total_guests_processed']} guests "
               f"from {start_date} to {end_date}")
    
    return jsonify(results)

@breakfast_auto_bp.route('/generate-today', methods=['POST'])
@login_required
def generate_today():
    """Quick generate orders for today only"""
    today = date.today()
    gen = get_generator()
    results = gen.generate_orders_for_date_range(
        today, 
        today, 
        preview_mode=False
    )
    
    if results['total_orders_generated'] > 0:
        flash(f"Generated {results['total_orders_generated']} breakfast orders for today!", 'success')
    else:
        flash("No new breakfast orders generated for today.", 'info')
    
    return redirect(url_for('breakfast_auto.index'))

@breakfast_auto_bp.route('/generate-week', methods=['POST'])
@login_required
def generate_week():
    """Generate orders for the next 7 days"""
    today = date.today()
    next_week = today + timedelta(days=7)
    
    gen = get_generator()
    results = gen.generate_orders_for_date_range(
        today, 
        next_week, 
        preview_mode=False
    )
    
    if results['total_orders_generated'] > 0:
        flash(f"Generated {results['total_orders_generated']} breakfast orders for the next 7 days!", 'success')
    else:
        flash("No new breakfast orders generated for the next 7 days.", 'info')
    
    return redirect(url_for('breakfast_auto.index'))

@breakfast_auto_bp.route('/api/guest-breakfast-status/<int:guest_id>')
@login_required
def guest_breakfast_status(guest_id):
    """API endpoint to get breakfast status for a specific guest"""
    guest = Tenant.query.get_or_404(guest_id)
    
    gen = get_generator()
    if not gen.breakfast_service:
        return jsonify({'error': 'Breakfast service not available'}), 500
    
    # Get breakfast service details
    breakfast_service = TenantService.query.filter_by(
        tenant_id=guest.id,
        service_id=gen.breakfast_service.id
    ).first()
    
    if not breakfast_service:
        return jsonify({
            'has_breakfast': False,
            'message': 'No breakfast service assigned'
        })
    
    # Get existing orders for the next 7 days
    today = date.today()
    next_week = today + timedelta(days=7)
    
    existing_orders = RestaurantOrder.query.filter(
        and_(
            RestaurantOrder.tenant_id == guest.id,
            RestaurantOrder.service_id == gen.breakfast_service.id,
            RestaurantOrder.order_date >= today,
            RestaurantOrder.order_date <= next_week
        )
    ).all()
    
    return jsonify({
        'has_breakfast': True,
        'service_details': {
            'quantity': breakfast_service.quantity,
            'start_date': breakfast_service.start_date.isoformat() if breakfast_service.start_date else None,
            'end_date': breakfast_service.end_date.isoformat() if breakfast_service.end_date else None,
            'unit_price': breakfast_service.unit_price
        },
        'existing_orders': [
            {
                'order_date': order.order_date.isoformat(),
                'quantity': order.quantity,
                'status': order.status
            } for order in existing_orders
        ]
    })
