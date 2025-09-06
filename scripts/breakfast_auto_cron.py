#!/usr/bin/env python3
"""
Automated Breakfast Order Generation Cron Job
This script can be run daily to automatically generate breakfast orders for guests
"""

import os
import sys
import logging
from datetime import date, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from extensions import db
from models import Tenant, TenantService, Service, RestaurantOrder
from sqlalchemy import and_

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/breakfast_auto_cron.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_app():
    """Create Flask app for cron job"""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://admin:Prefetch%4010@192.168.1.42:5432/hostel_management"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    db.init_app(app)
    return app

def generate_breakfast_orders_for_date(target_date):
    """
    Generate breakfast orders for a specific date
    
    Args:
        target_date (date): Date to generate orders for
        
    Returns:
        dict: Results of the generation process
    """
    results = {
        'date': target_date.isoformat(),
        'total_guests_processed': 0,
        'total_orders_generated': 0,
        'successful_guests': [],
        'failed_guests': []
    }
    
    # Get breakfast service
    breakfast_service = Service.query.filter_by(
        name='Breakfast',
        meal_category='breakfast',
        is_active=True
    ).first()
    
    if not breakfast_service:
        logger.error("Breakfast service not found in database")
        return results
    
    # Get all active tenants with breakfast services
    tenants_with_breakfast = Tenant.query.join(TenantService).filter(
        and_(
            Tenant.is_active == True,
            TenantService.service_id == breakfast_service.id,
            TenantService.quantity > 0
        )
    ).distinct().all()
    
    results['total_guests_processed'] = len(tenants_with_breakfast)
    
    for tenant in tenants_with_breakfast:
        try:
            # Get tenant's breakfast service details
            breakfast_service_detail = TenantService.query.filter_by(
                tenant_id=tenant.id,
                service_id=breakfast_service.id
            ).first()
            
            if not breakfast_service_detail:
                results['failed_guests'].append({
                    'guest_name': tenant.name,
                    'guest_id': tenant.id,
                    'error': 'No breakfast service details found'
                })
                continue
            
            # Determine the date range for the service
            service_start = breakfast_service_detail.start_date or tenant.start_date
            service_end = breakfast_service_detail.end_date or tenant.end_date
            
            if not service_start or not service_end:
                results['failed_guests'].append({
                    'guest_name': tenant.name,
                    'guest_id': tenant.id,
                    'error': 'Invalid service date range'
                })
                continue
            
            # Check if target date falls within the service period
            if not (service_start <= target_date <= service_end):
                results['failed_guests'].append({
                    'guest_name': tenant.name,
                    'guest_id': tenant.id,
                    'error': f'Target date {target_date} not within service period'
                })
                continue
            
            # Check for existing orders to prevent duplicates
            existing_order = RestaurantOrder.query.filter_by(
                tenant_id=tenant.id,
                service_id=breakfast_service.id,
                order_date=target_date,
                meal_time='breakfast'
            ).first()
            
            if existing_order:
                results['failed_guests'].append({
                    'guest_name': tenant.name,
                    'guest_id': tenant.id,
                    'error': f'Order already exists for {target_date}'
                })
                continue
            
            # Create the restaurant order
            order = RestaurantOrder(
                tenant_id=tenant.id,
                service_id=breakfast_service.id,
                order_date=target_date,
                meal_time='breakfast',
                quantity=tenant.number_of_guests,
                special_requests=f'Auto-generated for {tenant.name} (Cron Job)',
                status='pending',
                created_by=1  # System user ID (you may need to adjust this)
            )
            
            db.session.add(order)
            db.session.commit()
            
            results['total_orders_generated'] += 1
            results['successful_guests'].append({
                'guest_name': tenant.name,
                'guest_id': tenant.id,
                'order_id': order.id
            })
            
            logger.info(f"Generated breakfast order for {tenant.name} on {target_date}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error generating breakfast order for {tenant.name}: {str(e)}")
            results['failed_guests'].append({
                'guest_name': tenant.name,
                'guest_id': tenant.id,
                'error': f'Database error: {str(e)}'
            })
    
    return results

def main():
    """Main function for cron job"""
    app = create_app()
    
    with app.app_context():
        # Generate orders for today
        today = date.today()
        logger.info(f"Starting breakfast order generation for {today}")
        
        results = generate_breakfast_orders_for_date(today)
        
        # Log results
        logger.info(f"Generation completed for {today}")
        logger.info(f"Total guests processed: {results['total_guests_processed']}")
        logger.info(f"Total orders generated: {results['total_orders_generated']}")
        logger.info(f"Successful guests: {len(results['successful_guests'])}")
        logger.info(f"Failed guests: {len(results['failed_guests'])}")
        
        # Log failed guests
        if results['failed_guests']:
            logger.warning("Failed guests:")
            for failed in results['failed_guests']:
                logger.warning(f"  - {failed['guest_name']}: {failed['error']}")
        
        # Log successful guests
        if results['successful_guests']:
            logger.info("Successful guests:")
            for success in results['successful_guests']:
                logger.info(f"  - {success['guest_name']} (Order ID: {success['order_id']})")

if __name__ == '__main__':
    main()
