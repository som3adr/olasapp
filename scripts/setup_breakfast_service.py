#!/usr/bin/env python3
"""
Setup script to ensure breakfast service exists in the database
"""

import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from extensions import db
from models import Service

def create_app():
    """Create Flask app"""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://admin:Prefetch%4010@192.168.1.42:5432/hostel_management"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    db.init_app(app)
    return app

def setup_breakfast_service():
    """Ensure breakfast service exists in the database"""
    app = create_app()
    
    with app.app_context():
        # Check if breakfast service already exists
        breakfast_service = Service.query.filter_by(name='Breakfast').first()
        
        if breakfast_service:
            print(f"✅ Breakfast service already exists (ID: {breakfast_service.id})")
            print(f"   - Name: {breakfast_service.name}")
            print(f"   - Price: {breakfast_service.price} MAD")
            print(f"   - Meal Category: {breakfast_service.meal_category}")
            print(f"   - Active: {breakfast_service.is_active}")
            return breakfast_service
        
        # Create breakfast service if it doesn't exist
        print("🔧 Creating breakfast service...")
        
        breakfast_service = Service(
            name='Breakfast',
            description='Daily breakfast service for guests',
            price=25.0,  # Default price in MAD
            is_active=True,
            service_type='meal',
            meal_category='breakfast',
            preparation_time=30,  # 30 minutes preparation time
            is_available_today=True,
            ingredients='Bread, butter, jam, coffee, tea, juice, fruits',
            allergens='Gluten, dairy',
            dietary_restrictions='Vegetarian'
        )
        
        db.session.add(breakfast_service)
        db.session.commit()
        
        print(f"✅ Breakfast service created successfully (ID: {breakfast_service.id})")
        print(f"   - Name: {breakfast_service.name}")
        print(f"   - Price: {breakfast_service.price} MAD")
        print(f"   - Meal Category: {breakfast_service.meal_category}")
        
        return breakfast_service

def setup_dinner_service():
    """Ensure dinner service exists in the database"""
    app = create_app()
    
    with app.app_context():
        # Check if dinner service already exists
        dinner_service = Service.query.filter_by(name='Dinner').first()
        
        if dinner_service:
            print(f"✅ Dinner service already exists (ID: {dinner_service.id})")
            return dinner_service
        
        # Create dinner service if it doesn't exist
        print("🔧 Creating dinner service...")
        
        dinner_service = Service(
            name='Dinner',
            description='Daily dinner service for guests',
            price=45.0,  # Default price in MAD
            is_active=True,
            service_type='meal',
            meal_category='dinner',
            preparation_time=60,  # 60 minutes preparation time
            is_available_today=True,
            ingredients='Main course, side dish, salad, dessert',
            allergens='Various',
            dietary_restrictions='Vegetarian available'
        )
        
        db.session.add(dinner_service)
        db.session.commit()
        
        print(f"✅ Dinner service created successfully (ID: {dinner_service.id})")
        
        return dinner_service

def main():
    """Main setup function"""
    print("🍳 Setting up meal services for breakfast auto-generator...")
    print("=" * 60)
    
    # Setup breakfast service
    breakfast_service = setup_breakfast_service()
    print()
    
    # Setup dinner service (for completeness)
    dinner_service = setup_dinner_service()
    print()
    
    print("🎉 Setup completed successfully!")
    print("=" * 60)
    print("You can now use the breakfast auto-generator at:")
    print("http://localhost:5000/breakfast-auto/")

if __name__ == '__main__':
    main()
