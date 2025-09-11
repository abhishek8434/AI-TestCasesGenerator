#!/usr/bin/env python3
"""
Quick Admin User Creation Script
Run this once to create your admin user
"""

import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.mongo_handler import MongoHandler

def create_admin_user():
    """Create the initial admin user"""
    print("🔐 Creating Initial Admin User...")
    print("=" * 50)
    
    # Get admin details
    admin_email = input("Enter admin email: ").strip()
    admin_name = input("Enter admin name: ").strip()
    admin_password = input("Enter admin password: ").strip()
    
    if not all([admin_email, admin_name, admin_password]):
        print("❌ All fields are required!")
        return False
    
    try:
        # Initialize MongoDB handler
        mongo_handler = MongoHandler()
        
        # Create admin user
        result = mongo_handler.create_initial_admin_user(admin_email, admin_password, admin_name)
        
        if result["success"]:
            print("✅ Admin user created successfully!")
            print(f"   Email: {admin_email}")
            print(f"   Name: {admin_name}")
            print(f"   Role: admin")
            print(f"   User ID: {result['admin_user']['id']}")
            print("\n🎉 You can now log in with these credentials!")
            return True
        else:
            print(f"❌ Failed to create admin user: {result['message']}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 AI Test Case Generator - Admin Setup")
    print("=" * 50)
    
    success = create_admin_user()
    
    if success:
        print("\n✨ Setup completed successfully!")
        print("   You can now run your application and log in as admin.")
    else:
        print("\n💥 Setup failed. Please check the error messages above.")
        sys.exit(1)
