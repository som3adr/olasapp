#!/usr/bin/env python3
"""
Add already_paid_online field to Tenant table
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from extensions import db
from sqlalchemy import text

def add_already_paid_online_field():
    """Add already_paid_online field to Tenant table"""
    
    with app.app_context():
        try:
            print("=== Adding already_paid_online field to Tenant table ===")
            
            # Check if column already exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'tenant' 
                AND column_name = 'already_paid_online'
            """)).fetchone()
            
            if result:
                print("✅ Column 'already_paid_online' already exists in Tenant table")
                return True
            
            # Add the column
            print("📝 Adding already_paid_online column...")
            db.session.execute(text("""
                ALTER TABLE tenant 
                ADD COLUMN already_paid_online BOOLEAN DEFAULT FALSE
            """))
            
            db.session.commit()
            print("✅ Successfully added already_paid_online field to Tenant table")
            
            # Verify the column was added
            result = db.session.execute(text("""
                SELECT column_name, data_type, column_default
                FROM information_schema.columns 
                WHERE table_name = 'tenant' 
                AND column_name = 'already_paid_online'
            """)).fetchone()
            
            if result:
                print(f"✅ Verification successful:")
                print(f"   Column: {result[0]}")
                print(f"   Type: {result[1]}")
                print(f"   Default: {result[2]}")
                return True
            else:
                print("❌ Column was not added successfully")
                return False
                
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error: {str(e)}")
            return False

if __name__ == '__main__':
    success = add_already_paid_online_field()
    if success:
        print("\n🎉 Database migration completed successfully!")
        print("🌐 You can now use the 'Already Paid Online' feature")
    else:
        print("\n❌ Database migration failed!")
