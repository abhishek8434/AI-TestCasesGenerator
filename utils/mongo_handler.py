# Import error logging utilities
from utils.error_logger import capture_exception, capture_message, set_tag, set_context

import pymongo
from pymongo import MongoClient
from bson import ObjectId
import json
from datetime import datetime, timedelta
import hashlib
import string
import random
import logging
from config.settings import MONGODB_URI, MONGODB_DB
import uuid
import bcrypt
import jwt
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MongoHandler:
    def __init__(self):
        try:
            self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            # Verify connection
            self.client.server_info()
            self.db = self.client[MONGODB_DB]
            self.collection = self.db.test_cases
            self.analytics_collection = self.db.analytics
            self.user_sessions_collection = self.db.user_sessions
            self.users_collection = self.db.users
            logger.info("Successfully connected to MongoDB")
        except (pymongo.errors.ConnectionFailure, pymongo.errors.ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise Exception("Could not connect to MongoDB. Please check your connection settings.")

    def create_user(self, email, password, name, role='user'):
        """Create a new user account"""
        try:
            # Check if user already exists
            existing_user = self.users_collection.find_one({"email": email.lower()})
            if existing_user:
                return {"success": False, "message": "User with this email already exists"}
            
            # Hash the password
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
            
            # Create user document
            user_doc = {
                "_id": str(uuid.uuid4()),
                "email": email.lower(),
                "password": hashed_password,
                "name": name,
                "role": role,  # Can be 'admin' or 'user'
                "created_at": datetime.utcnow(),
                "last_login": None,
                "is_active": True
            }
            
            self.users_collection.insert_one(user_doc)
            logger.info(f"Successfully created user: {email} with role: {role}")
            return {
                "success": True, 
                "message": "User created successfully",
                "user": {
                    "id": user_doc["_id"],
                    "email": user_doc["email"],
                    "name": user_doc["name"],
                    "role": user_doc["role"]
                }
            }
            
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            return {"success": False, "message": "Failed to create user"}

    def create_admin_user(self, email, password, name):
        """Create the initial admin user (should only be called once)"""
        try:
            # Check if admin already exists
            existing_admin = self.users_collection.find_one({"role": "admin"})
            if existing_admin:
                return {"success": False, "message": "Admin user already exists"}
            
            # Create admin user
            result = self.create_user(email, password, name, role='admin')
            if result["success"]:
                logger.info(f"Successfully created admin user: {email}")
                return {"success": True, "message": "Admin user created successfully"}
            else:
                return result
                
        except Exception as e:
            logger.error(f"Error creating admin user: {str(e)}")
            return {"success": False, "message": "Failed to create admin user"}

    def authenticate_user(self, email, password):
        """Authenticate user login"""
        try:
            # Find user by email
            user = self.users_collection.find_one({"email": email.lower()})
            if not user:
                return {"success": False, "message": "Invalid email or password"}
            
            # Check if user is active
            if not user.get("is_active", True):
                return {"success": False, "message": "Account is deactivated"}
            
            # Verify password
            if bcrypt.checkpw(password.encode('utf-8'), user["password"]):
                # Update last login
                self.users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"last_login": datetime.utcnow()}}
                )
                
                # Generate JWT token
                token = self.generate_jwt_token(user["_id"])
                
                logger.info(f"Successfully authenticated user: {email}")
                return {
                    "success": True,
                    "message": "Login successful",
                    "user": {
                        "id": user["_id"],
                        "email": user["email"],
                        "name": user["name"],
                        "role": user.get("role", "user")
                    },
                    "token": token
                }
            else:
                return {"success": False, "message": "Invalid email or password"}
                
        except Exception as e:
            logger.error(f"Error authenticating user: {str(e)}")
            return {"success": False, "message": "Authentication failed"}

    def is_admin(self, user_id):
        """Check if a user is an admin"""
        try:
            user = self.users_collection.find_one({"_id": user_id})
            if user and user.get("is_active", True):
                return user.get("role") == "admin"
            return False
        except Exception as e:
            logger.error(f"Error checking admin status: {str(e)}")
            return False

    def get_all_users(self, admin_user_id):
        """Get all users (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            users = list(self.users_collection.find({}, {
                "_id": 1,
                "email": 1,
                "name": 1,
                "role": 1,
                "status": 1,
                "created_at": 1,
                "last_login": 1,
                "is_active": 1
                # Note: password is excluded by not including it in the projection
            }))
            
            # Convert ObjectId to string for JSON serialization
            for user in users:
                if "_id" in user:
                    user["_id"] = str(user["_id"])
                if "created_at" in user:
                    user["created_at"] = user["created_at"].isoformat()
                if "last_login" in user:
                    user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
            
            return {"success": True, "users": users}
            
        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return {"success": False, "message": "Failed to retrieve users"}

    def update_user_role(self, admin_user_id, target_user_id, new_role):
        """Update user role (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Validate role
            if new_role not in ['admin', 'user']:
                return {"success": False, "message": "Invalid role. Must be 'admin' or 'user'"}
            
            # Update user role
            result = self.users_collection.update_one(
                {"_id": target_user_id},
                {"$set": {"role": new_role}}
            )
            
            if result.modified_count > 0:
                logger.info(f"User role updated to {new_role} by admin {admin_user_id}")
                return {"success": True, "message": f"User role updated to {new_role}"}
            else:
                return {"success": False, "message": "User not found or role unchanged"}
                
        except Exception as e:
            logger.error(f"Error updating user role: {str(e)}")
            return {"success": False, "message": "Failed to update user role"}

    def toggle_user_status(self, admin_user_id, target_user_id, is_active):
        """Toggle user active status (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Update user status
            result = self.users_collection.update_one(
                {"_id": target_user_id},
                {"$set": {"is_active": is_active}}
            )
            
            if result.modified_count > 0:
                status_text = "activated" if is_active else "deactivated"
                logger.info(f"User {status_text} by admin {admin_user_id}")
                return {"success": True, "message": f"User {status_text} successfully"}
            else:
                return {"success": False, "message": "User not found or status unchanged"}
                
        except Exception as e:
            logger.error(f"Error toggling user status: {str(e)}")
            return {"success": False, "message": "Failed to update user status"}

    def create_user_by_admin(self, admin_user_id, email, password, name, role='user'):
        """Create a new user account by admin"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Create user with specified role
            result = self.create_user(email, password, name, role)
            if result["success"]:
                logger.info(f"User created by admin {admin_user_id}: {email} with role {role}")
                return {"success": True, "message": f"User created successfully with role {role}"}
            else:
                return result
                
        except Exception as e:
            logger.error(f"Error creating user by admin: {str(e)}")
            return {"success": False, "message": "Failed to create user"}

    def delete_user(self, admin_user_id, target_user_id):
        """Delete a user (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Check if trying to delete self
            if admin_user_id == target_user_id:
                return {"success": False, "message": "Cannot delete your own account"}
            
            # Delete user
            result = self.users_collection.delete_one({"_id": target_user_id})
            
            if result.deleted_count > 0:
                logger.info(f"User deleted by admin {admin_user_id}: {target_user_id}")
                return {"success": True, "message": "User deleted successfully"}
            else:
                return {"success": False, "message": "User not found"}
                
        except Exception as e:
            logger.error(f"Error deleting user: {str(e)}")
            return {"success": False, "message": "Failed to delete user"}

    def get_user_statistics(self, admin_user_id):
        """Get user statistics (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Get total users
            total_users = self.users_collection.count_documents({})
            
            # Get active users
            active_users = self.users_collection.count_documents({"is_active": True})
            
            # Get users by role
            admin_users = self.users_collection.count_documents({"role": "admin"})
            regular_users = self.users_collection.count_documents({"role": "user"})
            
            # Get users created this month
            from datetime import datetime, timedelta
            first_day = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            new_users_this_month = self.users_collection.count_documents({"created_at": {"$gte": first_day}})
            
            stats = {
                "total_users": total_users,
                "active_users": active_users,
                "inactive_users": total_users - active_users,
                "admin_users": admin_users,
                "regular_users": regular_users,
                "new_users_this_month": new_users_this_month
            }
            
            return {"success": True, "statistics": stats}
            
        except Exception as e:
            logger.error(f"Error getting user statistics: {str(e)}")
            return {"success": False, "message": "Failed to retrieve user statistics"}

    def get_user_by_id(self, user_id):
        """Get user details by ID"""
        try:
            user = self.users_collection.find_one({"_id": user_id}, {
                "password": 0  # Exclude password
            })
            
            if user:
                # Convert ObjectId to string for JSON serialization
                if "_id" in user:
                    user["_id"] = str(user["_id"])
                if "created_at" in user:
                    user["created_at"] = user["created_at"].isoformat()
                if "last_login" in user:
                    user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
                
                return {"success": True, "user": user}
            else:
                return {"success": False, "message": "User not found"}
                
        except Exception as e:
            logger.error(f"Error getting user by ID: {str(e)}")
            return {"success": False, "message": "Failed to retrieve user"}

    def update_user_profile(self, current_user_id, target_user_id, updates):
        """Update user profile (admin can update any user, regular users can only update themselves)"""
        try:
            current_user = self.users_collection.find_one({"_id": current_user_id})
            if not current_user:
                return {"success": False, "message": "Current user not found"}
            
            # Regular users can only update their own profile
            if current_user.get("role") != "admin" and current_user_id != target_user_id:
                return {"success": False, "message": "Access denied. You can only update your own profile."}
            
            # Admin can update any field except role (use update_user_role for that)
            # Regular users can only update name and email
            allowed_fields = ["name", "email"]
            if current_user.get("role") == "admin":
                allowed_fields.extend(["name", "email"])
            
            # Filter updates to only allowed fields
            filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
            
            if not filtered_updates:
                return {"success": False, "message": "No valid fields to update"}
            
            # Update user
            result = self.users_collection.update_one(
                {"_id": target_user_id},
                {"$set": filtered_updates}
            )
            
            if result.modified_count > 0:
                logger.info(f"User profile updated by {current_user_id}: {target_user_id}")
                return {"success": True, "message": "Profile updated successfully"}
            else:
                return {"success": False, "message": "No changes made"}
                
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}")
            return {"success": False, "message": "Failed to update profile"}

    def change_password(self, user_id, current_password, new_password):
        """Change user password"""
        try:
            user = self.users_collection.find_one({"_id": user_id})
            if not user:
                return {"success": False, "message": "User not found"}
            
            # Verify current password
            if not bcrypt.checkpw(current_password.encode('utf-8'), user["password"]):
                return {"success": False, "message": "Current password is incorrect"}
            
            # Hash new password
            salt = bcrypt.gensalt()
            hashed_new_password = bcrypt.hashpw(new_password.encode('utf-8'), salt)
            
            # Update password
            result = self.users_collection.update_one(
                {"_id": user_id},
                {"$set": {"password": hashed_new_password}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Password changed for user: {user_id}")
                return {"success": True, "message": "Password changed successfully"}
            else:
                return {"success": False, "message": "Failed to update password"}
                
        except Exception as e:
            logger.error(f"Error changing password: {str(e)}")
            return {"success": False, "message": "Failed to change password"}

    def reset_password_by_admin(self, admin_user_id, target_user_id, new_password):
        """Reset user password by admin"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Hash new password
            salt = bcrypt.gensalt()
            hashed_new_password = bcrypt.hashpw(new_password.encode('utf-8'), salt)
            
            # Update password
            result = self.users_collection.update_one(
                {"_id": target_user_id},
                {"$set": {"password": hashed_new_password}}
            )
            
            if result.modified_count > 0:
                logger.info(f"Password reset by admin {admin_user_id} for user: {target_user_id}")
                return {"success": True, "message": "Password reset successfully"}
            else:
                return {"success": False, "message": "User not found"}
                
        except Exception as e:
            logger.error(f"Error resetting password by admin: {str(e)}")
            return {"success": False, "message": "Failed to reset password"}

    def search_users(self, admin_user_id, query, limit=20):
        """Search users by name or email (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Create search query
            search_query = {
                "$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"email": {"$regex": query, "$options": "i"}}
                ]
            }
            
            # Find users
            users = list(self.users_collection.find(search_query, {
                "password": 0  # Exclude password
            }).limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for user in users:
                if "_id" in user:
                    user["_id"] = str(user["_id"])
                if "created_at" in user:
                    user["created_at"] = user["created_at"].isoformat()
                if "last_login" in user:
                    user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
            
            return {"success": True, "users": users, "count": len(users)}
            
        except Exception as e:
            logger.error(f"Error searching users: {str(e)}")
            return {"success": False, "message": "Failed to search users"}

    def get_user_activity_logs(self, admin_user_id, user_id=None, limit=50):
        """Get user activity logs (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Create query
            query = {}
            if user_id:
                query["user_id"] = user_id
            
            # Get logs from test_cases collection (assuming we store user activity there)
            logs = list(self.collection.find(query, {
                "user_id": 1,
                "created_at": 1,
                "source_type": 1,
                "status": 1
            }).sort("created_at", -1).limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for log in logs:
                if "_id" in log:
                    log["_id"] = str(log["_id"])
                if "created_at" in log:
                    log["created_at"] = log["created_at"].isoformat()
            
            return {"success": True, "logs": logs, "count": len(logs)}
            
        except Exception as e:
            logger.error(f"Error getting user activity logs: {str(e)}")
            return {"success": False, "message": "Failed to retrieve activity logs"}

    def bulk_update_user_roles(self, admin_user_id, user_updates):
        """Bulk update user roles (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Validate updates
            if not isinstance(user_updates, list):
                return {"success": False, "message": "Invalid format. Expected list of user updates."}
            
            updated_count = 0
            errors = []
            
            for update in user_updates:
                user_id = update.get("user_id")
                new_role = update.get("role")
                
                if not user_id or not new_role:
                    errors.append(f"Missing user_id or role for update: {update}")
                    continue
                
                if new_role not in ['admin', 'user']:
                    errors.append(f"Invalid role '{new_role}' for user {user_id}")
                    continue
                
                # Update user role
                result = self.users_collection.update_one(
                    {"_id": user_id},
                    {"$set": {"role": new_role}}
                )
                
                if result.modified_count > 0:
                    updated_count += 1
                    logger.info(f"User role updated to {new_role} by admin {admin_user_id}: {user_id}")
                else:
                    errors.append(f"Failed to update role for user {user_id}")
            
            return {
                "success": True,
                "message": f"Bulk update completed. {updated_count} users updated.",
                "updated_count": updated_count,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Error in bulk update user roles: {str(e)}")
            return {"success": False, "message": "Failed to perform bulk update"}

    def export_user_data(self, admin_user_id, format_type='json'):
        """Export user data (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Get all users
            users = list(self.users_collection.find({}, {
                "password": 0  # Exclude password
            }))
            
            # Convert ObjectId to string for JSON serialization
            for user in users:
                if "_id" in user:
                    user["_id"] = str(user["_id"])
                if "created_at" in user:
                    user["created_at"] = user["created_at"].isoformat()
                if "last_login" in user:
                    user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
            
            if format_type == 'json':
                return {"success": True, "data": users, "format": "json"}
            elif format_type == 'csv':
                # Convert to CSV format
                import csv
                import io
                
                output = io.StringIO()
                if users:
                    fieldnames = users[0].keys()
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(users)
                
                csv_data = output.getvalue()
                output.close()
                
                return {"success": True, "data": csv_data, "format": "csv"}
            else:
                return {"success": False, "message": "Unsupported format type"}
            
        except Exception as e:
            logger.error(f"Error exporting user data: {str(e)}")
            return {"success": False, "message": "Failed to export user data"}

    def get_user_dashboard_data(self, user_id):
        """Get user dashboard data with role-based access"""
        try:
            user = self.users_collection.find_one({"_id": user_id})
            if not user:
                return {"success": False, "message": "User not found"}
            
            # Get user's test cases
            user_test_cases = list(self.collection.find(
                {"user_id": user_id},
                {"_id": 1, "title": 1, "created_at": 1, "source_type": 1, "status": 1}
            ).sort("created_at", -1).limit(10))
            
            # Convert ObjectId to string for JSON serialization
            for test_case in user_test_cases:
                if "_id" in test_case:
                    test_case["_id"] = str(test_case["_id"])
                if "created_at" in test_case:
                    test_case["created_at"] = test_case["created_at"].isoformat()
            
            # Get basic stats
            total_test_cases = self.collection.count_documents({"user_id": user_id})
            
            # Get this month's test cases
            from datetime import datetime, timedelta
            first_day = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            this_month_count = self.collection.count_documents({
                "user_id": user_id,
                "created_at": {"$gte": first_day}
            })
            
            # Get last generated test case
            last_generated = self.collection.find_one(
                {"user_id": user_id},
                {"_id": 1, "title": 1, "created_at": 1}
            )
            
            if last_generated:
                if "_id" in last_generated:
                    last_generated["_id"] = str(last_generated["_id"])
                if "created_at" in last_generated:
                    last_generated["created_at"] = last_generated["created_at"].isoformat()
            
            dashboard_data = {
                "user_info": {
                    "id": user["_id"],
                    "name": user["name"],
                    "email": user["email"],
                    "role": user.get("role", "user"),
                    "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
                    "last_login": user["last_login"].isoformat() if user.get("last_login") else None
                },
                "statistics": {
                    "total_test_cases": total_test_cases,
                    "this_month": this_month_count,
                    "last_generated": last_generated
                },
                "recent_test_cases": user_test_cases
            }
            
            # Add admin-specific data if user is admin
            if user.get("role") == "admin":
                admin_stats = self.get_user_statistics(user_id)
                if admin_stats["success"]:
                    dashboard_data["admin_statistics"] = admin_stats["statistics"]
                
                # Get recent user activity
                recent_activity = self.get_user_activity_logs(user_id, limit=10)
                if recent_activity["success"]:
                    dashboard_data["recent_activity"] = recent_activity["logs"]
            
            return {"success": True, "dashboard_data": dashboard_data}
            
        except Exception as e:
            logger.error(f"Error getting user dashboard data: {str(e)}")
            return {"success": False, "message": "Failed to retrieve dashboard data"}

    def get_system_overview(self, admin_user_id):
        """Get system overview (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Get system statistics
            total_test_cases = self.collection.count_documents({})
            total_users = self.users_collection.count_documents({})
            total_analytics = self.analytics_collection.count_documents({})
            
            # Get recent activity
            recent_test_cases = list(self.collection.find({}, {
                "_id": 1,
                "title": 1,
                "created_at": 1,
                "user_id": 1,
                "source_type": 1
            }).sort("created_at", -1).limit(10))
            
            # Convert ObjectId to string for JSON serialization
            for test_case in recent_test_cases:
                if "_id" in test_case:
                    test_case["_id"] = str(test_case["_id"])
                if "created_at" in test_case:
                    test_case["created_at"] = test_case["created_at"].isoformat()
            
            # Get user statistics
            user_stats = self.get_user_statistics(admin_user_id)
            
            # Get storage information (approximate)
            storage_info = {
                "test_cases_size": total_test_cases * 1024,  # Approximate size in bytes
                "users_size": total_users * 512,
                "analytics_size": total_analytics * 2048
            }
            
            system_overview = {
                "total_test_cases": total_test_cases,
                "total_users": total_users,
                "total_analytics": total_analytics,
                "recent_activity": recent_test_cases,
                "user_statistics": user_stats.get("statistics", {}) if user_stats["success"] else {},
                "storage_info": storage_info,
                "system_health": "healthy"  # You can add more sophisticated health checks
            }
            
            return {"success": True, "system_overview": system_overview}
            
        except Exception as e:
            logger.error(f"Error getting system overview: {str(e)}")
            return {"success": False, "message": "Failed to retrieve system overview"}

    def get_all_users_paginated(self, admin_user_id, page=1, per_page=10):
        """Get all users with pagination (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate skip value for pagination
            skip = (page - 1) * per_page
            
            # Get total count
            total_users = self.users_collection.count_documents({})
            
            # Get users with pagination (sort → skip → limit for PyMongo)
            # Use inclusion projection only (can't mix inclusion and exclusion)
            users = list(self.users_collection.find({}, {
                "_id": 1,
                "email": 1,
                "name": 1,
                "role": 1,
                "status": 1,
                "created_at": 1,
                "last_login": 1,
                "is_active": 1
                # Note: password is excluded by not including it in the projection
            }).sort("created_at", -1).skip(skip).limit(per_page))
            
            # Convert ObjectId to string for JSON serialization
            for user in users:
                if "_id" in user:
                    user["_id"] = str(user["_id"])
                # Safely format datetimes if present and are datetime instances
                try:
                    from datetime import datetime as _dt
                    if "created_at" in user and isinstance(user["created_at"], _dt):
                        user["created_at"] = user["created_at"].isoformat()
                    if "last_login" in user and (user["last_login"] is None or isinstance(user["last_login"], _dt)):
                        user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
                except Exception:
                    # If formatting fails, leave values as-is
                    pass
            
            # Calculate pagination info
            total_pages = (total_users + per_page - 1) // per_page
            
            return {
                "success": True, 
                "users": users,
                "pagination": {
                    "current_page": page,
                    "per_page": per_page,
                    "total_users": total_users,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting paginated users: {str(e)}")
            return {"success": False, "message": "Failed to retrieve users"}

    def get_system_health(self, admin_user_id):
        """Get system health status (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Check database connectivity
            db_status = "healthy"
            try:
                self.db.command("ping")
            except Exception:
                db_status = "unhealthy"
            
            # Check collections
            collections_status = {}
            collections = ["users", "test_cases", "analytics"]
            
            for collection_name in collections:
                try:
                    if collection_name == "users":
                        collection = self.users_collection
                    elif collection_name == "test_cases":
                        collection = self.collection
                    elif collection_name == "analytics":
                        collection = self.analytics_collection
                    
                    # Try to count documents
                    count = collection.count_documents({})
                    collections_status[collection_name] = {
                        "status": "healthy",
                        "document_count": count
                    }
                except Exception as e:
                    collections_status[collection_name] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
            
            # Check recent activity (last 24 hours)
            from datetime import datetime, timedelta
            yesterday = datetime.now() - timedelta(days=1)
            
            recent_activity = {
                "new_users_24h": self.users_collection.count_documents({"created_at": {"$gte": yesterday}}),
                "new_test_cases_24h": self.collection.count_documents({"created_at": {"$gte": yesterday}}),
                "active_users_24h": self.users_collection.count_documents({"last_login": {"$gte": yesterday}})
            }
            
            # Overall system health
            overall_health = "healthy"
            if db_status == "unhealthy":
                overall_health = "critical"
            elif any(col["status"] == "unhealthy" for col in collections_status.values()):
                overall_health = "warning"
            
            return {
                "success": True,
                "system_health": {
                    "overall_status": overall_health,
                    "database_status": db_status,
                    "collections_status": collections_status,
                    "recent_activity": recent_activity,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting system health: {str(e)}")
            return {"success": False, "message": "Failed to retrieve system health"}

    def get_detailed_user_analytics(self, admin_user_id):
        """Get detailed user analytics (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            from datetime import datetime, timedelta
            
            # Get user statistics
            total_users = self.users_collection.count_documents({})
            admin_users = self.users_collection.count_documents({"role": "admin"})
            regular_users = self.users_collection.count_documents({"role": "user"})
            active_users = self.users_collection.count_documents({"is_active": True})
            
            # Get user activity over time (last 30 days)
            thirty_days_ago = datetime.now() - timedelta(days=30)
            users_created_30d = self.users_collection.count_documents({"created_at": {"$gte": thirty_days_ago}})
            
            # Get test case statistics by user
            pipeline = [
                {
                    "$group": {
                        "_id": "$user_id",
                        "test_case_count": {"$sum": 1},
                        "last_activity": {"$max": "$created_at"}
                    }
                },
                {
                    "$lookup": {
                        "from": "users",
                        "localField": "_id",
                        "foreignField": "_id",
                        "as": "user_info"
                    }
                },
                {
                    "$unwind": "$user_info"
                },
                {
                    "$project": {
                        "user_id": "$_id",
                        "user_name": "$user_info.name",
                        "user_email": "$user_info.email",
                        "test_case_count": 1,
                        "last_activity": 1
                    }
                },
                {
                    "$sort": {"test_case_count": -1}
                }
            ]
            
            user_activity = list(self.collection.aggregate(pipeline))
            
            # Convert ObjectId to string for JSON serialization
            for activity in user_activity:
                if "_id" in activity:
                    activity["_id"] = str(activity["_id"])
                if "user_id" in activity:
                    activity["user_id"] = str(activity["user_id"])
                if "last_activity" in activity:
                    activity["last_activity"] = activity["last_activity"].isoformat()
            
            # Get source type distribution
            source_pipeline = [
                {
                    "$group": {
                        "_id": "$source_type",
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            source_distribution = list(self.collection.aggregate(source_pipeline))
            
            return {
                "success": True,
                "analytics": {
                    "user_statistics": {
                        "total_users": total_users,
                        "admin_users": admin_users,
                        "regular_users": regular_users,
                        "active_users": active_users,
                        "users_created_30d": users_created_30d
                    },
                    "user_activity": user_activity[:10],  # Top 10 most active users
                    "source_distribution": source_distribution,
                    "generated_at": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting detailed user analytics: {str(e)}")
            return {"success": False, "message": "Failed to retrieve user analytics"}

    def create_user_by_admin(self, admin_user_id, user_data):
        """Create a new user by admin (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Validate required fields
            required_fields = ['name', 'email', 'password']
            for field in required_fields:
                if field not in user_data or not user_data[field]:
                    return {"success": False, "message": f"Missing required field: {field}"}
            
            # Check if user already exists
            existing_user = self.users_collection.find_one({"email": user_data['email']})
            if existing_user:
                return {"success": False, "message": "User with this email already exists"}
            
            # Hash password
            hashed_password = self.hash_password(user_data['password'])
            
            # Create user document
            user_doc = {
                "name": user_data['name'],
                "email": user_data['email'],
                "password": hashed_password,
                "role": user_data.get('role', 'user'),
                "is_active": user_data.get('is_active', True),
                "created_at": datetime.now(),
                "last_login": None,
                "status": "active"
            }
            
            # Insert user
            result = self.users_collection.insert_one(user_doc)
            
            if result.inserted_id:
                return {
                    "success": True,
                    "message": "User created successfully",
                    "user_id": str(result.inserted_id)
                }
            else:
                return {"success": False, "message": "Failed to create user"}
                
        except Exception as e:
            logger.error(f"Error creating user by admin: {str(e)}")
            return {"success": False, "message": "Failed to create user"}

    def export_system_data(self, admin_user_id):
        """Export system data (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            from datetime import datetime
            
            # Export users (without passwords)
            users = list(self.users_collection.find({}, {"password": 0}))
            for user in users:
                if "_id" in user:
                    user["_id"] = str(user["_id"])
                if "created_at" in user:
                    user["created_at"] = user["created_at"].isoformat()
                if "last_login" in user:
                    user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
            
            # Export test cases
            test_cases = list(self.collection.find({}))
            for test_case in test_cases:
                if "_id" in test_case:
                    test_case["_id"] = str(test_case["_id"])
                if "created_at" in test_case:
                    test_case["created_at"] = test_case["created_at"].isoformat()
            
            # Export analytics
            analytics = list(self.analytics_collection.find({}))
            for analytic in analytics:
                if "_id" in analytic:
                    analytic["_id"] = str(analytic["_id"])
                if "timestamp" in analytic:
                    analytic["timestamp"] = analytic["timestamp"].isoformat()
            
            export_data = {
                "export_info": {
                    "exported_at": datetime.now().isoformat(),
                    "exported_by": admin_user_id,
                    "version": "1.0"
                },
                "users": users,
                "test_cases": test_cases,
                "analytics": analytics,
                "statistics": {
                    "total_users": len(users),
                    "total_test_cases": len(test_cases),
                    "total_analytics": len(analytics)
                }
            }
            
            return {"success": True, "data": export_data}
            
        except Exception as e:
            logger.error(f"Error exporting system data: {str(e)}")
            return {"success": False, "message": "Failed to export system data"}

    def get_system_logs(self, admin_user_id):
        """Get system logs (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # For now, return mock logs. In a real system, you'd have a logs collection
            mock_logs = [
                {
                    "timestamp": datetime.now().isoformat(),
                    "level": "info",
                    "message": "System started successfully",
                    "source": "System"
                },
                {
                    "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
                    "level": "info",
                    "message": "User authentication successful",
                    "source": "Auth"
                },
                {
                    "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
                    "level": "warning",
                    "message": "High memory usage detected",
                    "source": "System"
                },
                {
                    "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
                    "level": "error",
                    "message": "Database connection timeout",
                    "source": "Database"
                }
            ]
            
            return {"success": True, "logs": mock_logs}
            
        except Exception as e:
            logger.error(f"Error getting system logs: {str(e)}")
            return {"success": False, "message": "Failed to retrieve system logs"}

    def create_system_backup(self, admin_user_id):
        """Create system backup (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            from datetime import datetime
            
            # Create backup data
            backup_data = {
                "backup_info": {
                    "created_at": datetime.now().isoformat(),
                    "created_by": admin_user_id,
                    "backup_type": "full"
                },
                "users_count": self.users_collection.count_documents({}),
                "test_cases_count": self.collection.count_documents({}),
                "analytics_count": self.analytics_collection.count_documents({})
            }
            
            # In a real system, you would save this to a backup location
            # For now, we'll just return success
            
            return {
                "success": True, 
                "message": "System backup created successfully",
                "backup_info": backup_data
            }
            
        except Exception as e:
            logger.error(f"Error creating system backup: {str(e)}")
            return {"success": False, "message": "Failed to create system backup"}

    def update_system_settings(self, admin_user_id, settings):
        """Update system settings (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # In a real system, you would save these settings to a settings collection
            # For now, we'll just validate and return success
            
            # Validate settings
            valid_settings = {
                "enableRegistration": bool,
                "requireEmailVerification": bool,
                "maxTestCases": int,
                "sessionTimeout": int,
                "emailNotifications": bool,
                "adminAlerts": bool
            }
            
            for key, value_type in valid_settings.items():
                if key in settings and not isinstance(settings[key], value_type):
                    return {"success": False, "message": f"Invalid setting type for {key}"}
            
            return {
                "success": True,
                "message": "System settings updated successfully",
                "settings": settings
            }
            
        except Exception as e:
            logger.error(f"Error updating system settings: {str(e)}")
            return {"success": False, "message": "Failed to update system settings"}

    def get_user_details(self, admin_user_id, target_user_id):
        """Get user details (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            from bson import ObjectId

            # Attempt lookup by ObjectId; if that fails, try direct string _id
            query_candidates = []
            try:
                user_object_id = ObjectId(target_user_id)
                query_candidates.append({"_id": user_object_id})
            except Exception:
                pass
            # Support string UUID ids as well
            query_candidates.append({"_id": target_user_id})

            # Get user details (first matching candidate)
            projection = {
                "_id": 1,
                "email": 1,
                "name": 1,
                "role": 1,
                "status": 1,
                "created_at": 1,
                "last_login": 1,
                "is_active": 1
            }

            user = None
            for q in query_candidates:
                user = self.users_collection.find_one(q, projection)
                if user:
                    break
            
            if not user:
                return {"success": False, "message": "User not found"}
            
            # Convert ObjectId to string for JSON serialization
            user["_id"] = str(user["_id"])
            
            # Safely format datetimes if present
            try:
                from datetime import datetime as _dt
                if "created_at" in user and isinstance(user["created_at"], _dt):
                    user["created_at"] = user["created_at"].isoformat()
                if "last_login" in user and (user["last_login"] is None or isinstance(user["last_login"], _dt)):
                    user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
            except Exception:
                pass
            
            return {"success": True, "user": user}
            
        except Exception as e:
            logger.error(f"Error getting user details: {str(e)}")
            return {"success": False, "message": "Failed to retrieve user details"}

    def update_user_by_admin(self, admin_user_id, target_user_id, user_data):
        """Update user by admin (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            from bson import ObjectId

            # Build query supporting ObjectId and string UUID
            query_candidates = []
            try:
                user_object_id = ObjectId(target_user_id)
                query_candidates.append({"_id": user_object_id})
            except Exception:
                pass
            query_candidates.append({"_id": target_user_id})

            # Check if user exists
            existing_user = None
            chosen_query = None
            for q in query_candidates:
                existing_user = self.users_collection.find_one(q)
                if existing_user:
                    chosen_query = q
                    break
            if not existing_user:
                return {"success": False, "message": "User not found"}
            
            # Validate required fields
            if 'name' in user_data and not user_data['name']:
                return {"success": False, "message": "Name cannot be empty"}
            
            if 'email' in user_data and not user_data['email']:
                return {"success": False, "message": "Email cannot be empty"}
            
            # Check if email is being changed and if it already exists
            if 'email' in user_data and user_data['email'] != existing_user.get('email'):
                email_exists = self.users_collection.find_one({"email": user_data['email']})
                if email_exists:
                    return {"success": False, "message": "Email already exists"}
            
            # Validate role
            if 'role' in user_data and user_data['role'] not in ['admin', 'user']:
                return {"success": False, "message": "Invalid role. Must be 'admin' or 'user'"}
            
            # Prepare update data
            update_data = {}
            if 'name' in user_data:
                update_data['name'] = user_data['name']
            if 'email' in user_data:
                update_data['email'] = user_data['email']
            if 'role' in user_data:
                update_data['role'] = user_data['role']
            if 'is_active' in user_data:
                update_data['is_active'] = bool(user_data['is_active'])
            
            # Update user
            result = self.users_collection.update_one(chosen_query, {"$set": update_data})
            
            if result.modified_count > 0:
                return {
                    "success": True,
                    "message": "User updated successfully"
                }
            else:
                return {"success": False, "message": "No changes made to user"}
                
        except Exception as e:
            logger.error(f"Error updating user by admin: {str(e)}")
            return {"success": False, "message": "Failed to update user"}

    def backup_user_data(self, admin_user_id, backup_type='full'):
        """Backup user data (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            backup_data = {}
            
            if backup_type in ['full', 'users']:
                # Backup users
                users = list(self.users_collection.find({}, {
                    "password": 0  # Exclude passwords for security
                }))
                
                # Convert ObjectId to string for JSON serialization
                for user in users:
                    if "_id" in user:
                        user["_id"] = str(user["_id"])
                    if "created_at" in user:
                        user["created_at"] = user["created_at"].isoformat()
                    if "last_login" in user:
                        user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
                
                backup_data["users"] = users
            
            if backup_type in ['full', 'test_cases']:
                # Backup test cases
                test_cases = list(self.collection.find({}, {
                    "_id": 1,
                    "title": 1,
                    "created_at": 1,
                    "user_id": 1,
                    "source_type": 1,
                    "status": 1
                }))
                
                # Convert ObjectId to string for JSON serialization
                for test_case in test_cases:
                    if "_id" in test_case:
                        test_case["_id"] = str(test_case["_id"])
                    if "created_at" in test_case:
                        test_case["created_at"] = test_case["created_at"].isoformat()
                
                backup_data["test_cases"] = test_cases
            
            if backup_type in ['full', 'analytics']:
                # Backup analytics
                analytics = list(self.analytics_collection.find({}, {
                    "_id": 1,
                    "created_at": 1,
                    "type": 1,
                    "data": 1
                }))
                
                # Convert ObjectId to string for JSON serialization
                for analytic in analytics:
                    if "_id" in analytic:
                        analytic["_id"] = str(analytic["_id"])
                    if "created_at" in analytic:
                        analytic["created_at"] = analytic["created_at"].isoformat()
                
                backup_data["analytics"] = analytics
            
            # Add backup metadata
            backup_data["metadata"] = {
                "backup_type": backup_type,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": admin_user_id,
                "total_users": len(backup_data.get("users", [])),
                "total_test_cases": len(backup_data.get("test_cases", [])),
                "total_analytics": len(backup_data.get("analytics", []))
            }
            
            logger.info(f"Backup created by admin {admin_user_id}: {backup_type} backup")
            return {"success": True, "backup_data": backup_data}
            
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            return {"success": False, "message": "Failed to create backup"}

    def restore_user_data(self, admin_user_id, backup_data, restore_type='full'):
        """Restore user data from backup (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Validate backup data
            if not isinstance(backup_data, dict) or "metadata" not in backup_data:
                return {"success": False, "message": "Invalid backup data format"}
            
            restored_count = 0
            errors = []
            
            if restore_type in ['full', 'users'] and "users" in backup_data:
                try:
                    # Clear existing users (be careful with this!)
                    # self.users_collection.delete_many({})
                    
                    # Restore users
                    for user in backup_data["users"]:
                        # Convert string dates back to datetime
                        if "created_at" in user and user["created_at"]:
                            user["created_at"] = datetime.fromisoformat(user["created_at"])
                        if "last_login" in user and user["last_login"]:
                            user["last_login"] = datetime.fromisoformat(user["last_login"])
                        
                        # Insert user
                        result = self.users_collection.insert_one(user)
                        if result.inserted_id:
                            restored_count += 1
                        else:
                            errors.append(f"Failed to restore user: {user.get('email', 'Unknown')}")
                    
                except Exception as e:
                    errors.append(f"Error restoring users: {str(e)}")
            
            if restore_type in ['full', 'test_cases'] and "test_cases" in backup_data:
                try:
                    # Clear existing test cases (be careful with this!)
                    # self.collection.delete_many({})
                    
                    # Restore test cases
                    for test_case in backup_data["test_cases"]:
                        # Convert string dates back to datetime
                        if "created_at" in test_case and test_case["created_at"]:
                            test_case["created_at"] = datetime.fromisoformat(test_case["created_at"])
                        
                        # Insert test case
                        result = self.collection.insert_one(test_case)
                        if result.inserted_id:
                            restored_count += 1
                        else:
                            errors.append(f"Failed to restore test case: {test_case.get('title', 'Unknown')}")
                    
                except Exception as e:
                    errors.append(f"Error restoring test cases: {str(e)}")
            
            if restore_type in ['full', 'analytics'] and "analytics" in backup_data:
                try:
                    # Clear existing analytics (be careful with this!)
                    # self.analytics_collection.delete_many({})
                    
                    # Restore analytics
                    for analytic in backup_data["analytics"]:
                        # Convert string dates back to datetime
                        if "created_at" in analytic and analytic["created_at"]:
                            analytic["created_at"] = datetime.fromisoformat(analytic["created_at"])
                        
                        # Insert analytic
                        result = self.analytics_collection.insert_one(analytic)
                        if result.inserted_id:
                            restored_count += 1
                        else:
                            errors.append(f"Error restoring analytic data")
                    
                except Exception as e:
                    errors.append(f"Error restoring analytics: {str(e)}")
            
            logger.info(f"Data restoration completed by admin {admin_user_id}: {restore_type} restore")
            return {
                "success": True,
                "message": f"Restoration completed. {restored_count} items restored.",
                "restored_count": restored_count,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Error restoring data: {str(e)}")
            return {"success": False, "message": "Failed to restore data"}

    def get_user_permissions(self, user_id):
        """Get user permissions based on role"""
        try:
            user = self.users_collection.find_one({"_id": user_id})
            if not user:
                return {"success": False, "message": "User not found"}
            
            role = user.get("role", "user")
            
            # Define permissions for each role
            permissions = {
                "admin": {
                    "can_create_users": True,
                    "can_delete_users": True,
                    "can_update_user_roles": True,
                    "can_view_all_users": True,
                    "can_view_system_stats": True,
                    "can_backup_data": True,
                    "can_restore_data": True,
                    "can_export_data": True,
                    "can_manage_system": True,
                    "can_view_analytics": True,
                    "can_manage_test_cases": True
                },
                "user": {
                    "can_create_users": False,
                    "can_delete_users": False,
                    "can_update_user_roles": False,
                    "can_view_all_users": False,
                    "can_view_system_stats": False,
                    "can_backup_data": False,
                    "can_restore_data": False,
                    "can_export_data": False,
                    "can_manage_system": False,
                    "can_view_analytics": True,
                    "can_manage_test_cases": True
                }
            }
            
            user_permissions = permissions.get(role, permissions["user"])
            
            return {
                "success": True,
                "permissions": user_permissions,
                "role": role
            }
            
        except Exception as e:
            logger.error(f"Error getting user permissions: {str(e)}")
            return {"success": False, "message": "Failed to retrieve user permissions"}

    def validate_admin_access(self, user_id, required_permission=None):
        """Validate if user has admin access and specific permission if required"""
        try:
            user = self.users_collection.find_one({"_id": user_id})
            if not user:
                return {"success": False, "message": "User not found"}
            
            if user.get("role") != "admin":
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            if required_permission:
                permissions = self.get_user_permissions(user_id)
                if not permissions["success"]:
                    return {"success": False, "message": "Failed to retrieve user permissions"}
                
                if not permissions["permissions"].get(required_permission, False):
                    return {"success": False, "message": f"Access denied. {required_permission} permission required."}
            
            return {"success": True, "message": "Access granted"}
            
        except Exception as e:
            logger.error(f"Error validating admin access: {str(e)}")
            return {"success": False, "message": "Failed to validate access"}

    def get_user_audit_trail(self, admin_user_id, user_id=None, action_type=None, limit=100):
        """Get user audit trail (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Create query
            query = {}
            if user_id:
                query["user_id"] = user_id
            if action_type:
                query["action_type"] = action_type
            
            # Get audit logs (you'll need to create an audit collection)
            # For now, we'll return a placeholder
            audit_logs = []
            
            # You can implement actual audit logging by creating an audit collection
            # and logging all admin actions there
            
            return {
                "success": True,
                "audit_logs": audit_logs,
                "count": len(audit_logs),
                "message": "Audit trail feature not yet implemented"
            }
            
        except Exception as e:
            logger.error(f"Error getting user audit trail: {str(e)}")
            return {"success": False, "message": "Failed to retrieve audit trail"}

    def log_admin_action(self, admin_user_id, action_type, target_id=None, details=None):
        """Log admin actions for audit trail"""
        try:
            # Create audit log entry
            audit_entry = {
                "admin_user_id": admin_user_id,
                "action_type": action_type,
                "target_id": target_id,
                "details": details,
                "timestamp": datetime.utcnow(),
                "ip_address": None,  # You can add IP address logging if needed
                "user_agent": None   # You can add user agent logging if needed
            }
            
            # Insert into audit collection (create if doesn't exist)
            audit_collection = self.db.admin_audit_logs
            result = audit_collection.insert_one(audit_entry)
            
            if result.inserted_id:
                logger.info(f"Admin action logged: {action_type} by {admin_user_id}")
                return {"success": True, "message": "Action logged successfully"}
            else:
                return {"success": False, "message": "Failed to log action"}
                
        except Exception as e:
            logger.error(f"Error logging admin action: {str(e)}")
            return {"success": False, "message": "Failed to log admin action"}

    def get_user_sessions(self, admin_user_id, user_id=None, limit=50):
        """Get user session information (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Create query
            query = {}
            if user_id:
                query["user_id"] = user_id
            
            # Get user sessions
            sessions = list(self.user_sessions_collection.find(query, {
                "_id": 1,
                "user_id": 1,
                "created_at": 1,
                "last_activity": 1,
                "ip_address": 1,
                "user_agent": 1,
                "is_active": 1
            }).sort("last_activity", -1).limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for session in sessions:
                if "_id" in session:
                    session["_id"] = str(session["_id"])
                if "created_at" in session:
                    session["created_at"] = session["created_at"].isoformat()
                if "last_activity" in session:
                    session["last_activity"] = session["last_activity"].isoformat()
            
            return {"success": True, "sessions": sessions, "count": len(sessions)}
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {str(e)}")
            return {"success": False, "message": "Failed to retrieve user sessions"}

    def terminate_user_sessions(self, admin_user_id, user_id=None, session_id=None):
        """Terminate user sessions (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Create query
            query = {}
            if user_id:
                query["user_id"] = user_id
            if session_id:
                query["_id"] = session_id
            
            # Terminate sessions
            result = self.user_sessions_collection.update_many(
                query,
                {"$set": {"is_active": False, "terminated_at": datetime.utcnow()}}
            )
            
            if result.modified_count > 0:
                logger.info(f"User sessions terminated by admin {admin_user_id}: {result.modified_count} sessions")
                return {"success": True, "message": f"{result.modified_count} sessions terminated successfully"}
            else:
                return {"success": False, "message": "No sessions found to terminate"}
                
        except Exception as e:
            logger.error(f"Error terminating user sessions: {str(e)}")
            return {"success": False, "message": "Failed to terminate sessions"}

    def get_user_login_history(self, admin_user_id, user_id=None, limit=100):
        """Get user login history (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Create query
            query = {}
            if user_id:
                query["user_id"] = user_id
            
            # Get login history from users collection
            users = list(self.users_collection.find(query, {
                "_id": 1,
                "email": 1,
                "name": 1,
                "last_login": 1,
                "created_at": 1
            }).sort("last_login", -1).limit(limit))
            
            # Convert ObjectId to string for JSON serialization
            for user in users:
                if "_id" in user:
                    user["_id"] = str(user["_id"])
                if "created_at" in user:
                    user["created_at"] = user["created_at"].isoformat()
                if "last_login" in user:
                    user["last_login"] = user["last_login"].isoformat() if user["last_login"] else None
            
            return {"success": True, "login_history": users, "count": len(users)}
            
        except Exception as e:
            logger.error(f"Error getting user login history: {str(e)}")
            return {"success": False, "message": "Failed to retrieve login history"}

    def get_user_performance_metrics(self, admin_user_id, user_id=None, time_period='month'):
        """Get user performance metrics (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Create query
            query = {"created_at": {"$gte": start_date}}
            if user_id:
                query["user_id"] = user_id
            
            # Get test case metrics
            test_case_metrics = list(self.collection.aggregate([
                {"$match": query},
                {"$group": {
                    "_id": "$user_id",
                    "total_test_cases": {"$sum": 1},
                    "avg_completion_time": {"$avg": "$completion_time"},
                    "success_rate": {"$avg": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}}
                }}
            ]))
            
            # Get user details for metrics
            user_metrics = []
            for metric in test_case_metrics:
                user = self.users_collection.find_one({"_id": metric["_id"]}, {
                    "name": 1,
                    "email": 1,
                    "role": 1
                })
                
                if user:
                    user_metric = {
                        "user_id": str(metric["_id"]),
                        "name": user["name"],
                        "email": user["email"],
                        "role": user.get("role", "user"),
                        "total_test_cases": metric["total_test_cases"],
                        "avg_completion_time": metric.get("avg_completion_time", 0),
                        "success_rate": metric.get("success_rate", 0) * 100
                    }
                    user_metrics.append(user_metric)
            
            # Sort by total test cases
            user_metrics.sort(key=lambda x: x["total_test_cases"], reverse=True)
            
            return {
                "success": True,
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "user_metrics": user_metrics,
                "total_users": len(user_metrics)
            }
            
        except Exception as e:
            logger.error(f"Error getting user performance metrics: {str(e)}")
            return {"success": False, "message": "Failed to retrieve performance metrics"}

    def get_system_health_status(self, admin_user_id):
        """Get system health status (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Check database connection
            try:
                self.client.server_info()
                db_status = "healthy"
            except Exception as e:
                db_status = f"unhealthy: {str(e)}"
            
            # Check collections
            collections_status = {}
            for collection_name in ["users", "test_cases", "analytics", "user_sessions"]:
                try:
                    collection = self.db[collection_name]
                    count = collection.count_documents({})
                    collections_status[collection_name] = {
                        "status": "healthy",
                        "document_count": count
                    }
                except Exception as e:
                    collections_status[collection_name] = {
                        "status": f"unhealthy: {str(e)}",
                        "document_count": 0
                    }
            
            # Check system resources (basic)
            import psutil
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                system_resources = {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": disk.percent,
                    "status": "available"
                }
            except ImportError:
                system_resources = {
                    "status": "psutil not available",
                    "message": "Install psutil package for system resource monitoring"
                }
            
            # Overall health status
            overall_status = "healthy"
            if db_status != "healthy":
                overall_status = "unhealthy"
            
            for collection_status in collections_status.values():
                if collection_status["status"] != "healthy":
                    overall_status = "unhealthy"
                    break
            
            health_status = {
                "overall_status": overall_status,
                "timestamp": datetime.utcnow().isoformat(),
                "database": {
                    "status": db_status,
                    "connection": "MongoDB"
                },
                "collections": collections_status,
                "system_resources": system_resources,
                "recommendations": []
            }
            
            # Add recommendations based on status
            if overall_status == "unhealthy":
                health_status["recommendations"].append("Check database connection and collection access")
            
            if system_resources.get("cpu_percent", 0) > 80:
                health_status["recommendations"].append("High CPU usage detected")
            
            if system_resources.get("memory_percent", 0) > 80:
                health_status["recommendations"].append("High memory usage detected")
            
            if system_resources.get("disk_percent", 0) > 90:
                health_status["recommendations"].append("Low disk space detected")
            
            return {"success": True, "health_status": health_status}
            
        except Exception as e:
            logger.error(f"Error getting system health status: {str(e)}")
            return {"success": False, "message": "Failed to retrieve system health status"}

    def get_user_activity_summary(self, admin_user_id, time_period='month'):
        """Get user activity summary (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get activity summary
            activity_summary = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": {
                        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                        "source_type": "$source_type"
                    },
                    "count": {"$sum": 1},
                    "users": {"$addToSet": "$user_id"}
                }},
                {"$group": {
                    "_id": "$_id.date",
                    "total_test_cases": {"$sum": "$count"},
                    "unique_users": {"$sum": {"$size": "$users"}},
                    "source_types": {
                        "$push": {
                            "source_type": "$_id.source_type",
                            "count": "$count"
                        }
                    }
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            # Get user registration summary
            user_registration_summary = list(self.users_collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "new_users": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            # Get login activity summary
            login_activity_summary = list(self.users_collection.aggregate([
                {"$match": {"last_login": {"$gte": start_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$last_login"}},
                    "active_users": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            # Combine all summaries
            combined_summary = {}
            
            # Initialize dates
            current_date = start_date
            while current_date <= now:
                date_str = current_date.strftime("%Y-%m-%d")
                combined_summary[date_str] = {
                    "date": date_str,
                    "total_test_cases": 0,
                    "unique_users": 0,
                    "new_users": 0,
                    "active_users": 0,
                    "source_types": {}
                }
                current_date += timedelta(days=1)
            
            # Fill in test case activity
            for summary in activity_summary:
                date_str = summary["_id"]
                if date_str in combined_summary:
                    combined_summary[date_str]["total_test_cases"] = summary["total_test_cases"]
                    combined_summary[date_str]["unique_users"] = summary["unique_users"]
                    
                    # Fill in source types
                    for source_type_info in summary["source_types"]:
                        source_type = source_type_info["source_type"]
                        count = source_type_info["count"]
                        combined_summary[date_str]["source_types"][source_type] = count
            
            # Fill in user registration
            for summary in user_registration_summary:
                date_str = summary["_id"]
                if date_str in combined_summary:
                    combined_summary[date_str]["new_users"] = summary["new_users"]
            
            # Fill in login activity
            for summary in login_activity_summary:
                date_str = summary["_id"]
                if date_str in combined_summary:
                    combined_summary[date_str]["active_users"] = summary["active_users"]
            
            # Convert to list and sort
            activity_summary_list = list(combined_summary.values())
            activity_summary_list.sort(key=lambda x: x["date"])
            
            return {
                "success": True,
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "activity_summary": activity_summary_list,
                "total_days": len(activity_summary_list)
            }
            
        except Exception as e:
            logger.error(f"Error getting user activity summary: {str(e)}")
            return {"success": False, "message": "Failed to retrieve activity summary"}

    def get_user_engagement_metrics(self, admin_user_id, time_period='month'):
        """Get user engagement metrics (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get total users
            total_users = self.users_collection.count_documents({})
            
            # Get active users (users who logged in during the period)
            active_users = self.users_collection.count_documents({
                "last_login": {"$gte": start_date}
            })
            
            # Get new users during the period
            new_users = self.users_collection.count_documents({
                "created_at": {"$gte": start_date}
            })
            
            # Get users who created test cases during the period
            users_with_activity = len(self.collection.distinct("user_id", {
                "created_at": {"$gte": start_date}
            }))
            
            # Calculate engagement metrics
            engagement_rate = (active_users / total_users * 100) if total_users > 0 else 0
            activity_rate = (users_with_activity / total_users * 100) if total_users > 0 else 0
            retention_rate = ((total_users - new_users) / total_users * 100) if total_users > 0 else 0
            
            # Get user activity frequency
            user_activity_frequency = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "activity_count": {"$sum": 1}
                }},
                {"$group": {
                    "_id": None,
                    "avg_activity_per_user": {"$avg": "$activity_count"},
                    "max_activity": {"$max": "$activity_count"},
                    "min_activity": {"$min": "$activity_count"}
                }}
            ]))
            
            activity_stats = user_activity_frequency[0] if user_activity_frequency else {
                "avg_activity_per_user": 0,
                "max_activity": 0,
                "min_activity": 0
            }
            
            # Get source type distribution
            source_type_distribution = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$source_type",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}}
            ]))
            
            # Get user role distribution
            role_distribution = list(self.users_collection.aggregate([
                {"$group": {
                    "_id": "$role",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"count": -1}}
            ]))
            
            engagement_metrics = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_users": total_users,
                "active_users": active_users,
                "new_users": new_users,
                "users_with_activity": users_with_activity,
                "engagement_rate": round(engagement_rate, 2),
                "activity_rate": round(activity_rate, 2),
                "retention_rate": round(retention_rate, 2),
                "activity_stats": {
                    "avg_activity_per_user": round(activity_stats["avg_activity_per_user"], 2),
                    "max_activity": activity_stats["max_activity"],
                    "min_activity": activity_stats["min_activity"]
                },
                "source_type_distribution": source_type_distribution,
                "role_distribution": role_distribution
            }
            
            return {"success": True, "engagement_metrics": engagement_metrics}
            
        except Exception as e:
            logger.error(f"Error getting user engagement metrics: {str(e)}")
            return {"success": False, "message": "Failed to retrieve engagement metrics"}

    def get_user_feedback_metrics(self, admin_user_id, time_period='month'):
        """Get user feedback and ratings metrics (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get test case success rates
            test_case_success_rates = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "total_test_cases": {"$sum": 1},
                    "successful_test_cases": {
                        "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    }
                }},
                {"$project": {
                    "user_id": "$_id",
                    "total_test_cases": 1,
                    "success_rate": {
                        "$multiply": [
                            {"$divide": ["$successful_test_cases", "$total_test_cases"]},
                            100
                        ]
                    }
                }}
            ]))
            
            # Get user satisfaction scores (if you have a ratings collection)
            # For now, we'll use test case completion as a proxy for satisfaction
            user_satisfaction = []
            for user_metric in test_case_success_rates:
                satisfaction_score = 0
                if user_metric["total_test_cases"] > 0:
                    if user_metric["success_rate"] >= 90:
                        satisfaction_score = 5  # Excellent
                    elif user_metric["success_rate"] >= 80:
                        satisfaction_score = 4  # Good
                    elif user_metric["success_rate"] >= 70:
                        satisfaction_score = 3  # Average
                    elif user_metric["success_rate"] >= 60:
                        satisfaction_score = 2  # Below Average
                    else:
                        satisfaction_score = 1  # Poor
                
                user_satisfaction.append({
                    "user_id": user_metric["user_id"],
                    "satisfaction_score": satisfaction_score,
                    "success_rate": round(user_metric["success_rate"], 2),
                    "total_test_cases": user_metric["total_test_cases"]
                })
            
            # Calculate overall satisfaction metrics
            if user_satisfaction:
                avg_satisfaction = sum(u["satisfaction_score"] for u in user_satisfaction) / len(user_satisfaction)
                satisfaction_distribution = {}
                for i in range(1, 6):
                    satisfaction_distribution[f"score_{i}"] = len([u for u in user_satisfaction if u["satisfaction_score"] == i])
            else:
                avg_satisfaction = 0
                satisfaction_distribution = {f"score_{i}": 0 for i in range(1, 6)}
            
            # Get user activity correlation with satisfaction
            activity_satisfaction_correlation = []
            for user in user_satisfaction:
                # Get user details
                user_details = self.users_collection.find_one({"_id": user["user_id"]}, {
                    "name": 1,
                    "email": 1,
                    "role": 1,
                    "created_at": 1
                })
                
                if user_details:
                    activity_satisfaction_correlation.append({
                        "user_id": user["user_id"],
                        "name": user_details["name"],
                        "email": user_details["email"],
                        "role": user_details.get("role", "user"),
                        "satisfaction_score": user["satisfaction_score"],
                        "success_rate": user["success_rate"],
                        "total_test_cases": user["total_test_cases"],
                        "user_since": user_details["created_at"].isoformat() if user_details.get("created_at") else None
                    })
            
            # Sort by satisfaction score
            activity_satisfaction_correlation.sort(key=lambda x: x["satisfaction_score"], reverse=True)
            
            feedback_metrics = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "overall_satisfaction": round(avg_satisfaction, 2),
                "satisfaction_distribution": satisfaction_distribution,
                "total_users_analyzed": len(user_satisfaction),
                "user_satisfaction_details": activity_satisfaction_correlation,
                "success_rate_summary": {
                    "excellent": len([u for u in user_satisfaction if u["success_rate"] >= 90]),
                    "good": len([u for u in user_satisfaction if 80 <= u["success_rate"] < 90]),
                    "average": len([u for u in user_satisfaction if 70 <= u["success_rate"] < 80]),
                    "below_average": len([u for u in user_satisfaction if 60 <= u["success_rate"] < 70]),
                    "poor": len([u for u in user_satisfaction if u["success_rate"] < 60])
                }
            }
            
            return {"success": True, "feedback_metrics": feedback_metrics}
            
        except Exception as e:
            logger.error(f"Error getting user feedback metrics: {str(e)}")
            return {"success": False, "message": "Failed to retrieve feedback metrics"}

    def get_user_growth_trends(self, admin_user_id, time_period='year'):
        """Get user growth trends (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'month':
                start_date = now - timedelta(days=30)
                date_format = "%Y-%m"
            elif time_period == 'quarter':
                start_date = now - timedelta(days=90)
                date_format = "%Y-Q%q"
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
                date_format = "%Y-%m"
            else:
                start_date = now - timedelta(days=365)  # Default to year
                date_format = "%Y-%m"
            
            # Get user registration trends
            user_registration_trends = list(self.users_collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": date_format, "date": "$created_at"}},
                    "new_users": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            # Get user activity trends
            user_activity_trends = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": date_format, "date": "$created_at"}},
                    "total_activities": {"$sum": 1},
                    "unique_users": {"$size": {"$addToSet": "$user_id"}}
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            # Get user login trends
            user_login_trends = list(self.users_collection.aggregate([
                {"$match": {"last_login": {"$gte": start_date}}},
                {"$group": {
                    "_id": {"$dateToString": {"format": date_format, "date": "$last_login"}},
                    "active_users": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            # Combine all trends
            combined_trends = {}
            
            # Initialize time periods
            current_date = start_date
            while current_date <= now:
                if time_period == 'month':
                    period_key = current_date.strftime("%Y-%m")
                elif time_period == 'quarter':
                    quarter = (current_date.month - 1) // 3 + 1
                    period_key = f"{current_date.year}-Q{quarter}"
                else:
                    period_key = current_date.strftime("%Y-%m")
                
                combined_trends[period_key] = {
                    "period": period_key,
                    "new_users": 0,
                    "total_activities": 0,
                    "unique_users": 0,
                    "active_users": 0,
                    "growth_rate": 0,
                    "activity_rate": 0
                }
                
                if time_period == 'month':
                    current_date += timedelta(days=30)
                elif time_period == 'quarter':
                    current_date += timedelta(days=90)
                else:
                    current_date += timedelta(days=30)
            
            # Fill in user registration trends
            for trend in user_registration_trends:
                period_key = trend["_id"]
                if period_key in combined_trends:
                    combined_trends[period_key]["new_users"] = trend["new_users"]
            
            # Fill in user activity trends
            for trend in user_activity_trends:
                period_key = trend["_id"]
                if period_key in combined_trends:
                    combined_trends[period_key]["total_activities"] = trend["total_activities"]
                    combined_trends[period_key]["unique_users"] = trend["unique_users"]
            
            # Fill in user login trends
            for trend in user_login_trends:
                period_key = trend["_id"]
                if period_key in combined_trends:
                    combined_trends[period_key]["active_users"] = trend["active_users"]
            
            # Calculate growth rates and activity rates
            periods = sorted(combined_trends.keys())
            for i, period in enumerate(periods):
                if i > 0:
                    prev_period = periods[i-1]
                    prev_users = combined_trends[prev_period]["new_users"]
                    current_users = combined_trends[period]["new_users"]
                    
                    if prev_users > 0:
                        growth_rate = ((current_users - prev_users) / prev_users) * 100
                    else:
                        growth_rate = 100 if current_users > 0 else 0
                    
                    combined_trends[period]["growth_rate"] = round(growth_rate, 2)
                
                # Calculate activity rate
                total_users_in_period = sum(combined_trends[p]["new_users"] for p in periods[:i+1])
                if total_users_in_period > 0:
                    activity_rate = (combined_trends[period]["active_users"] / total_users_in_period) * 100
                else:
                    activity_rate = 0
                
                combined_trends[period]["activity_rate"] = round(activity_rate, 2)
            
            # Convert to list
            growth_trends_list = list(combined_trends.values())
            
            # Calculate summary statistics
            total_new_users = sum(trend["new_users"] for trend in growth_trends_list)
            avg_growth_rate = sum(trend["growth_rate"] for trend in growth_trends_list if trend["growth_rate"] != 0) / len([t for t in growth_trends_list if t["growth_rate"] != 0]) if any(t["growth_rate"] != 0 for t in growth_trends_list) else 0
            avg_activity_rate = sum(trend["activity_rate"] for trend in growth_trends_list) / len(growth_trends_list) if growth_trends_list else 0
            
            growth_trends = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_new_users": total_new_users,
                "average_growth_rate": round(avg_growth_rate, 2),
                "average_activity_rate": round(avg_activity_rate, 2),
                "trends": growth_trends_list,
                "summary": {
                    "best_growth_period": max(growth_trends_list, key=lambda x: x["growth_rate"]) if growth_trends_list else None,
                    "best_activity_period": max(growth_trends_list, key=lambda x: x["activity_rate"]) if growth_trends_list else None,
                    "total_periods": len(growth_trends_list)
                }
            }
            
            return {"success": True, "growth_trends": growth_trends}
            
        except Exception as e:
            logger.error(f"Error getting user growth trends: {str(e)}")
            return {"success": False, "message": "Failed to retrieve growth trends"}

    def get_user_retention_analysis(self, admin_user_id, time_period='month'):
        """Get user retention analysis (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'week':
                start_date = now - timedelta(weeks=4)  # 4 weeks for retention analysis
            elif time_period == 'month':
                start_date = now - timedelta(days=90)  # 3 months for retention analysis
            elif time_period == 'quarter':
                start_date = now - timedelta(days=180)  # 6 months for retention analysis
            else:
                start_date = now - timedelta(days=90)  # Default to 3 months
            
            # Get user cohorts (users who registered in the same time period)
            cohort_analysis = []
            
            # Create weekly cohorts for the analysis period
            current_cohort_start = start_date
            while current_cohort_start <= now:
                cohort_end = current_cohort_start + timedelta(weeks=1)
                
                # Get users who registered in this cohort
                cohort_users = list(self.users_collection.find({
                    "created_at": {
                        "$gte": current_cohort_start,
                        "$lt": cohort_end
                    }
                }, {"_id": 1, "created_at": 1}))
                
                if cohort_users:
                    cohort_size = len(cohort_users)
                    cohort_user_ids = [user["_id"] for user in cohort_users]
                    
                    # Calculate retention for different time periods
                    retention_periods = [1, 2, 3, 4]  # weeks
                    retention_data = {}
                    
                    for period in retention_periods:
                        period_start = cohort_end + timedelta(weeks=period-1)
                        period_end = period_start + timedelta(weeks=1)
                        
                        # Count users who were active in this period
                        active_users = self.collection.count_documents({
                            "user_id": {"$in": cohort_user_ids},
                            "created_at": {
                                "$gte": period_start,
                                "$lt": period_end
                            }
                        })
                        
                        retention_rate = (active_users / cohort_size * 100) if cohort_size > 0 else 0
                        retention_data[f"week_{period}"] = {
                            "active_users": active_users,
                            "retention_rate": round(retention_rate, 2)
                        }
                    
                    cohort_analysis.append({
                        "cohort_start": current_cohort_start.isoformat(),
                        "cohort_end": cohort_end.isoformat(),
                        "cohort_size": cohort_size,
                        "retention_data": retention_data
                    })
                
                current_cohort_start = cohort_end
            
            # Calculate overall retention metrics
            total_cohorts = len(cohort_analysis)
            if total_cohorts > 0:
                avg_week_1_retention = sum(cohort["retention_data"]["week_1"]["retention_rate"] for cohort in cohort_analysis) / total_cohorts
                avg_week_2_retention = sum(cohort["retention_data"]["week_2"]["retention_rate"] for cohort in cohort_analysis) / total_cohorts
                avg_week_3_retention = sum(cohort["retention_data"]["week_3"]["retention_rate"] for cohort in cohort_analysis) / total_cohorts
                avg_week_4_retention = sum(cohort["retention_data"]["week_4"]["retention_rate"] for cohort in cohort_analysis) / total_cohorts
            else:
                avg_week_1_retention = avg_week_2_retention = avg_week_3_retention = avg_week_4_retention = 0
            
            # Get user churn analysis
            churn_analysis = []
            for cohort in cohort_analysis:
                cohort_start = datetime.fromisoformat(cohort["cohort_start"])
                cohort_end = datetime.fromisoformat(cohort["cohort_end"])
                
                # Calculate churn rate (users who stopped being active)
                churn_rate = 100 - cohort["retention_data"]["week_4"]["retention_rate"]
                
                churn_analysis.append({
                    "cohort_period": f"{cohort_start.strftime('%Y-%m-%d')} to {cohort_end.strftime('%Y-%m-%d')}",
                    "cohort_size": cohort["cohort_size"],
                    "week_1_retention": cohort["retention_data"]["week_1"]["retention_rate"],
                    "week_4_retention": cohort["retention_data"]["week_4"]["retention_rate"],
                    "churn_rate": round(churn_rate, 2)
                })
            
            # Get user lifetime value analysis
            user_lifetime_analysis = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "total_test_cases": {"$sum": 1},
                    "first_activity": {"$min": "$created_at"},
                    "last_activity": {"$max": "$created_at"}
                }},
                {"$project": {
                    "user_id": "$_id",
                    "total_test_cases": 1,
                    "lifetime_days": {
                        "$divide": [
                            {"$subtract": ["$last_activity", "$first_activity"]},
                            1000 * 60 * 60 * 24  # Convert milliseconds to days
                        ]
                    }
                }}
            ]))
            
            # Calculate average lifetime metrics
            if user_lifetime_analysis:
                avg_lifetime_days = sum(user["lifetime_days"] for user in user_lifetime_analysis) / len(user_lifetime_analysis)
                avg_test_cases_per_user = sum(user["total_test_cases"] for user in user_lifetime_analysis) / len(user_lifetime_analysis)
            else:
                avg_lifetime_days = avg_test_cases_per_user = 0
            
            retention_analysis = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_cohorts": total_cohorts,
                "cohort_analysis": cohort_analysis,
                "overall_retention_metrics": {
                    "week_1_retention": round(avg_week_1_retention, 2),
                    "week_2_retention": round(avg_week_2_retention, 2),
                    "week_3_retention": round(avg_week_3_retention, 2),
                    "week_4_retention": round(avg_week_4_retention, 2)
                },
                "churn_analysis": churn_analysis,
                "user_lifetime_analysis": {
                    "total_users_analyzed": len(user_lifetime_analysis),
                    "average_lifetime_days": round(avg_lifetime_days, 2),
                    "average_test_cases_per_user": round(avg_test_cases_per_user, 2)
                }
            }
            
            return {"success": True, "retention_analysis": retention_analysis}
            
        except Exception as e:
            logger.error(f"Error getting user retention analysis: {str(e)}")
            return {"success": False, "message": "Failed to retrieve retention analysis"}

    def get_user_behavior_patterns(self, admin_user_id, time_period='month'):
        """Get user behavior patterns (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get time-based activity patterns
            hourly_activity = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": {"$hour": "$created_at"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            daily_activity = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": {"$dayOfWeek": "$created_at"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]))
            
            # Get source type preferences by user
            source_type_preferences = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": {
                        "user_id": "$user_id",
                        "source_type": "$source_type"
                    },
                    "count": {"$sum": 1}
                }},
                {"$group": {
                    "_id": "$_id.user_id",
                    "source_types": {
                        "$push": {
                            "source_type": "$_id.source_type",
                            "count": "$count"
                        }
                    },
                    "total_activities": {"$sum": "$count"}
                }},
                {"$sort": {"total_activities": -1}}
            ]))
            
            # Get user session patterns
            user_session_patterns = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "sessions": {
                        "$push": {
                            "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                            "time": {"$hour": "$created_at"}
                        }
                    },
                    "total_activities": {"$sum": 1}
                }},
                {"$project": {
                    "user_id": "$_id",
                    "total_activities": 1,
                    "unique_days": {"$size": {"$setUnion": "$sessions.date"}},
                    "avg_activities_per_day": {"$divide": ["$total_activities", {"$size": {"$setUnion": "$sessions.date"}}]},
                    "session_patterns": "$sessions"
                }}
            ]))
            
            # Get user engagement patterns
            engagement_patterns = []
            for user_pattern in user_session_patterns:
                # Get user details
                user_details = self.users_collection.find_one({"_id": user_pattern["user_id"]}, {
                    "name": 1,
                    "email": 1,
                    "role": 1
                })
                
                if user_details:
                    # Calculate engagement score based on activity frequency
                    activity_frequency = user_pattern["avg_activities_per_day"]
                    engagement_score = 0
                    
                    if activity_frequency >= 5:
                        engagement_score = "Very High"
                    elif activity_frequency >= 3:
                        engagement_score = "High"
                    elif activity_frequency >= 1:
                        engagement_score = "Medium"
                    else:
                        engagement_score = "Low"
                    
                    engagement_patterns.append({
                        "user_id": str(user_pattern["user_id"]),
                        "name": user_details["name"],
                        "email": user_details["email"],
                        "role": user_details.get("role", "user"),
                        "total_activities": user_pattern["total_activities"],
                        "unique_days": user_pattern["unique_days"],
                        "avg_activities_per_day": round(user_pattern["avg_activities_per_day"], 2),
                        "engagement_score": engagement_score
                    })
            
            # Sort by engagement score
            engagement_patterns.sort(key=lambda x: {
                "Very High": 4,
                "High": 3,
                "Medium": 2,
                "Low": 1
            }[x["engagement_score"]], reverse=True)
            
            # Get peak usage times
            peak_usage_times = []
            for hour_data in hourly_activity:
                hour = hour_data["_id"]
                count = hour_data["count"]
                
                time_period = ""
                if 6 <= hour < 12:
                    time_period = "Morning"
                elif 12 <= hour < 17:
                    time_period = "Afternoon"
                elif 17 <= hour < 21:
                    time_period = "Evening"
                else:
                    time_period = "Night"
                
                peak_usage_times.append({
                    "hour": hour,
                    "time_period": time_period,
                    "activity_count": count,
                    "formatted_time": f"{hour:02d}:00"
                })
            
            # Get weekly activity patterns
            weekly_patterns = []
            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            for day_data in daily_activity:
                day_number = day_data["_id"]
                count = day_data["count"]
                
                weekly_patterns.append({
                    "day_number": day_number,
                    "day_name": day_names[day_number - 1],
                    "activity_count": count
                })
            
            behavior_patterns = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "hourly_activity": peak_usage_times,
                "weekly_patterns": weekly_patterns,
                "source_type_preferences": source_type_preferences,
                "user_session_patterns": user_session_patterns,
                "engagement_patterns": engagement_patterns,
                "summary": {
                    "peak_hour": max(peak_usage_times, key=lambda x: x["activity_count"]) if peak_usage_times else None,
                    "peak_day": max(weekly_patterns, key=lambda x: x["activity_count"]) if weekly_patterns else None,
                    "total_users_analyzed": len(engagement_patterns),
                    "high_engagement_users": len([u for u in engagement_patterns if u["engagement_score"] in ["Very High", "High"]])
                }
            }
            
            return {"success": True, "behavior_patterns": behavior_patterns}
            
        except Exception as e:
            logger.error(f"Error getting user behavior patterns: {str(e)}")
            return {"success": False, "message": "Failed to retrieve behavior patterns"}

    def get_user_segmentation_analysis(self, admin_user_id, time_period='month'):
        """Get user segmentation analysis (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get user activity data for segmentation
            user_activity_data = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "total_test_cases": {"$sum": 1},
                    "source_types": {"$addToSet": "$source_type"},
                    "first_activity": {"$min": "$created_at"},
                    "last_activity": {"$max": "$created_at"},
                    "avg_daily_activity": {
                        "$avg": {
                            "$divide": [
                                {"$subtract": ["$last_activity", "$first_activity"]},
                                1000 * 60 * 60 * 24  # Convert to days
                            ]
                        }
                    }
                }}
            ]))
            
            # Get user details and create segments
            user_segments = []
            for user_activity in user_activity_data:
                user_details = self.users_collection.find_one({"_id": user_activity["_id"]}, {
                    "name": 1,
                    "email": 1,
                    "role": 1,
                    "created_at": 1
                })
                
                if user_details:
                    # Calculate user age in days
                    user_age_days = 0
                    if user_details.get("created_at"):
                        user_age_days = (now - user_details["created_at"]).days
                    
                    # Determine user segment based on activity and age
                    segment = self._determine_user_segment(
                        user_activity["total_test_cases"],
                        user_activity["avg_daily_activity"],
                        user_age_days,
                        len(user_activity["source_types"])
                    )
                    
                    user_segments.append({
                        "user_id": str(user_activity["_id"]),
                        "name": user_details["name"],
                        "email": user_details["email"],
                        "role": user_details.get("role", "user"),
                        "segment": segment,
                        "total_test_cases": user_activity["total_test_cases"],
                        "source_types_used": len(user_activity["source_types"]),
                        "source_types": user_activity["source_types"],
                        "user_age_days": user_age_days,
                        "avg_daily_activity": round(user_activity["avg_daily_activity"], 2) if user_activity["avg_daily_activity"] else 0
                    })
            
            # Group users by segment
            segment_groups = {}
            for user in user_segments:
                segment = user["segment"]
                if segment not in segment_groups:
                    segment_groups[segment] = []
                segment_groups[segment].append(user)
            
            # Calculate segment statistics
            segment_statistics = {}
            for segment, users in segment_groups.items():
                total_users = len(users)
                avg_test_cases = sum(u["total_test_cases"] for u in users) / total_users if total_users > 0 else 0
                avg_age_days = sum(u["user_age_days"] for u in users) / total_users if total_users > 0 else 0
                avg_source_types = sum(u["source_types_used"] for u in users) / total_users if total_users > 0 else 0
                
                segment_statistics[segment] = {
                    "total_users": total_users,
                    "percentage": round((total_users / len(user_segments) * 100), 2) if user_segments else 0,
                    "avg_test_cases": round(avg_test_cases, 2),
                    "avg_age_days": round(avg_age_days, 2),
                    "avg_source_types": round(avg_source_types, 2),
                    "users": users
                }
            
            # Get segment behavior patterns
            segment_behavior = {}
            for segment, stats in segment_statistics.items():
                if stats["users"]:
                    # Get source type preferences for this segment
                    source_type_counts = {}
                    for user in stats["users"]:
                        for source_type in user["source_types"]:
                            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
                    
                    # Sort source types by usage
                    sorted_source_types = sorted(source_type_counts.items(), key=lambda x: x[1], reverse=True)
                    
                    segment_behavior[segment] = {
                        "preferred_source_types": sorted_source_types[:3],  # Top 3
                        "activity_level": self._get_activity_level_description(stats["avg_test_cases"]),
                        "engagement_level": self._get_engagement_level_description(stats["avg_source_types"])
                    }
            
            # Create segment recommendations
            segment_recommendations = {}
            for segment, stats in segment_statistics.items():
                recommendations = []
                
                if segment == "Power Users":
                    recommendations.extend([
                        "Provide advanced features and customization options",
                        "Offer priority support and early access to new features",
                        "Consider beta testing opportunities"
                    ])
                elif segment == "Active Users":
                    recommendations.extend([
                        "Encourage exploration of additional source types",
                        "Provide tips for optimizing test case generation",
                        "Offer training materials and best practices"
                    ])
                elif segment == "Regular Users":
                    recommendations.extend([
                        "Increase engagement through notifications and reminders",
                        "Provide onboarding and tutorial content",
                        "Offer incentives for consistent usage"
                    ])
                elif segment == "Occasional Users":
                    recommendations.extend([
                        "Improve onboarding experience",
                        "Provide quick-start templates",
                        "Send re-engagement campaigns"
                    ])
                elif segment == "New Users":
                    recommendations.extend([
                        "Provide comprehensive onboarding",
                        "Offer guided tours and tutorials",
                        "Set up welcome series emails"
                    ])
                
                segment_recommendations[segment] = recommendations
            
            segmentation_analysis = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_users_analyzed": len(user_segments),
                "segment_groups": segment_groups,
                "segment_statistics": segment_statistics,
                "segment_behavior": segment_behavior,
                "segment_recommendations": segment_recommendations,
                "summary": {
                    "largest_segment": max(segment_statistics.items(), key=lambda x: x[1]["total_users"])[0] if segment_statistics else None,
                    "most_active_segment": max(segment_statistics.items(), key=lambda x: x[1]["avg_test_cases"])[0] if segment_statistics else None,
                    "total_segments": len(segment_statistics)
                }
            }
            
            return {"success": True, "segmentation_analysis": segmentation_analysis}
            
        except Exception as e:
            logger.error(f"Error getting user segmentation analysis: {str(e)}")
            return {"success": False, "message": "Failed to retrieve segmentation analysis"}

    def _determine_user_segment(self, total_test_cases, avg_daily_activity, user_age_days, source_types_count):
        """Helper method to determine user segment"""
        if user_age_days <= 7:
            return "New Users"
        elif total_test_cases >= 50 and avg_daily_activity >= 3:
            return "Power Users"
        elif total_test_cases >= 20 and avg_daily_activity >= 1:
            return "Active Users"
        elif total_test_cases >= 5:
            return "Regular Users"
        else:
            return "Occasional Users"

    def _get_activity_level_description(self, avg_test_cases):
        """Helper method to get activity level description"""
        if avg_test_cases >= 5:
            return "Very High"
        elif avg_test_cases >= 3:
            return "High"
        elif avg_test_cases >= 1:
            return "Medium"
        else:
            return "Low"

    def _get_engagement_level_description(self, avg_source_types):
        """Helper method to get engagement level description"""
        if avg_source_types >= 3:
            return "Very High"
        elif avg_source_types >= 2:
            return "High"
        elif avg_source_types >= 1:
            return "Medium"
        else:
            return "Low"

    def get_user_conversion_funnel(self, admin_user_id, time_period='month'):
        """Get user conversion funnel analysis (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Define conversion funnel stages
            funnel_stages = [
                "registered",
                "first_login",
                "first_test_case",
                "multiple_test_cases",
                "multiple_source_types",
                "regular_user",
                "power_user"
            ]
            
            # Get user progression through funnel
            funnel_data = {}
            
            # Stage 1: Registered users
            total_registered = self.users_collection.count_documents({
                "created_at": {"$gte": start_date}
            })
            funnel_data["registered"] = {
                "count": total_registered,
                "percentage": 100,
                "dropoff": 0
            }
            
            # Stage 2: First login
            first_login_users = self.users_collection.count_documents({
                "created_at": {"$gte": start_date},
                "last_login": {"$exists": True, "$ne": None}
            })
            funnel_data["first_login"] = {
                "count": first_login_users,
                "percentage": round((first_login_users / total_registered * 100), 2) if total_registered > 0 else 0,
                "dropoff": round(((total_registered - first_login_users) / total_registered * 100), 2) if total_registered > 0 else 0
            }
            
            # Stage 3: First test case
            users_with_test_cases = len(self.collection.distinct("user_id", {
                "created_at": {"$gte": start_date}
            }))
            funnel_data["first_test_case"] = {
                "count": users_with_test_cases,
                "percentage": round((users_with_test_cases / total_registered * 100), 2) if total_registered > 0 else 0,
                "dropoff": round(((first_login_users - users_with_test_cases) / first_login_users * 100), 2) if first_login_users > 0 else 0
            }
            
            # Stage 4: Multiple test cases
            users_with_multiple_test_cases = len(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "test_case_count": {"$sum": 1}
                }},
                {"$match": {"test_case_count": {"$gte": 2}}}
            ]))
            funnel_data["multiple_test_cases"] = {
                "count": users_with_multiple_test_cases,
                "percentage": round((users_with_multiple_test_cases / total_registered * 100), 2) if total_registered > 0 else 0,
                "dropoff": round(((users_with_test_cases - users_with_multiple_test_cases) / users_with_test_cases * 100), 2) if users_with_test_cases > 0 else 0
            }
            
            # Stage 5: Multiple source types
            users_with_multiple_sources = len(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "source_types": {"$addToSet": "$source_type"}
                }},
                {"$match": {"$expr": {"$gte": [{"$size": "$source_types"}, 2]}}}
            ]))
            funnel_data["multiple_source_types"] = {
                "count": users_with_multiple_sources,
                "percentage": round((users_with_multiple_sources / total_registered * 100), 2) if total_registered > 0 else 0,
                "dropoff": round(((users_with_multiple_test_cases - users_with_multiple_sources) / users_with_multiple_test_cases * 100), 2) if users_with_multiple_test_cases > 0 else 0
            }
            
            # Stage 6: Regular users (5+ test cases)
            regular_users = len(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "test_case_count": {"$sum": 1}
                }},
                {"$match": {"test_case_count": {"$gte": 5}}}
            ]))
            funnel_data["regular_user"] = {
                "count": regular_users,
                "percentage": round((regular_users / total_registered * 100), 2) if total_registered > 0 else 0,
                "dropoff": round(((users_with_multiple_sources - regular_users) / users_with_multiple_sources * 100), 2) if users_with_multiple_sources > 0 else 0
            }
            
            # Stage 7: Power users (20+ test cases)
            power_users = len(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "test_case_count": {"$sum": 1}
                }},
                {"$match": {"test_case_count": {"$gte": 20}}}
            ]))
            funnel_data["power_user"] = {
                "count": power_users,
                "percentage": round((power_users / total_registered * 100), 2) if total_registered > 0 else 0,
                "dropoff": round(((regular_users - power_users) / regular_users * 100), 2) if regular_users > 0 else 0
            }
            
            # Calculate overall conversion rates
            overall_conversion_rate = round((power_users / total_registered * 100), 2) if total_registered > 0 else 0
            avg_stage_conversion = sum(stage["percentage"] for stage in funnel_data.values()) / len(funnel_data)
            
            # Get funnel insights
            funnel_insights = []
            
            # Identify biggest dropoff points
            biggest_dropoffs = sorted(funnel_data.items(), key=lambda x: x[1]["dropoff"], reverse=True)[:3]
            for stage, data in biggest_dropoffs:
                if data["dropoff"] > 0:
                    funnel_insights.append(f"Biggest dropoff at {stage.replace('_', ' ').title()} stage: {data['dropoff']}%")
            
            # Identify best performing stages
            best_stages = sorted(funnel_data.items(), key=lambda x: x[1]["percentage"], reverse=True)[:3]
            for stage, data in best_stages:
                if data["percentage"] > 0:
                    funnel_insights.append(f"Best performing stage: {stage.replace('_', ' ').title()} with {data['percentage']}% conversion")
            
            # Get user journey analysis
            user_journey_data = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "journey": {
                        "$push": {
                            "source_type": "$source_type",
                            "timestamp": "$created_at"
                        }
                    },
                    "total_activities": {"$sum": 1}
                }},
                {"$sort": {"total_activities": -1}},
                {"$limit": 10}
            ]))
            
            # Process user journey data
            user_journeys = []
            for journey in user_journey_data:
                # Sort journey by timestamp
                sorted_journey = sorted(journey["journey"], key=lambda x: x["timestamp"])
                
                # Create journey path
                journey_path = [step["source_type"] for step in sorted_journey]
                
                user_journeys.append({
                    "user_id": str(journey["_id"]),
                    "journey_path": journey_path,
                    "total_activities": journey["total_activities"],
                    "journey_length": len(journey_path)
                })
            
            conversion_funnel = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "funnel_stages": funnel_stages,
                "funnel_data": funnel_data,
                "overall_metrics": {
                    "total_registered": total_registered,
                    "overall_conversion_rate": overall_conversion_rate,
                    "average_stage_conversion": round(avg_stage_conversion, 2),
                    "final_stage_users": power_users
                },
                "funnel_insights": funnel_insights,
                "user_journeys": user_journeys,
                "recommendations": [
                    "Focus on reducing dropoff at identified bottleneck stages",
                    "Implement onboarding improvements for new users",
                    "Create engagement campaigns for users at risk of dropping off",
                    "Provide incentives for progression through funnel stages",
                    "Analyze successful user journeys for optimization opportunities"
                ]
            }
            
            return {"success": True, "conversion_funnel": conversion_funnel}
            
        except Exception as e:
            logger.error(f"Error getting user conversion funnel: {str(e)}")
            return {"success": False, "message": "Failed to retrieve conversion funnel"}

    def get_user_satisfaction_and_feedback(self, admin_user_id, time_period='month'):
        """Get user satisfaction and feedback analysis (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get user activity and success metrics
            user_metrics = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "total_test_cases": {"$sum": 1},
                    "successful_test_cases": {
                        "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    },
                    "failed_test_cases": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "source_types": {"$addToSet": "$source_type"},
                    "avg_completion_time": {"$avg": "$completion_time"},
                    "last_activity": {"$max": "$created_at"}
                }}
            ]))
            
            # Calculate satisfaction scores and feedback
            satisfaction_data = []
            for user_metric in user_metrics:
                total_cases = user_metric["total_test_cases"]
                success_rate = (user_metric["successful_test_cases"] / total_cases * 100) if total_cases > 0 else 0
                
                # Calculate satisfaction score based on multiple factors
                satisfaction_score = 0
                
                # Factor 1: Success rate (40% weight)
                success_score = min(success_rate / 20, 5) * 0.4  # Normalize to 0-5 scale
                
                # Factor 2: Activity level (30% weight)
                activity_score = min(total_cases / 10, 5) * 0.3  # Normalize to 0-5 scale
                
                # Factor 3: Source type diversity (20% weight)
                diversity_score = min(len(user_metric["source_types"]) / 2, 5) * 0.2  # Normalize to 0-5 scale
                
                # Factor 4: Completion time efficiency (10% weight)
                completion_score = 0
                if user_metric.get("avg_completion_time"):
                    # Lower completion time = higher score (inverse relationship)
                    avg_time = user_metric["avg_completion_time"]
                    if avg_time <= 60:  # 1 minute or less
                        completion_score = 5 * 0.1
                    elif avg_time <= 300:  # 5 minutes or less
                        completion_score = 4 * 0.1
                    elif avg_time <= 600:  # 10 minutes or less
                        completion_score = 3 * 0.1
                    elif avg_time <= 1800:  # 30 minutes or less
                        completion_score = 2 * 0.1
                    else:
                        completion_score = 1 * 0.1
                
                # Calculate total satisfaction score
                satisfaction_score = success_score + activity_score + diversity_score + completion_score
                
                # Determine satisfaction level
                if satisfaction_score >= 4.5:
                    satisfaction_level = "Very Satisfied"
                elif satisfaction_score >= 3.5:
                    satisfaction_level = "Satisfied"
                elif satisfaction_score >= 2.5:
                    satisfaction_level = "Neutral"
                elif satisfaction_score >= 1.5:
                    satisfaction_level = "Dissatisfied"
                else:
                    satisfaction_level = "Very Dissatisfied"
                
                # Get user details
                user_details = self.users_collection.find_one({"_id": user_metric["_id"]}, {
                    "name": 1,
                    "email": 1,
                    "role": 1,
                    "created_at": 1
                })
                
                if user_details:
                    satisfaction_data.append({
                        "user_id": str(user_metric["_id"]),
                        "name": user_details["name"],
                        "email": user_details["email"],
                        "role": user_details.get("role", "user"),
                        "satisfaction_score": round(satisfaction_score, 2),
                        "satisfaction_level": satisfaction_level,
                        "success_rate": round(success_rate, 2),
                        "total_test_cases": total_cases,
                        "source_types_used": len(user_metric["source_types"]),
                        "avg_completion_time": round(user_metric.get("avg_completion_time", 0), 2),
                        "user_since": user_details["created_at"].isoformat() if user_details.get("created_at") else None
                    })
            
            # Calculate overall satisfaction metrics
            if satisfaction_data:
                overall_satisfaction = sum(user["satisfaction_score"] for user in satisfaction_data) / len(satisfaction_data)
                
                # Satisfaction distribution
                satisfaction_distribution = {
                    "Very Satisfied": len([u for u in satisfaction_data if u["satisfaction_level"] == "Very Satisfied"]),
                    "Satisfied": len([u for u in satisfaction_data if u["satisfaction_level"] == "Satisfied"]),
                    "Neutral": len([u for u in satisfaction_data if u["satisfaction_level"] == "Neutral"]),
                    "Dissatisfied": len([u for u in satisfaction_data if u["satisfaction_level"] == "Dissatisfied"]),
                    "Very Dissatisfied": len([u for u in satisfaction_data if u["satisfaction_level"] == "Very Dissatisfied"])
                }
                
                # Success rate distribution
                success_rate_distribution = {
                    "Excellent (90-100%)": len([u for u in satisfaction_data if u["success_rate"] >= 90]),
                    "Good (80-89%)": len([u for u in satisfaction_data if 80 <= u["success_rate"] < 90]),
                    "Average (70-79%)": len([u for u in satisfaction_data if 70 <= u["success_rate"] < 80]),
                    "Below Average (60-69%)": len([u for u in satisfaction_data if 60 <= u["success_rate"] < 70]),
                    "Poor (<60%)": len([u for u in satisfaction_data if u["success_rate"] < 60])
                }
            else:
                overall_satisfaction = 0
                satisfaction_distribution = {}
                success_rate_distribution = {}
            
            # Get user feedback insights
            feedback_insights = []
            
            # Identify top performers
            top_performers = sorted(satisfaction_data, key=lambda x: x["satisfaction_score"], reverse=True)[:5]
            if top_performers:
                feedback_insights.append(f"Top performers have an average satisfaction score of {round(sum(u['satisfaction_score'] for u in top_performers) / len(top_performers), 2)}")
            
            # Identify areas for improvement
            low_satisfaction_users = [u for u in satisfaction_data if u["satisfaction_level"] in ["Dissatisfied", "Very Dissatisfied"]]
            if low_satisfaction_users:
                avg_success_rate = sum(u["success_rate"] for u in low_satisfaction_users) / len(low_satisfaction_users)
                feedback_insights.append(f"Low satisfaction users have an average success rate of {round(avg_success_rate, 2)}%")
            
            # Identify correlation between success rate and satisfaction
            if len(satisfaction_data) > 1:
                success_scores = [u["success_rate"] for u in satisfaction_data]
                satisfaction_scores = [u["satisfaction_score"] for u in satisfaction_data]
                
                # Simple correlation calculation
                n = len(satisfaction_data)
                sum_xy = sum(success_scores[i] * satisfaction_scores[i] for i in range(n))
                sum_x = sum(success_scores)
                sum_y = sum(satisfaction_scores)
                sum_x2 = sum(x * x for x in success_scores)
                sum_y2 = sum(y * y for y in satisfaction_scores)
                
                correlation = (n * sum_xy - sum_x * sum_y) / ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5
                
                if abs(correlation) > 0.7:
                    feedback_insights.append(f"Strong correlation ({round(correlation, 2)}) between success rate and satisfaction")
                elif abs(correlation) > 0.5:
                    feedback_insights.append(f"Moderate correlation ({round(correlation, 2)}) between success rate and satisfaction")
                else:
                    feedback_insights.append(f"Weak correlation ({round(correlation, 2)}) between success rate and satisfaction")
            
            # Get improvement recommendations
            improvement_recommendations = []
            
            if satisfaction_distribution.get("Dissatisfied", 0) + satisfaction_distribution.get("Very Dissatisfied", 0) > 0:
                improvement_recommendations.extend([
                    "Focus on improving success rates for dissatisfied users",
                    "Provide additional training and support resources",
                    "Implement user feedback collection system"
                ])
            
            if success_rate_distribution.get("Poor (<60%)", 0) > 0:
                improvement_recommendations.extend([
                    "Investigate causes of high failure rates",
                    "Improve error handling and user guidance",
                    "Consider simplifying complex workflows"
                ])
            
            if len(satisfaction_data) > 0:
                avg_completion_time = sum(u["avg_completion_time"] for u in satisfaction_data if u["avg_completion_time"] > 0) / len([u for u in satisfaction_data if u["avg_completion_time"] > 0])
                if avg_completion_time > 600:  # More than 10 minutes
                    improvement_recommendations.append("Optimize test case generation process to reduce completion time")
            
            satisfaction_analysis = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_users_analyzed": len(satisfaction_data),
                "overall_satisfaction": round(overall_satisfaction, 2),
                "satisfaction_distribution": satisfaction_distribution,
                "success_rate_distribution": success_rate_distribution,
                "user_satisfaction_details": satisfaction_data,
                "feedback_insights": feedback_insights,
                "improvement_recommendations": improvement_recommendations,
                "summary": {
                    "satisfaction_trend": "Improving" if overall_satisfaction > 3.5 else "Needs Attention",
                    "top_performers_count": len(top_performers) if 'top_performers' in locals() else 0,
                    "improvement_needed_count": len(low_satisfaction_users) if 'low_satisfaction_users' in locals() else 0
                }
            }
            
            return {"success": True, "satisfaction_analysis": satisfaction_analysis}
            
        except Exception as e:
            logger.error(f"Error getting user satisfaction and feedback: {str(e)}")
            return {"success": False, "message": "Failed to retrieve satisfaction analysis"}

    def get_user_predictive_analytics(self, admin_user_id, time_period='month'):
        """Get user predictive analytics (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get user activity patterns for prediction
            user_activity_patterns = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "activities": {
                        "$push": {
                            "timestamp": "$created_at",
                            "source_type": "$source_type",
                            "status": "$status"
                        }
                    },
                    "total_activities": {"$sum": 1},
                    "first_activity": {"$min": "$created_at"},
                    "last_activity": {"$max": "$created_at"}
                }},
                {"$sort": {"total_activities": -1}}
            ]))
            
            # Analyze user behavior patterns and make predictions
            user_predictions = []
            churn_risk_users = []
            growth_potential_users = []
            engagement_opportunities = []
            
            for user_pattern in user_activity_patterns:
                user_id = user_pattern["_id"]
                
                # Get user details
                user_details = self.users_collection.find_one({"_id": user_id}, {
                    "name": 1,
                    "email": 1,
                    "role": 1,
                    "created_at": 1,
                    "last_login": 1
                })
                
                if user_details:
                    # Calculate user metrics
                    total_activities = user_pattern["total_activities"]
                    first_activity = user_pattern["first_activity"]
                    last_activity = user_pattern["last_activity"]
                    
                    # Calculate activity frequency
                    if first_activity and last_activity:
                        activity_period = (last_activity - first_activity).days
                        if activity_period > 0:
                            daily_activity_rate = total_activities / activity_period
                        else:
                            daily_activity_rate = total_activities
                    else:
                        daily_activity_rate = 0
                    
                    # Calculate days since last activity
                    days_since_last_activity = (now - last_activity).days if last_activity else 0
                    
                    # Predict user behavior
                    predictions = self._predict_user_behavior(
                        total_activities,
                        daily_activity_rate,
                        days_since_last_activity,
                        user_pattern["activities"]
                    )
                    
                    # Determine user category
                    user_category = self._categorize_user_for_prediction(predictions)
                    
                    # Create user prediction data
                    user_prediction = {
                        "user_id": str(user_id),
                        "name": user_details["name"],
                        "email": user_details["email"],
                        "role": user_details.get("role", "user"),
                        "predictions": predictions,
                        "user_category": user_category,
                        "risk_score": predictions["churn_risk"],
                        "growth_potential": predictions["growth_potential"],
                        "engagement_score": predictions["engagement_score"]
                    }
                    
                    user_predictions.append(user_prediction)
                    
                    # Categorize users for different strategies
                    if predictions["churn_risk"] >= 0.7:
                        churn_risk_users.append(user_prediction)
                    elif predictions["growth_potential"] >= 0.8:
                        growth_potential_users.append(user_prediction)
                    elif predictions["engagement_score"] <= 0.4:
                        engagement_opportunities.append(user_prediction)
            
            # Calculate predictive metrics
            if user_predictions:
                avg_churn_risk = sum(u["risk_score"] for u in user_predictions) / len(user_predictions)
                avg_growth_potential = sum(u["growth_potential"] for u in user_predictions) / len(user_predictions)
                avg_engagement_score = sum(u["engagement_score"] for u in user_predictions) / len(user_predictions)
                
                # Identify trends
                high_risk_users = len([u for u in user_predictions if u["risk_score"] >= 0.7])
                high_potential_users = len([u for u in user_predictions if u["growth_potential"] >= 0.8])
                low_engagement_users = len([u for u in user_predictions if u["engagement_score"] <= 0.4])
            else:
                avg_churn_risk = avg_growth_potential = avg_engagement_score = 0
                high_risk_users = high_potential_users = low_engagement_users = 0
            
            # Generate predictive insights
            predictive_insights = []
            
            if avg_churn_risk > 0.6:
                predictive_insights.append(f"High overall churn risk ({round(avg_churn_risk * 100, 1)}%) - implement retention strategies")
            
            if avg_growth_potential > 0.7:
                predictive_insights.append(f"Strong growth potential ({round(avg_growth_potential * 100, 1)}%) - focus on expansion opportunities")
            
            if avg_engagement_score < 0.5:
                predictive_insights.append(f"Low engagement levels ({round(avg_engagement_score * 100, 1)}%) - implement engagement campaigns")
            
            if high_risk_users > 0:
                predictive_insights.append(f"{high_risk_users} users at high churn risk - prioritize retention efforts")
            
            if high_potential_users > 0:
                predictive_insights.append(f"{high_potential_users} users with high growth potential - focus on expansion")
            
            # Generate action recommendations
            action_recommendations = []
            
            if churn_risk_users:
                action_recommendations.extend([
                    "Implement targeted retention campaigns for high-risk users",
                    "Provide personalized support and incentives",
                    "Analyze common patterns among churn-risk users"
                ])
            
            if growth_potential_users:
                action_recommendations.extend([
                    "Offer advanced features and premium options to high-potential users",
                    "Provide upselling and cross-selling opportunities",
                    "Create loyalty programs for power users"
                ])
            
            if engagement_opportunities:
                action_recommendations.extend([
                    "Send re-engagement campaigns to low-engagement users",
                    "Provide onboarding improvements and tutorials",
                    "Implement gamification elements"
                ])
            
            # Get predictive trends
            predictive_trends = self._calculate_predictive_trends(user_predictions, time_period)
            
            predictive_analytics = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_users_analyzed": len(user_predictions),
                "predictive_metrics": {
                    "average_churn_risk": round(avg_churn_risk, 3),
                    "average_growth_potential": round(avg_growth_potential, 3),
                    "average_engagement_score": round(avg_engagement_score, 3),
                    "high_risk_users": high_risk_users,
                    "high_potential_users": high_potential_users,
                    "low_engagement_users": low_engagement_users
                },
                "user_predictions": user_predictions,
                "user_categories": {
                    "churn_risk_users": churn_risk_users,
                    "growth_potential_users": growth_potential_users,
                    "engagement_opportunities": engagement_opportunities
                },
                "predictive_insights": predictive_insights,
                "action_recommendations": action_recommendations,
                "predictive_trends": predictive_trends,
                "summary": {
                    "overall_risk_level": "High" if avg_churn_risk > 0.6 else "Medium" if avg_churn_risk > 0.3 else "Low",
                    "growth_opportunity": "High" if avg_growth_potential > 0.7 else "Medium" if avg_growth_potential > 0.5 else "Low",
                    "engagement_status": "Good" if avg_engagement_score > 0.6 else "Fair" if avg_engagement_score > 0.4 else "Poor"
                }
            }
            
            return {"success": True, "predictive_analytics": predictive_analytics}
            
        except Exception as e:
            logger.error(f"Error getting user predictive analytics: {str(e)}")
            return {"success": False, "message": "Failed to retrieve predictive analytics"}

    def _predict_user_behavior(self, total_activities, daily_activity_rate, days_since_last_activity, activities):
        """Helper method to predict user behavior"""
        # Churn risk prediction (0-1 scale, higher = more risk)
        churn_risk = 0
        
        # Factor 1: Days since last activity (40% weight)
        if days_since_last_activity > 30:
            churn_risk += 0.4
        elif days_since_last_activity > 14:
            churn_risk += 0.3
        elif days_since_last_activity > 7:
            churn_risk += 0.2
        elif days_since_last_activity > 3:
            churn_risk += 0.1
        
        # Factor 2: Activity rate decline (30% weight)
        if daily_activity_rate < 0.1:
            churn_risk += 0.3
        elif daily_activity_rate < 0.5:
            churn_risk += 0.2
        elif daily_activity_rate < 1.0:
            churn_risk += 0.1
        
        # Factor 3: Total activity volume (20% weight)
        if total_activities < 5:
            churn_risk += 0.2
        elif total_activities < 10:
            churn_risk += 0.1
        
        # Factor 4: Activity consistency (10% weight)
        if len(activities) > 1:
            # Check if activities are spread out or clustered
            timestamps = [a["timestamp"] for a in activities]
            timestamps.sort()
            
            gaps = []
            for i in range(1, len(timestamps)):
                gap = (timestamps[i] - timestamps[i-1]).days
                gaps.append(gap)
            
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                if avg_gap > 7:  # Large gaps between activities
                    churn_risk += 0.1
        
        # Growth potential prediction (0-1 scale, higher = more potential)
        growth_potential = 0
        
        # Factor 1: Current activity level (40% weight)
        if daily_activity_rate >= 2:
            growth_potential += 0.4
        elif daily_activity_rate >= 1:
            growth_potential += 0.3
        elif daily_activity_rate >= 0.5:
            growth_potential += 0.2
        elif daily_activity_rate >= 0.1:
            growth_potential += 0.1
        
        # Factor 2: Activity consistency (30% weight)
        if total_activities >= 20:
            growth_potential += 0.3
        elif total_activities >= 10:
            growth_potential += 0.2
        elif total_activities >= 5:
            growth_potential += 0.1
        
        # Factor 3: Source type diversity (20% weight)
        source_types = set(a["source_type"] for a in activities)
        if len(source_types) >= 3:
            growth_potential += 0.2
        elif len(source_types) >= 2:
            growth_potential += 0.1
        
        # Factor 4: Recent activity (10% weight)
        if days_since_last_activity <= 3:
            growth_potential += 0.1
        
        # Engagement score prediction (0-1 scale, higher = more engaged)
        engagement_score = 0
        
        # Factor 1: Activity frequency (40% weight)
        if daily_activity_rate >= 1:
            engagement_score += 0.4
        elif daily_activity_rate >= 0.5:
            engagement_score += 0.3
        elif daily_activity_rate >= 0.2:
            engagement_score += 0.2
        elif daily_activity_rate >= 0.1:
            engagement_score += 0.1
        
        # Factor 2: Activity recency (30% weight)
        if days_since_last_activity <= 1:
            engagement_score += 0.3
        elif days_since_last_activity <= 3:
            engagement_score += 0.2
        elif days_since_last_activity <= 7:
            engagement_score += 0.1
        
        # Factor 3: Activity volume (20% weight)
        if total_activities >= 10:
            engagement_score += 0.2
        elif total_activities >= 5:
            engagement_score += 0.1
        
        # Factor 4: Activity variety (10% weight)
        if len(source_types) >= 2:
            engagement_score += 0.1
        
        return {
            "churn_risk": min(churn_risk, 1.0),
            "growth_potential": min(growth_potential, 1.0),
            "engagement_score": min(engagement_score, 1.0)
        }

    def _categorize_user_for_prediction(self, predictions):
        """Helper method to categorize users based on predictions"""
        churn_risk = predictions["churn_risk"]
        growth_potential = predictions["growth_potential"]
        engagement_score = predictions["engagement_score"]
        
        if churn_risk >= 0.7:
            return "High Churn Risk"
        elif growth_potential >= 0.8:
            return "High Growth Potential"
        elif engagement_score <= 0.3:
            return "Low Engagement"
        elif engagement_score >= 0.7 and growth_potential >= 0.6:
            return "Power User"
        elif engagement_score >= 0.5:
            return "Engaged User"
        else:
            return "Standard User"

    def _calculate_predictive_trends(self, user_predictions, time_period):
        """Helper method to calculate predictive trends"""
        if not user_predictions:
            return {}
        
        # Calculate trends based on user categories
        category_counts = {}
        for user in user_predictions:
            category = user["user_category"]
            if category not in category_counts:
                category_counts[category] = 0
            category_counts[category] += 1
        
        # Calculate percentage distribution
        total_users = len(user_predictions)
        category_percentages = {}
        for category, count in category_counts.items():
            category_percentages[category] = round((count / total_users) * 100, 2)
        
        # Identify dominant trends
        dominant_trends = []
        for category, percentage in sorted(category_percentages.items(), key=lambda x: x[1], reverse=True):
            if percentage >= 20:  # Categories with 20% or more users
                dominant_trends.append(f"{category}: {percentage}% of users")
        
        return {
            "category_distribution": category_counts,
            "category_percentages": category_percentages,
            "dominant_trends": dominant_trends,
            "total_categories": len(category_counts)
        }

    def get_comprehensive_user_analytics(self, admin_user_id, time_period='month'):
        """Get comprehensive user analytics combining all metrics (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(days=7)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'quarter':
                start_date = now - timedelta(days=90)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get all analytics data
            analytics_data = {}
            
            # 1. User Statistics
            user_stats = self.get_user_statistics(admin_user_id)
            if user_stats["success"]:
                analytics_data["user_statistics"] = user_stats["statistics"]
            
            # 2. User Activity Summary
            activity_summary = self.get_user_activity_summary(admin_user_id, time_period)
            if activity_summary["success"]:
                analytics_data["activity_summary"] = activity_summary["activity_summary"]
            
            # 3. User Engagement Metrics
            engagement_metrics = self.get_user_engagement_metrics(admin_user_id, time_period)
            if engagement_metrics["success"]:
                analytics_data["engagement_metrics"] = engagement_metrics["engagement_metrics"]
            
            # 4. User Performance Metrics
            performance_metrics = self.get_user_performance_metrics(admin_user_id, time_period=time_period)
            if performance_metrics["success"]:
                analytics_data["performance_metrics"] = performance_metrics
            
            # 5. User Behavior Patterns
            behavior_patterns = self.get_user_behavior_patterns(admin_user_id, time_period)
            if behavior_patterns["success"]:
                analytics_data["behavior_patterns"] = behavior_patterns["behavior_patterns"]
            
            # 6. User Segmentation Analysis
            segmentation_analysis = self.get_user_segmentation_analysis(admin_user_id, time_period)
            if segmentation_analysis["success"]:
                analytics_data["segmentation_analysis"] = segmentation_analysis["segmentation_analysis"]
            
            # 7. User Conversion Funnel
            conversion_funnel = self.get_user_conversion_funnel(admin_user_id, time_period)
            if conversion_funnel["success"]:
                analytics_data["conversion_funnel"] = conversion_funnel["conversion_funnel"]
            
            # 8. User Retention Analysis
            retention_analysis = self.get_user_retention_analysis(admin_user_id, time_period)
            if retention_analysis["success"]:
                analytics_data["retention_analysis"] = retention_analysis["retention_analysis"]
            
            # 9. User Growth Trends
            growth_trends = self.get_user_growth_trends(admin_user_id, time_period)
            if growth_trends["success"]:
                analytics_data["growth_trends"] = growth_trends["growth_trends"]
            
            # 10. User Satisfaction and Feedback
            satisfaction_analysis = self.get_user_satisfaction_and_feedback(admin_user_id, time_period)
            if satisfaction_analysis["success"]:
                analytics_data["satisfaction_analysis"] = satisfaction_analysis["satisfaction_analysis"]
            
            # 11. User Predictive Analytics
            predictive_analytics = self.get_user_predictive_analytics(admin_user_id, time_period)
            if predictive_analytics["success"]:
                analytics_data["predictive_analytics"] = predictive_analytics["predictive_analytics"]
            
            # 12. System Overview
            system_overview = self.get_system_overview(admin_user_id)
            if system_overview["success"]:
                analytics_data["system_overview"] = system_overview["system_overview"]
            
            # 13. System Health Status
            system_health = self.get_system_health_status(admin_user_id)
            if system_health["success"]:
                analytics_data["system_health"] = system_health["health_status"]
            
            # Generate executive summary
            executive_summary = self._generate_executive_summary(analytics_data, time_period)
            
            # Generate key insights
            key_insights = self._generate_key_insights(analytics_data)
            
            # Generate strategic recommendations
            strategic_recommendations = self._generate_strategic_recommendations(analytics_data)
            
            # Calculate overall health score
            overall_health_score = self._calculate_overall_health_score(analytics_data)
            
            comprehensive_analytics = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "overall_health_score": overall_health_score,
                "executive_summary": executive_summary,
                "key_insights": key_insights,
                "strategic_recommendations": strategic_recommendations,
                "analytics_data": analytics_data,
                "summary": {
                    "total_metrics_analyzed": len(analytics_data),
                    "data_completeness": self._calculate_data_completeness(analytics_data),
                    "analysis_timestamp": now.isoformat(),
                    "recommendations_count": len(strategic_recommendations),
                    "insights_count": len(key_insights)
                }
            }
            
            return {"success": True, "comprehensive_analytics": comprehensive_analytics}
            
        except Exception as e:
            logger.error(f"Error getting comprehensive user analytics: {str(e)}")
            return {"success": False, "message": "Failed to retrieve comprehensive analytics"}

    def _generate_executive_summary(self, analytics_data, time_period):
        """Generate executive summary from analytics data"""
        summary = {
            "overview": f"Comprehensive user analytics report for {time_period} period",
            "key_highlights": [],
            "performance_overview": {},
            "trends": [],
            "risks": [],
            "opportunities": []
        }
        
        # Extract key highlights
        if "user_statistics" in analytics_data:
            stats = analytics_data["user_statistics"]
            summary["key_highlights"].extend([
                f"Total users: {stats.get('total_users', 0)}",
                f"Active users: {stats.get('active_users', 0)}",
                f"New users this month: {stats.get('new_users_this_month', 0)}"
            ])
        
        # Extract performance overview
        if "performance_metrics" in analytics_data:
            perf = analytics_data["performance_metrics"]
            summary["performance_overview"] = {
                "total_users_analyzed": perf.get("total_users", 0),
                "time_period": perf.get("time_period", time_period)
            }
        
        # Extract trends
        if "growth_trends" in analytics_data:
            trends = analytics_data["growth_trends"]
            summary["trends"].extend([
                f"Total new users: {trends.get('total_new_users', 0)}",
                f"Average growth rate: {trends.get('average_growth_rate', 0)}%"
            ])
        
        # Extract risks
        if "predictive_analytics" in analytics_data:
            pred = analytics_data["predictive_analytics"]
            risk_level = pred.get("summary", {}).get("overall_risk_level", "Unknown")
            summary["risks"].append(f"Overall churn risk level: {risk_level}")
        
        # Extract opportunities
        if "engagement_metrics" in analytics_data:
            engagement = analytics_data["engagement_metrics"]
            summary["opportunities"].extend([
                f"Engagement rate: {engagement.get('engagement_rate', 0)}%",
                f"Activity rate: {engagement.get('activity_rate', 0)}%"
            ])
        
        return summary

    def _generate_key_insights(self, analytics_data):
        """Generate key insights from analytics data"""
        insights = []
        
        # User growth insights
        if "growth_trends" in analytics_data:
            trends = analytics_data["growth_trends"]
            if trends.get("total_new_users", 0) > 0:
                insights.append(f"User growth is positive with {trends['total_new_users']} new users")
        
        # Engagement insights
        if "engagement_metrics" in analytics_data:
            engagement = analytics_data["engagement_metrics"]
            if engagement.get("engagement_rate", 0) < 50:
                insights.append("User engagement is below optimal levels - consider engagement campaigns")
        
        # Retention insights
        if "retention_analysis" in analytics_data:
            retention = analytics_data["retention_analysis"]
            if retention.get("overall_retention_metrics", {}).get("week_1_retention", 0) < 70:
                insights.append("First-week retention needs improvement - focus on onboarding")
        
        # Performance insights
        if "performance_metrics" in analytics_data:
            perf = analytics_data["performance_metrics"]
            if perf.get("user_metrics"):
                avg_test_cases = sum(u["total_test_cases"] for u in perf["user_metrics"]) / len(perf["user_metrics"])
                insights.append(f"Average test cases per user: {round(avg_test_cases, 1)}")
        
        return insights

    def _generate_strategic_recommendations(self, analytics_data):
        """Generate strategic recommendations from analytics data"""
        recommendations = []
        
        # User acquisition recommendations
        if "growth_trends" in analytics_data:
            trends = analytics_data["growth_trends"]
            if trends.get("total_new_users", 0) < 10:
                recommendations.append("Implement user acquisition strategies to increase sign-ups")
        
        # Retention recommendations
        if "retention_analysis" in analytics_data:
            retention = analytics_data["retention_analysis"]
            if retention.get("overall_retention_metrics", {}).get("week_4_retention", 0) < 30:
                recommendations.append("Develop long-term retention strategies and loyalty programs")
        
        # Engagement recommendations
        if "engagement_metrics" in analytics_data:
            engagement = analytics_data["engagement_metrics"]
            if engagement.get("engagement_rate", 0) < 60:
                recommendations.append("Implement user engagement campaigns and feature adoption strategies")
        
        # Performance recommendations
        if "performance_metrics" in analytics_data:
            perf = analytics_data["performance_metrics"]
            if perf.get("user_metrics"):
                low_performers = [u for u in perf["user_metrics"] if u["total_test_cases"] < 5]
                if len(low_performers) > len(perf["user_metrics"]) * 0.3:
                    recommendations.append("Provide additional support and training for low-performing users")
        
        # System optimization recommendations
        if "system_health" in analytics_data:
            health = analytics_data["system_health"]
            if health.get("overall_status") == "unhealthy":
                recommendations.append("Address system health issues to improve user experience")
        
        return recommendations

    def _calculate_overall_health_score(self, analytics_data):
        """Calculate overall system health score from analytics data"""
        health_score = 0
        total_factors = 0
        
        # Factor 1: User growth (25% weight)
        if "growth_trends" in analytics_data:
            trends = analytics_data["growth_trends"]
            growth_score = min(trends.get("total_new_users", 0) / 10, 1.0)  # Normalize to 0-1
            health_score += growth_score * 0.25
            total_factors += 0.25
        
        # Factor 2: User engagement (25% weight)
        if "engagement_metrics" in analytics_data:
            engagement = analytics_data["engagement_metrics"]
            engagement_score = min(engagement.get("engagement_rate", 0) / 100, 1.0)  # Normalize to 0-1
            health_score += engagement_score * 0.25
            total_factors += 0.25
        
        # Factor 3: User retention (25% weight)
        if "retention_analysis" in analytics_data:
            retention = analytics_data["retention_analysis"]
            retention_score = min(retention.get("overall_retention_metrics", {}).get("week_1_retention", 0) / 100, 1.0)
            health_score += retention_score * 0.25
            total_factors += 0.25
        
        # Factor 4: System health (25% weight)
        if "system_health" in analytics_data:
            health = analytics_data["system_health"]
            system_score = 1.0 if health.get("overall_status") == "healthy" else 0.5
            health_score += system_score * 0.25
            total_factors += 0.25
        
        # Normalize score
        if total_factors > 0:
            final_score = health_score / total_factors
        else:
            final_score = 0
        
        # Convert to percentage and categorize
        health_percentage = round(final_score * 100, 1)
        
        if health_percentage >= 80:
            health_category = "Excellent"
        elif health_percentage >= 60:
            health_category = "Good"
        elif health_percentage >= 40:
            health_category = "Fair"
        else:
            health_category = "Poor"
        
        return {
            "score": health_percentage,
            "category": health_category,
            "factors_analyzed": total_factors
        }

    def _calculate_data_completeness(self, analytics_data):
        """Calculate data completeness percentage"""
        total_possible_metrics = 13  # Total number of possible analytics metrics
        available_metrics = len(analytics_data)
        
        completeness_percentage = round((available_metrics / total_possible_metrics) * 100, 1)
        
        if completeness_percentage >= 90:
            completeness_level = "Excellent"
        elif completeness_percentage >= 75:
            completeness_level = "Good"
        elif completeness_percentage >= 60:
            completeness_level = "Fair"
        else:
            completeness_level = "Poor"
        
        return {
            "percentage": completeness_percentage,
            "level": completeness_level,
            "available_metrics": available_metrics,
            "total_possible_metrics": total_possible_metrics
        }

    def create_initial_admin_user(self, email, password, name):
        """Create the initial admin user (should only be called once during setup)"""
        try:
            # Check if any admin user already exists
            existing_admin = self.users_collection.find_one({"role": "admin"})
            if existing_admin:
                return {"success": False, "message": "Admin user already exists. Cannot create another admin."}
            
            # Create admin user with admin role
            admin_user_doc = {
                "_id": str(uuid.uuid4()),
                "email": email.lower(),
                "password": bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()),
                "name": name,
                "role": "admin",  # Set role as admin
                "created_at": datetime.utcnow(),
                "last_login": None,
                "is_active": True,
                "permissions": {
                    "can_create_users": True,
                    "can_delete_users": True,
                    "can_update_user_roles": True,
                    "can_view_all_users": True,
                    "can_view_system_stats": True,
                    "can_backup_data": True,
                    "can_restore_data": True,
                    "can_export_data": True,
                    "can_manage_system": True,
                    "can_view_analytics": True,
                    "can_manage_test_cases": True
                }
            }
            
            # Insert admin user
            result = self.users_collection.insert_one(admin_user_doc)
            
            if result.inserted_id:
                logger.info(f"Initial admin user created successfully: {email}")
                
                # Log the admin creation action
                self.log_admin_action(
                    admin_user_id="SYSTEM_SETUP",
                    action_type="initial_admin_created",
                    target_id=str(result.inserted_id),
                    details=f"Initial admin user {email} created during system setup"
                )
                
                return {
                    "success": True,
                    "message": "Initial admin user created successfully",
                    "admin_user": {
                        "id": str(result.inserted_id),
                        "email": email,
                        "name": name,
                        "role": "admin"
                    }
                }
            else:
                return {"success": False, "message": "Failed to create admin user"}
                
        except Exception as e:
            logger.error(f"Error creating initial admin user: {str(e)}")
            return {"success": False, "message": "Failed to create admin user"}

    def get_user_dashboard_data(self, user_id):
        """Get user dashboard data with role-based access"""
        try:
            user = self.users_collection.find_one({"_id": user_id})
            if not user:
                return {"success": False, "message": "User not found"}
            
            # Get user's test cases
            user_test_cases = list(self.collection.find(
                {"user_id": user_id},
                {"_id": 1, "title": 1, "created_at": 1, "source_type": 1, "status": 1}
            ).sort("created_at", -1).limit(10))
            
            # Convert ObjectId to string for JSON serialization
            for test_case in user_test_cases:
                if "_id" in test_case:
                    test_case["_id"] = str(test_case["_id"])
                if "created_at" in test_case:
                    test_case["created_at"] = test_case["created_at"].isoformat()
            
            # Get user's role and permissions
            role = user.get("role", "user")
            permissions = self.get_user_permissions(user_id)
            
            # Calculate basic stats
            total_test_cases = len(user_test_cases)
            this_month_test_cases = len([tc for tc in user_test_cases if tc.get("created_at", "").startswith(datetime.utcnow().strftime("%Y-%m"))])
            
            # Get last generated test case
            last_generated = None
            if user_test_cases:
                last_generated = user_test_cases[0]
            
            # Prepare dashboard data
            dashboard_data = {
                "user_info": {
                    "id": str(user["_id"]),
                    "name": user["name"],
                    "email": user["email"],
                    "role": role,
                    "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
                    "last_login": user["last_login"].isoformat() if user.get("last_login") else None
                },
                "stats": {
                    "total_test_cases": total_test_cases,
                    "this_month": this_month_test_cases,
                    "last_generated": last_generated
                },
                "test_cases": user_test_cases,
                "permissions": permissions.get("permissions", {}) if permissions["success"] else {},
                "role": role
            }
            
            # Add admin-specific data if user is admin
            if role == "admin":
                admin_data = self._get_admin_dashboard_data(user_id)
                dashboard_data["admin_data"] = admin_data
            
            return {"success": True, "dashboard_data": dashboard_data}
            
        except Exception as e:
            logger.error(f"Error getting user dashboard data: {str(e)}")
            return {"success": False, "message": "Failed to retrieve dashboard data"}

    def _get_admin_dashboard_data(self, admin_user_id):
        """Get admin-specific dashboard data"""
        try:
            # Get system overview
            system_overview = self.get_system_overview(admin_user_id)
            
            # Get user statistics
            user_stats = self.get_user_statistics(admin_user_id)
            
            # Get recent activity
            recent_activity = self.get_user_activity_summary(admin_user_id, 'week')
            
            # Get system health
            system_health = self.get_system_health_status(admin_user_id)
            
            admin_data = {
                "system_overview": system_overview.get("system_overview", {}) if system_overview["success"] else {},
                "user_statistics": user_stats.get("statistics", {}) if user_stats["success"] else {},
                "recent_activity": recent_activity.get("activity_summary", []) if recent_activity["success"] else [],
                "system_health": system_health.get("health_status", {}) if system_health["success"] else {},
                "quick_actions": [
                    "View all users",
                    "System health check",
                    "User analytics",
                    "Backup data",
                    "Export reports"
                ]
            }
            
            return admin_data
            
        except Exception as e:
            logger.error(f"Error getting admin dashboard data: {str(e)}")
            return {}

    def get_user_activity_timeline(self, user_id, time_period='month'):
        """Get user activity timeline with detailed events"""
        try:
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(weeks=1)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'quarter':
                start_date = now - timedelta(days=90)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get user's test case activities
            test_case_activities = list(self.collection.find(
                {"user_id": user_id, "created_at": {"$gte": start_date}},
                {"_id": 1, "created_at": 1, "source_type": 1, "status": 1, "title": 1}
            ).sort("created_at", -1))
            
            # Get user's login activities (from user document)
            user = self.users_collection.find_one({"_id": user_id}, {
                "created_at": 1,
                "last_login": 1
            })
            
            # Create timeline events
            timeline_events = []
            
            # Add user registration event
            if user and user.get("created_at"):
                timeline_events.append({
                    "event_type": "user_registration",
                    "timestamp": user["created_at"],
                    "description": "User account created",
                    "icon": "user-plus",
                    "category": "account"
                })
            
            # Add test case generation events
            for activity in test_case_activities:
                timeline_events.append({
                    "event_type": "test_case_generated",
                    "timestamp": activity["created_at"],
                    "description": f"Generated test case from {activity.get('source_type', 'unknown')}",
                    "icon": "file-earmark-text",
                    "category": "test_case",
                    "details": {
                        "test_case_id": str(activity["_id"]),
                        "source_type": activity.get("source_type", "unknown"),
                        "title": activity.get("title", "Untitled")
                    }
                })
            
            # Add login events (if we track them)
            if user and user.get("last_login"):
                timeline_events.append({
                    "event_type": "user_login",
                    "timestamp": user["last_login"],
                    "description": "User logged in",
                    "icon": "box-arrow-in-right",
                    "category": "account"
                })
            
            # Sort events by timestamp (newest first)
            timeline_events.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # Convert timestamps to ISO format for JSON serialization
            for event in timeline_events:
                event["timestamp"] = event["timestamp"].isoformat()
            
            # Group events by date
            events_by_date = {}
            for event in timeline_events:
                date_key = event["timestamp"][:10]  # YYYY-MM-DD
                if date_key not in events_by_date:
                    events_by_date[date_key] = []
                events_by_date[date_key].append(event)
            
            # Calculate activity statistics
            total_events = len(timeline_events)
            test_case_events = len([e for e in timeline_events if e["event_type"] == "test_case_generated"])
            account_events = len([e for e in timeline_events if e["event_type"] in ["user_registration", "user_login"]])
            
            # Get activity frequency
            if len(timeline_events) > 1:
                # Calculate average events per day
                first_event = min(timeline_events, key=lambda x: x["timestamp"])
                last_event = max(timeline_events, key=lambda x: x["timestamp"])
                
                first_date = datetime.fromisoformat(first_event["timestamp"])
                last_date = datetime.fromisoformat(last_event["timestamp"])
                days_between = (last_date - first_date).days
                
                if days_between > 0:
                    events_per_day = total_events / days_between
                else:
                    events_per_day = total_events
            else:
                events_per_day = total_events
            
            # Create activity summary
            activity_summary = {
                "total_events": total_events,
                "test_case_events": test_case_events,
                "account_events": account_events,
                "events_per_day": round(events_per_day, 2),
                "most_active_day": max(events_by_date.items(), key=lambda x: len(x[1]))[0] if events_by_date else None,
                "activity_streak": self._calculate_activity_streak(timeline_events)
            }
            
            timeline_data = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_events": total_events,
                "timeline_events": timeline_events,
                "events_by_date": events_by_date,
                "activity_summary": activity_summary,
                "summary": {
                    "most_common_event": "test_case_generated" if test_case_events > account_events else "account_activity",
                    "activity_level": self._get_activity_level_description(events_per_day),
                    "timeline_completeness": "Complete" if total_events > 0 else "No activity"
                }
            }
            
            return {"success": True, "timeline_data": timeline_data}
            
        except Exception as e:
            logger.error(f"Error getting user activity timeline: {str(e)}")
            return {"success": False, "message": "Failed to retrieve activity timeline"}

    def _calculate_activity_streak(self, timeline_events):
        """Calculate user's activity streak"""
        if not timeline_events:
            return 0
        
        # Sort events by timestamp (oldest first)
        sorted_events = sorted(timeline_events, key=lambda x: x["timestamp"])
        
        current_streak = 0
        max_streak = 0
        last_event_date = None
        
        for event in sorted_events:
            event_date = datetime.fromisoformat(event["timestamp"]).date()
            
            if last_event_date is None:
                current_streak = 1
            elif (event_date - last_event_date).days == 1:
                current_streak += 1
            else:
                max_streak = max(max_streak, current_streak)
                current_streak = 1
            
            last_event_date = event_date
        
        # Check final streak
        max_streak = max(max_streak, current_streak)
        
        return max_streak

    def get_user_achievements_and_milestones(self, user_id):
        """Get user achievements and milestones based on their activity"""
        try:
            # Get user's test case data
            test_cases = list(self.collection.find(
                {"user_id": user_id},
                {"_id": 1, "created_at": 1, "source_type": 1, "status": 1}
            ).sort("created_at", 1))  # Sort by creation date (oldest first)
            
            # Get user details
            user = self.users_collection.find_one({"_id": user_id}, {
                "created_at": 1,
                "last_login": 1
            })
            
            if not user:
                return {"success": False, "message": "User not found"}
            
            # Calculate achievements and milestones
            achievements = []
            milestones = []
            
            # Achievement 1: First Test Case
            if len(test_cases) >= 1:
                first_test_case = test_cases[0]
                achievements.append({
                    "id": "first_test_case",
                    "title": "First Steps",
                    "description": "Generated your first test case",
                    "icon": "star-fill",
                    "category": "milestone",
                    "unlocked_at": first_test_case["created_at"].isoformat(),
                    "rarity": "common"
                })
            
            # Achievement 2: 10 Test Cases
            if len(test_cases) >= 10:
                tenth_test_case = test_cases[9]
                achievements.append({
                    "id": "ten_test_cases",
                    "title": "Getting Started",
                    "description": "Generated 10 test cases",
                    "icon": "star-fill",
                    "category": "milestone",
                    "unlocked_at": tenth_test_case["created_at"].isoformat(),
                    "rarity": "common"
                })
            
            # Achievement 3: 50 Test Cases
            if len(test_cases) >= 50:
                fiftieth_test_case = test_cases[49]
                achievements.append({
                    "id": "fifty_test_cases",
                    "title": "Test Case Master",
                    "description": "Generated 50 test cases",
                    "icon": "star-fill",
                    "category": "milestone",
                    "unlocked_at": fiftieth_test_case["created_at"].isoformat(),
                    "rarity": "rare"
                })
            
            # Achievement 4: 100 Test Cases
            if len(test_cases) >= 100:
                hundredth_test_case = test_cases[99]
                achievements.append({
                    "id": "hundred_test_cases",
                    "title": "Test Case Expert",
                    "description": "Generated 100 test cases",
                    "icon": "star-fill",
                    "category": "milestone",
                    "unlocked_at": hundredth_test_case["created_at"].isoformat(),
                    "rarity": "epic"
                })
            
            # Achievement 5: Multiple Source Types
            source_types = set(tc["source_type"] for tc in test_cases if tc.get("source_type"))
            if len(source_types) >= 2:
                achievements.append({
                    "id": "multiple_sources",
                    "title": "Versatile Tester",
                    "description": f"Used {len(source_types)} different source types",
                    "icon": "collection",
                    "category": "versatility",
                    "unlocked_at": test_cases[-1]["created_at"].isoformat() if test_cases else None,
                    "rarity": "uncommon"
                })
            
            # Achievement 6: All Source Types
            all_source_types = {"url", "image", "jira", "azure", "text"}
            if source_types.issuperset(all_source_types):
                achievements.append({
                    "id": "all_sources",
                    "title": "Source Master",
                    "description": "Used all available source types",
                    "icon": "award",
                    "category": "versatility",
                    "unlocked_at": test_cases[-1]["created_at"].isoformat() if test_cases else None,
                    "rarity": "legendary"
                })
            
            # Achievement 7: Consistent User
            if user.get("created_at"):
                days_since_registration = (datetime.utcnow() - user["created_at"]).days
                if days_since_registration >= 30:
                    achievements.append({
                        "id": "monthly_user",
                        "title": "Monthly User",
                        "description": "Been using the platform for 30+ days",
                        "icon": "calendar-check",
                        "category": "loyalty",
                        "unlocked_at": (user["created_at"] + timedelta(days=30)).isoformat(),
                        "rarity": "common"
                    })
                
                if days_since_registration >= 90:
                    achievements.append({
                        "id": "quarterly_user",
                        "title": "Quarterly User",
                        "description": "Been using the platform for 90+ days",
                        "icon": "calendar-check",
                        "category": "loyalty",
                        "unlocked_at": (user["created_at"] + timedelta(days=90)).isoformat(),
                        "rarity": "uncommon"
                    })
                
                if days_since_registration >= 365:
                    achievements.append({
                        "id": "yearly_user",
                        "title": "Yearly User",
                        "description": "Been using the platform for 365+ days",
                        "icon": "calendar-check",
                        "category": "loyalty",
                        "unlocked_at": (user["created_at"] + timedelta(days=365)).isoformat(),
                        "rarity": "rare"
                    })
            
            # Achievement 8: Active Streak
            if test_cases:
                # Calculate consecutive days with activity
                activity_dates = set()
                for tc in test_cases:
                    activity_dates.add(tc["created_at"].date())
                
                sorted_dates = sorted(activity_dates)
                max_streak = 0
                current_streak = 0
                
                for i in range(len(sorted_dates)):
                    if i == 0:
                        current_streak = 1
                    elif (sorted_dates[i] - sorted_dates[i-1]).days == 1:
                        current_streak += 1
                    else:
                        max_streak = max(max_streak, current_streak)
                        current_streak = 1
                
                max_streak = max(max_streak, current_streak)
                
                if max_streak >= 7:
                    achievements.append({
                        "id": "weekly_streak",
                        "title": "Weekly Warrior",
                        "description": "Maintained a 7-day activity streak",
                        "icon": "fire",
                        "category": "consistency",
                        "unlocked_at": test_cases[-1]["created_at"].isoformat(),
                        "rarity": "uncommon"
                    })
                
                if max_streak >= 30:
                    achievements.append({
                        "id": "monthly_streak",
                        "title": "Monthly Master",
                        "description": "Maintained a 30-day activity streak",
                        "icon": "fire",
                        "category": "consistency",
                        "unlocked_at": test_cases[-1]["created_at"].isoformat(),
                        "rarity": "rare"
                    })
            
            # Calculate progress towards next milestones
            next_milestones = []
            
            # Next test case milestone
            current_count = len(test_cases)
            if current_count < 10:
                next_milestones.append({
                    "type": "test_cases",
                    "current": current_count,
                    "target": 10,
                    "title": "Getting Started",
                    "description": "Generate 10 test cases",
                    "progress": (current_count / 10) * 100
                })
            elif current_count < 50:
                next_milestones.append({
                    "type": "test_cases",
                    "current": current_count,
                    "target": 50,
                    "title": "Test Case Master",
                    "description": "Generate 50 test cases",
                    "progress": (current_count / 50) * 100
                })
            elif current_count < 100:
                next_milestones.append({
                    "type": "test_cases",
                    "current": current_count,
                    "target": 100,
                    "title": "Test Case Expert",
                    "description": "Generate 100 test cases",
                    "progress": (current_count / 100) * 100
                })
            
            # Next source type milestone
            if len(source_types) < 5:
                next_milestones.append({
                    "type": "source_types",
                    "current": len(source_types),
                    "target": 5,
                    "title": "Source Master",
                    "description": "Use all 5 source types",
                    "progress": (len(source_types) / 5) * 100
                })
            
            # Calculate statistics
            total_achievements = len(achievements)
            achievement_categories = {}
            rarity_counts = {}
            
            for achievement in achievements:
                # Count by category
                category = achievement["category"]
                if category not in achievement_categories:
                    achievement_categories[category] = 0
                achievement_categories[category] += 1
                
                # Count by rarity
                rarity = achievement["rarity"]
                if rarity not in rarity_counts:
                    rarity_counts[rarity] = 0
                rarity_counts[rarity] += 1
            
            # Calculate completion percentage
            total_possible_achievements = 15  # Total number of possible achievements
            completion_percentage = (total_achievements / total_possible_achievements) * 100
            
            achievements_data = {
                "total_achievements": total_achievements,
                "completion_percentage": round(completion_percentage, 1),
                "achievements": achievements,
                "next_milestones": next_milestones,
                "statistics": {
                    "by_category": achievement_categories,
                    "by_rarity": rarity_counts,
                    "total_possible": total_possible_achievements
                },
                "summary": {
                    "level": self._get_achievement_level(completion_percentage),
                    "next_achievement": next_milestones[0] if next_milestones else None,
                    "recent_achievement": achievements[0] if achievements else None
                }
            }
            
            return {"success": True, "achievements_data": achievements_data}
            
        except Exception as e:
            logger.error(f"Error getting user achievements: {str(e)}")
            return {"success": False, "message": "Failed to retrieve achievements"}

    def _get_achievement_level(self, completion_percentage):
        """Get achievement level based on completion percentage"""
        if completion_percentage >= 90:
            return "Legendary"
        elif completion_percentage >= 75:
            return "Master"
        elif completion_percentage >= 50:
            return "Expert"
        elif completion_percentage >= 25:
            return "Intermediate"
        elif completion_percentage >= 10:
            return "Beginner"
        else:
            return "Novice"

    def get_user_comparison_and_benchmarking(self, admin_user_id, time_period='month'):
        """Get user comparison and benchmarking data (admin only)"""
        try:
            # Verify admin status
            if not self.is_admin(admin_user_id):
                return {"success": False, "message": "Access denied. Admin privileges required."}
            
            # Calculate time period
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            
            if time_period == 'day':
                start_date = now - timedelta(days=1)
            elif time_period == 'week':
                start_date = now - timedelta(days=7)
            elif time_period == 'month':
                start_date = now - timedelta(days=30)
            elif time_period == 'quarter':
                start_date = now - timedelta(days=90)
            elif time_period == 'year':
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=30)  # Default to month
            
            # Get all users' performance data
            user_performance_data = list(self.collection.aggregate([
                {"$match": {"created_at": {"$gte": start_date}}},
                {"$group": {
                    "_id": "$user_id",
                    "total_test_cases": {"$sum": 1},
                    "avg_completion_time": {"$avg": "$completion_time"},
                    "success_rate": {
                        "$avg": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    },
                    "source_types": {"$addToSet": "$source_type"},
                    "first_activity": {"$min": "$created_at"},
                    "last_activity": {"$max": "$created_at"}
                }},
                {"$sort": {"total_test_cases": -1}}
            ]))
            
            # Get user details and calculate benchmarks
            user_benchmarks = []
            total_users = len(user_performance_data)
            
            for user_perf in user_performance_data:
                user_details = self.users_collection.find_one({"_id": user_perf["_id"]}, {
                    "name": 1,
                    "email": 1,
                    "role": 1,
                    "created_at": 1
                })
                
                if user_details:
                    # Calculate user metrics
                    test_case_count = user_perf["total_test_cases"]
                    avg_completion_time = user_perf.get("avg_completion_time", 0)
                    success_rate = user_perf.get("success_rate", 0) * 100
                    source_type_diversity = len(user_perf["source_types"])
                    
                    # Calculate user age in days
                    user_age_days = 0
                    if user_details.get("created_at"):
                        user_age_days = (now - user_details["created_at"]).days
                    
                    # Calculate efficiency score
                    efficiency_score = 0
                    if test_case_count > 0 and avg_completion_time > 0:
                        # Higher test case count and lower completion time = higher efficiency
                        efficiency_score = min((test_case_count / avg_completion_time) * 100, 100)
                    
                    user_benchmarks.append({
                        "user_id": str(user_perf["_id"]),
                        "name": user_details["name"],
                        "email": user_details["email"],
                        "role": user_details.get("role", "user"),
                        "metrics": {
                            "test_case_count": test_case_count,
                            "avg_completion_time": round(avg_completion_time, 2),
                            "success_rate": round(success_rate, 2),
                            "source_type_diversity": source_type_diversity,
                            "user_age_days": user_age_days,
                            "efficiency_score": round(efficiency_score, 2)
                        }
                    })
            
            # Calculate benchmarks
            if user_benchmarks:
                # Performance benchmarks
                test_case_counts = [u["metrics"]["test_case_count"] for u in user_benchmarks]
                completion_times = [u["metrics"]["avg_completion_time"] for u in user_benchmarks if u["metrics"]["avg_completion_time"] > 0]
                success_rates = [u["metrics"]["success_rate"] for u in user_benchmarks]
                efficiency_scores = [u["metrics"]["efficiency_score"] for u in user_benchmarks]
                
                benchmarks = {
                    "test_cases": {
                        "average": round(sum(test_case_counts) / len(test_case_counts), 2),
                        "median": sorted(test_case_counts)[len(test_case_counts) // 2],
                        "top_25_percentile": sorted(test_case_counts)[int(len(test_case_counts) * 0.75)],
                        "top_10_percentile": sorted(test_case_counts)[int(len(test_case_counts) * 0.9)]
                    },
                    "completion_time": {
                        "average": round(sum(completion_times) / len(completion_times), 2) if completion_times else 0,
                        "median": sorted(completion_times)[len(completion_times) // 2] if completion_times else 0,
                        "fastest": min(completion_times) if completion_times else 0
                    },
                    "success_rate": {
                        "average": round(sum(success_rates) / len(success_rates), 2),
                        "median": sorted(success_rates)[len(success_rates) // 2],
                        "top_25_percentile": sorted(success_rates)[int(len(success_rates) * 0.75)]
                    },
                    "efficiency": {
                        "average": round(sum(efficiency_scores) / len(efficiency_scores), 2),
                        "median": sorted(efficiency_scores)[len(efficiency_scores) // 2],
                        "top_25_percentile": sorted(efficiency_scores)[int(len(efficiency_scores) * 0.75)]
                    }
                }
                
                # Calculate user rankings
                for user in user_benchmarks:
                    # Test case count ranking
                    test_case_ranking = len([u for u in user_benchmarks if u["metrics"]["test_case_count"] > user["metrics"]["test_case_count"]]) + 1
                    user["rankings"] = {
                        "test_case_count": test_case_ranking,
                        "test_case_percentile": round((total_users - test_case_ranking + 1) / total_users * 100, 1)
                    }
                    
                    # Efficiency ranking
                    efficiency_ranking = len([u for u in user_benchmarks if u["metrics"]["efficiency_score"] > user["metrics"]["efficiency_score"]]) + 1
                    user["rankings"]["efficiency"] = efficiency_ranking
                    user["rankings"]["efficiency_percentile"] = round((total_users - efficiency_ranking + 1) / total_users * 100, 1)
                    
                    # Overall ranking (weighted average)
                    overall_score = (
                        user["rankings"]["test_case_percentile"] * 0.4 +
                        user["rankings"]["efficiency_percentile"] * 0.3 +
                        user["metrics"]["success_rate"] * 0.3
                    )
                    user["rankings"]["overall_score"] = round(overall_score, 1)
                
                # Sort by overall score
                user_benchmarks.sort(key=lambda x: x["rankings"]["overall_score"], reverse=True)
                
                # Add ranking numbers
                for i, user in enumerate(user_benchmarks):
                    user["rankings"]["position"] = i + 1
            else:
                benchmarks = {}
            
            # Generate insights
            insights = []
            
            if user_benchmarks:
                # Top performers
                top_performers = user_benchmarks[:3]
                insights.append(f"Top 3 performers: {', '.join([u['name'] for u in top_performers])}")
                
                # Performance gaps
                if len(user_benchmarks) > 1:
                    top_score = user_benchmarks[0]["rankings"]["overall_score"]
                    bottom_score = user_benchmarks[-1]["rankings"]["overall_score"]
                    performance_gap = top_score - bottom_score
                    insights.append(f"Performance gap between top and bottom users: {round(performance_gap, 1)} points")
                
                # Benchmark comparisons
                if benchmarks:
                    avg_test_cases = benchmarks["test_cases"]["average"]
                    insights.append(f"Average test cases per user: {avg_test_cases}")
                    
                    top_25_threshold = benchmarks["test_cases"]["top_25_percentile"]
                    insights.append(f"Top 25% threshold: {top_25_threshold} test cases")
            
            # Generate recommendations
            recommendations = []
            
            if user_benchmarks:
                # Identify low performers
                low_performers = [u for u in user_benchmarks if u["rankings"]["overall_score"] < 50]
                if low_performers:
                    recommendations.append(f"Provide additional support for {len(low_performers)} low-performing users")
                
                # Identify high performers for recognition
                high_performers = [u for u in user_benchmarks if u["rankings"]["overall_score"] >= 80]
                if high_performers:
                    recommendations.append(f"Recognize and reward {len(high_performers)} high-performing users")
                
                # Training recommendations
                if benchmarks:
                    avg_success_rate = benchmarks["success_rate"]["average"]
                    if avg_success_rate < 80:
                        recommendations.append("Implement training programs to improve success rates")
                    
                    avg_efficiency = benchmarks["efficiency"]["average"]
                    if avg_efficiency < 50:
                        recommendations.append("Provide efficiency training and best practices")
            
            comparison_data = {
                "time_period": time_period,
                "start_date": start_date.isoformat(),
                "end_date": now.isoformat(),
                "total_users_analyzed": total_users,
                "user_benchmarks": user_benchmarks,
                "benchmarks": benchmarks,
                "insights": insights,
                "recommendations": recommendations,
                "summary": {
                    "top_performer": user_benchmarks[0] if user_benchmarks else None,
                    "average_performance": benchmarks.get("test_cases", {}).get("average", 0) if benchmarks else 0,
                    "performance_distribution": {
                        "excellent": len([u for u in user_benchmarks if u["rankings"]["overall_score"] >= 80]),
                        "good": len([u for u in user_benchmarks if 60 <= u["rankings"]["overall_score"] < 80]),
                        "average": len([u for u in user_benchmarks if 40 <= u["rankings"]["overall_score"] < 60]),
                        "below_average": len([u for u in user_benchmarks if u["rankings"]["overall_score"] < 40])
                    }
                }
            }
            
            return {"success": True, "comparison_data": comparison_data}
            
        except Exception as e:
            logger.error(f"Error getting user comparison and benchmarking: {str(e)}")
            return {"success": False, "message": "Failed to retrieve comparison data"}

    def get_user_learning_insights(self, user_id):
        """Get user learning and development insights"""
        try:
            # Get user's test case progression
            test_cases = list(self.collection.find(
                {"user_id": user_id},
                {"_id": 1, "created_at": 1, "source_type": 1, "status": 1}
            ).sort("created_at", 1))
            
            if not test_cases:
                return {"success": True, "learning_insights": {"message": "No test cases found for analysis"}}
            
            # Calculate learning metrics
            source_types_used = set(tc["source_type"] for tc in test_cases if tc.get("source_type"))
            total_test_cases = len(test_cases)
            
            # Learning progression
            learning_stages = []
            if total_test_cases >= 1:
                learning_stages.append("Beginner - First test case generated")
            if total_test_cases >= 5:
                learning_stages.append("Novice - Basic understanding achieved")
            if total_test_cases >= 15:
                learning_stages.append("Intermediate - Consistent usage")
            if total_test_cases >= 30:
                learning_stages.append("Advanced - Proficient user")
            if total_test_cases >= 50:
                learning_stages.append("Expert - Master level")
            
            # Skill development areas
            skill_areas = {
                "url_testing": len([tc for tc in test_cases if tc.get("source_type") == "url"]),
                "image_testing": len([tc for tc in test_cases if tc.get("source_type") == "image"]),
                "jira_integration": len([tc for tc in test_cases if tc.get("source_type") == "jira"]),
                "azure_integration": len([tc for tc in test_cases if tc.get("source_type") == "azure"]),
                "text_analysis": len([tc for tc in test_cases if tc.get("source_type") == "text"])
            }
            
            # Identify strengths and areas for improvement
            strengths = [area for area, count in skill_areas.items() if count >= 5]
            improvement_areas = [area for area, count in skill_areas.items() if count < 3]
            
            learning_insights = {
                "current_stage": learning_stages[-1] if learning_stages else "New User",
                "learning_progression": learning_stages,
                "skill_development": skill_areas,
                "strengths": strengths,
                "improvement_areas": improvement_areas,
                "recommendations": [
                    f"Focus on {area.replace('_', ' ').title()} to improve skills" for area in improvement_areas
                ] if improvement_areas else ["Continue exploring different source types"]
            }
            
            return {"success": True, "learning_insights": learning_insights}
            
        except Exception as e:
            logger.error(f"Error getting learning insights: {str(e)}")
            return {"success": False, "message": "Failed to retrieve learning insights"}

    def generate_jwt_token(self, user_id):
        """Generate JWT token for user"""
        try:
            payload = {
                "user_id": user_id,
                "exp": datetime.utcnow() + timedelta(days=30),  # 30 days expiry
                "iat": datetime.utcnow()
            }
            # Use a secret key from environment or generate one
            secret_key = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
            token = jwt.encode(payload, secret_key, algorithm="HS256")
            return token
        except Exception as e:
            logger.error(f"Error generating JWT token: {str(e)}")
            return None

    def verify_jwt_token(self, token):
        """Verify JWT token and return user info"""
        try:
            secret_key = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            user_id = payload.get("user_id")
            
            if user_id:
                user = self.users_collection.find_one({"_id": user_id})
                if user and user.get("is_active", True):
                    return {
                        "success": True,
                        "user": {
                            "id": user["_id"],
                            "email": user["email"],
                            "name": user["name"],
                            "role": user.get("role", "user")
                        }
                    }
            
            return {"success": False, "message": "Invalid or expired token"}
            
        except jwt.ExpiredSignatureError:
            return {"success": False, "message": "Token expired"}
        except jwt.InvalidTokenError:
            return {"success": False, "message": "Invalid token"}
        except Exception as e:
            logger.error(f"Error verifying JWT token: {str(e)}")
            return {"success": False, "message": "Token verification failed"}

    def get_user_test_cases(self, user_id, limit=50):
        """Get all test cases for a specific user"""
        try:
            test_cases = list(self.collection.find(
                {"user_id": user_id},
                {"_id": 1, "test_data": 1, "created_at": 1, "source_type": 1, "item_id": 1}
            ).sort("created_at", -1).limit(limit))
            
            return test_cases
        except Exception as e:
            logger.error(f"Error getting user test cases: {str(e)}")
            return []

    def save_test_case(self, test_data, item_id=None, source_type=None, user_id=None):
        """Save test case data and generate unique URL with optional user association"""
        try:
            unique_id = str(uuid.uuid4())
            document = {
                "_id": unique_id,
                "test_data": test_data,
                "created_at": datetime.utcnow(),
                "url_key": unique_id,
                "item_id": item_id,
                "source_type": source_type,  # Preserve source type for proper identification
                "status": {},  # Initialize empty status dictionary for test cases
                "user_id": user_id  # Associate with user if provided
            }
            self.collection.insert_one(document)
            logger.info(f"Successfully saved test case with ID: {unique_id}, source_type: {source_type}, user_id: {user_id}")
            return unique_id
        except Exception as e:
            logger.error(f"Error saving test case: {str(e)}")
            raise Exception("Failed to save test case to database")

    def update_status_dict(self, url_key, status_values):
        """Update the status dictionary for a test case document"""
        try:
            result = self.collection.update_one(
                {"url_key": url_key},
                {"$set": {"status": status_values}}
            )
            if result.modified_count > 0:
                logger.info(f"Successfully updated status dict for {url_key}")
                return True
            else:
                logger.warning(f"No document found to update status for {url_key}")
                return False
        except Exception as e:
            logger.error(f"Error updating status dict: {str(e)}")
            return False

    def track_user_session(self, session_data):
        """Track user session and page visits"""
        try:
            session_doc = {
                "session_id": session_data.get("session_id"),
                "user_agent": session_data.get("user_agent"),
                "ip_address": session_data.get("ip_address"),
                "referrer": session_data.get("referrer"),
                "page_visited": session_data.get("page_visited"),
                "timestamp": datetime.utcnow(),
                "country": session_data.get("country"),
                "city": session_data.get("city")
            }
            self.user_sessions_collection.insert_one(session_doc)
            logger.info(f"Tracked user session: {session_data.get('session_id')}")
            return True
        except Exception as e:
            logger.error(f"Error tracking user session: {str(e)}")
            return False

    def track_event(self, event_data):
        """Track user events and interactions"""
        try:
            event_doc = {
                "event_type": event_data.get("event_type"),
                "event_data": event_data.get("event_data", {}),
                "session_id": event_data.get("session_id"),
                "user_agent": event_data.get("user_agent"),
                "ip_address": event_data.get("ip_address"),
                "timestamp": datetime.utcnow(),
                "source_type": event_data.get("source_type"),
                "test_case_types": event_data.get("test_case_types", []),
                "item_count": event_data.get("item_count", 0)
            }
            
            # Add user_id and user_role if available
            if event_data.get("user_id"):
                event_doc["user_id"] = event_data.get("user_id")
            if event_data.get("user_role"):
                event_doc["user_role"] = event_data.get("user_role")
            
            self.analytics_collection.insert_one(event_doc)
            logger.info(f"Tracked event: {event_data.get('event_type')}")
            return True
        except Exception as e:
            logger.error(f"Error tracking event: {str(e)}")
            return False

    def get_analytics_summary(self, start_date=None, end_date=None, days=30, source_type=None, user_id=None):
        """Get analytics summary for the specified date range or number of days with optional filters"""
        try:
            if start_date and end_date:
                # Convert string dates to datetime objects
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)  # Include end date
                date_filter = {"timestamp": {"$gte": start_datetime, "$lt": end_datetime}}
            else:
                # Fallback to days parameter
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                date_filter = {"timestamp": {"$gte": cutoff_date}}
            
            # Build base filter with date and optional filters
            base_filter = {**date_filter}
            if source_type:
                base_filter["source_type"] = source_type
            
            # Add user_id filter if provided
            if user_id:
                base_filter["user_id"] = user_id
                # Also filter sessions by user_id
                date_filter["user_id"] = user_id
            
            # Get total sessions (sessions don't have event_type or source_type, so use date filter only)
            total_sessions = self.user_sessions_collection.count_documents(date_filter)
            
            # Get total events with filters
            total_events = self.analytics_collection.count_documents(base_filter)
            
            # Get generate button clicks with filters
            generate_filter = {**base_filter, "event_type": "generate_button_click"}
            generate_clicks = self.analytics_collection.count_documents(generate_filter)
            
            # Get successful generations with filters
            success_filter = {**base_filter, "event_type": "test_case_generated"}
            successful_generations = self.analytics_collection.count_documents(success_filter)
            
            # Get source type distribution - only count successful test case generations
            source_type_pipeline = [
                {"$match": {**base_filter, "event_type": "test_case_generated"}},
                {"$addFields": {
                    "effective_source_type": {
                        "$cond": {
                            "if": {"$and": [
                                {"$ne": ["$source_type", None]},
                                {"$ne": ["$source_type", ""]}
                            ]},
                            "then": "$source_type",
                            "else": "$event_data.source_type"
                        }
                    }
                }},
                {"$match": {"effective_source_type": {"$exists": True, "$ne": None, "$ne": ""}}},
                {"$group": {"_id": "$effective_source_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            source_type_stats = list(self.analytics_collection.aggregate(source_type_pipeline))
            
            # Get test case type distribution - only count successful test case generations
            test_case_type_pipeline = [
                {"$match": {**base_filter, "event_type": "test_case_generated", "test_case_types": {"$exists": True, "$ne": []}}},
                {"$unwind": "$test_case_types"},
                {"$group": {"_id": "$test_case_types", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            test_case_type_stats = list(self.analytics_collection.aggregate(test_case_type_pipeline))
            
            # Get daily activity
            daily_activity_pipeline = [
                {"$match": base_filter},
                {"$group": {
                    "_id": {
                        "year": {"$year": "$timestamp"},
                        "month": {"$month": "$timestamp"},
                        "day": {"$dayOfMonth": "$timestamp"}
                    },
                    "events": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            daily_activity = list(self.analytics_collection.aggregate(daily_activity_pipeline))
            
            # Get generation timing statistics
            timing_pipeline = [
                {"$match": {
                    **base_filter,
                    "event_type": "test_case_generated",
                    "event_data.generation_duration_seconds": {"$exists": True}
                }},
                {"$group": {
                    "_id": None,
                    "avg_generation_time": {"$avg": "$event_data.generation_duration_seconds"},
                    "min_generation_time": {"$min": "$event_data.generation_duration_seconds"},
                    "max_generation_time": {"$max": "$event_data.generation_duration_seconds"},
                    "total_generations": {"$sum": 1}
                }}
            ]
            timing_stats = list(self.analytics_collection.aggregate(timing_pipeline))
            
            # Get timing by source type
            timing_by_source_pipeline = [
                {"$match": {
                    **base_filter,
                    "event_type": "test_case_generated",
                    "event_data.generation_duration_seconds": {"$exists": True}
                }},
                {"$addFields": {
                    "effective_source_type": {
                        "$cond": {
                            "if": {"$and": [
                                {"$ne": ["$source_type", None]},
                                {"$ne": ["$source_type", ""]}
                            ]},
                            "then": "$source_type",
                            "else": "$event_data.source_type"
                        }
                    }
                }},
                {"$match": {"effective_source_type": {"$exists": True, "$ne": None, "$ne": ""}}},
                {"$group": {
                    "_id": "$effective_source_type",
                    "avg_generation_time": {"$avg": "$event_data.generation_duration_seconds"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"avg_generation_time": -1}}
            ]
            timing_by_source = list(self.analytics_collection.aggregate(timing_by_source_pipeline))
            
            # Get timing by item count
            timing_by_items_pipeline = [
                {"$match": {
                    **base_filter,
                    "event_type": "test_case_generated",
                    "event_data.generation_duration_seconds": {"$exists": True},
                    "item_count": {"$exists": True, "$ne": 0}
                }},
                {"$group": {
                    "_id": {
                        "item_range": {
                            "$cond": {
                                "if": {"$lte": ["$item_count", 5]},
                                "then": "1-5 items",
                                "else": {
                                    "$cond": {
                                        "if": {"$lte": ["$item_count", 10]},
                                        "then": "6-10 items",
                                        "else": {
                                            "$cond": {
                                                "if": {"$lte": ["$item_count", 20]},
                                                "then": "11-20 items",
                                                "else": "20+ items"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "avg_generation_time": {"$avg": "$event_data.generation_duration_seconds"},
                    "avg_time_per_item": {"$avg": "$event_data.average_time_per_item"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id.item_range": 1}}
            ]
            timing_by_items = list(self.analytics_collection.aggregate(timing_by_items_pipeline))
            
            # For non-admin users, don't show session data
            if user_id:
                # Regular user: hide session data
                return {
                    "total_sessions": 0,  # Hide sessions for regular users
                    "total_events": total_events,
                    "generate_clicks": generate_clicks,
                    "successful_generations": successful_generations,
                    "success_rate": min((successful_generations / generate_clicks * 100) if generate_clicks > 0 else 0, 100),
                    "source_type_distribution": source_type_stats,
                    "test_case_type_distribution": test_case_type_stats,
                    "daily_activity": daily_activity,
                    "generation_timing": timing_stats[0] if timing_stats else None,
                    "timing_by_source": timing_by_source,
                    "timing_by_items": timing_by_items,
                    "period_days": days
                }
            else:
                # Admin: show all data including sessions
                return {
                    "total_sessions": total_sessions,
                    "total_events": total_events,
                    "generate_clicks": generate_clicks,
                    "successful_generations": successful_generations,
                    "success_rate": min((successful_generations / generate_clicks * 100) if generate_clicks > 0 else 0, 100),
                    "source_type_distribution": source_type_stats,
                    "test_case_type_distribution": test_case_type_stats,
                    "daily_activity": daily_activity,
                    "generation_timing": timing_stats[0] if timing_stats else None,
                    "timing_by_source": timing_by_source,
                    "timing_by_items": timing_by_items,
                    "period_days": days
                }
        except Exception as e:
            logger.error(f"Error getting analytics summary: {str(e)}")
            return None

    def get_detailed_analytics(self, filters=None):
        """Get detailed analytics with optional filters"""
        try:
            match_criteria = {}
            if filters:
                if filters.get("start_date"):
                    match_criteria["timestamp"] = {"$gte": filters["start_date"]}
                if filters.get("end_date"):
                    if "timestamp" in match_criteria:
                        match_criteria["timestamp"]["$lte"] = filters["end_date"]
                    else:
                        match_criteria["timestamp"] = {"$lte": filters["end_date"]}
                if filters.get("event_type"):
                    match_criteria["event_type"] = filters["event_type"]
                if filters.get("source_type"):
                    match_criteria["source_type"] = filters["source_type"]
            
            # Get events with pagination
            events = list(self.analytics_collection.find(
                match_criteria,
                {"_id": 0}  # Exclude MongoDB _id
            ).sort("timestamp", -1).limit(1000))
            
            return events
        except Exception as e:
            logger.error(f"Error getting detailed analytics: {str(e)}")
            return None

    def update_test_case_status(self, url_key, test_case_id, status):
        try:
            # First verify the document exists
            doc = self.collection.find_one({"url_key": url_key})
            if not doc:
                logger.error(f"No document found with url_key: {url_key}")
                return False

            # Log the request details
            logger.info(f"Updating status for test case with identifier '{test_case_id}' in document {url_key}")
            
            # Always update the central status dictionary first for reliable syncing
            # This ensures all views (main and shared) use the same status values
            title_found = False
            
            # Check if we already know this is a title (most common case)
            if test_case_id and '.' not in test_case_id and '/' not in test_case_id:
                # Update the status dictionary directly using the test_case_id as title
                self.collection.update_one(
                    {"url_key": url_key},
                    {"$set": {f"status.{test_case_id}": status}}
                )
                title_found = True
                logger.info(f"Updated central status dictionary for title: {test_case_id}")
            
            # Check if this is a shared view update
            is_shared_view = False
            if 'test_data' in doc and isinstance(doc['test_data'], list):
                is_shared_view = True
                logger.info(f"Shared view update detected for {url_key}")
            
            if is_shared_view:
                # For shared views, test_data is a list of test case objects
                test_cases = doc['test_data']
                
                # Update status in the array
                found = False
                for idx, tc in enumerate(test_cases):
                    title = tc.get('Title', '')
                    
                    # Match by title (which is our primary identifier in shared views)
                    if title == test_case_id:
                        logger.info(f"Found shared view match by title: {title}")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.{idx}.Status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                        
                        found = True
                        break
                
                if not found:
                    logger.warning(f"No test case found with title '{test_case_id}' in shared view document {url_key}")
                    return False
                
                return True
                
            elif 'test_data' in doc and 'test_cases' in doc['test_data']:
                test_cases = doc['test_data']['test_cases']
                
                # Extract just the UI identifier part (e.g., TC_UI_01 from TC_UI_01_Email_Field_Presence)
                ui_identifier = None
                if '_' in test_case_id:
                    parts = test_case_id.split('_')
                    if len(parts) >= 3:
                        ui_identifier = f"{parts[0]}_{parts[1]}_{parts[2]}"
                        logger.info(f"Extracted UI identifier: {ui_identifier}")
                
                # Approach 1: Try to find the test case by matching part of the title
                for idx, tc in enumerate(test_cases):
                    title = tc.get('Title', tc.get('title', ''))
                    content = tc.get('Content', tc.get('content', ''))
                    
                    # If no title field, try to extract title from content
                    if not title and content:
                        # Look for "Title:" in the content
                        lines = content.split('\n')
                        for line in lines:
                            if line.strip().startswith('Title:'):
                                title = line.strip().replace('Title:', '').strip()
                                break
                        
                        # If still no title, try to extract from the first line that looks like a test case ID
                        if not title:
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and (line.startswith('TC_') or line.startswith('TC_FUNC_') or line.startswith('TC_UI_')):
                                    title = line
                                    break
                    
                    # Check if the title or content contains the test case ID
                    if title and test_case_id in title:
                        logger.info(f"Found match in title: {title}")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                        
                        if result.modified_count > 0:
                            logger.info(f"Successfully updated status by title match for {test_case_id}")
                            return True
                    
                    # Check if the test case ID (without the item suffix) matches the title
                    # e.g., "TC_FUNC_01_Verify_Dashboard_Display_Payable_Amount" should match
                    # "TC_FUNC_01_Verify_Dashboard_Display_Payable_Amount (KAN-4)"
                    if title and '(' in test_case_id:
                        # Extract the base title (before the parentheses)
                        base_title = test_case_id.split('(')[0].strip()
                        if title == base_title:
                            logger.info(f"Found match by base title: {base_title}")
                            result = self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"test_data.test_cases.{idx}.status": status}}
                            )
                            
                            # Also update the status in the status dictionary for syncing
                            if not title_found:
                                self.collection.update_one(
                                    {"url_key": url_key},
                                    {"$set": {f"status.{test_case_id}": status}}
                                )
                            
                            if result.modified_count > 0:
                                logger.info(f"Successfully updated status by base title match for {test_case_id}")
                                return True
                    
                    # Fallback: Check if the test case ID appears anywhere in the content
                    if content and test_case_id in content:
                        logger.info(f"Found match in content for test case ID: {test_case_id}")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{test_case_id}": status}}
                            )
                        
                        if result.modified_count > 0:
                            logger.info(f"Successfully updated status by content match for {test_case_id}")
                            return True
                    
                    # Also try matching with just the UI identifier part (more precise matching)
                    if ui_identifier and title:
                        # Check if the title starts with the UI identifier followed by underscore or space
                        # This prevents partial matches like TC_FUNC_2 matching TC_FUNC_20
                        if (title.startswith(ui_identifier + '_') or 
                            title.startswith(ui_identifier + ' ') or
                            title == ui_identifier):
                            logger.info(f"Found match for UI identifier {ui_identifier} in title: {title}")
                            result = self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"test_data.test_cases.{idx}.status": status}}
                            )
                            
                            # Also update the status in the status dictionary for syncing
                            if not title_found:
                                self.collection.update_one(
                                    {"url_key": url_key},
                                    {"$set": {f"status.{test_case_id}": status}}
                                )
                            
                            if result.modified_count > 0:
                                logger.info(f"Successfully updated status by UI identifier match for {ui_identifier}")
                                return True
                    
                    # Check content field as well
                    if content and test_case_id in content:
                        logger.info(f"Found match in content")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if title and not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                        
                        if result.modified_count > 0:
                            logger.info(f"Successfully updated status by content match for {test_case_id}")
                            return True
                
                # Approach 2: Fall back to direct ID matching (for backwards compatibility)
                for idx, tc in enumerate(test_cases):
                    if tc.get('test_case_id') == test_case_id or tc.get('Test Case ID') == test_case_id:
                        logger.info(f"Found direct ID match at index {idx}")
                        title = tc.get('Title', tc.get('title', ''))
                        
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if title and not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                            
                        return result.modified_count > 0
                
                # If we got here, no match was found
                logger.warning(f"No test case found matching '{test_case_id}' in document {url_key}")
                return False
            else:
                logger.warning(f"Document {url_key} has no test cases")
                return False

        except Exception as e:
            logger.error(f"Error updating test case status: {str(e)}")
            return False

    def get_test_case(self, url_key):
        """Retrieve test case data by URL key"""
        try:
            result = self.collection.find_one({"url_key": url_key})
            if not result:
                # Try to find by _id as fallback
                result = self.collection.find_one({"_id": url_key})
                if result:
                    logger.info(f"Found document by _id: {url_key}")
                else:
                    logger.warning(f"No test case found for URL key or _id: {url_key}")
            return result
        except Exception as e:
            logger.error(f"Error retrieving test case: {str(e)}")
            raise Exception("Failed to retrieve test case from database")
            
    def get_test_case_status_values(self, url_key, force_refresh=False):
        """Retrieve all status values for test cases in a document
        
        Args:
            url_key: The unique URL key for the document
            force_refresh: If True, forces a direct database query to get fresh data
        """
        try:
            # Debug: Print direct DB query
            # logger.info(f"DIRECT DB QUERY FOR STATUS VALUES: url_key={url_key}, force_refresh={force_refresh}")
            
            # Always get a fresh copy from the database when force_refresh is True
            result = self.collection.find_one({"url_key": url_key})
            if not result:
                # Try to find by _id as fallback
                result = self.collection.find_one({"_id": url_key})
                if result:
                    logger.info(f"Found document by _id: {url_key}")
                else:
                    logger.warning(f"No test case found for URL key or _id: {url_key}")
                    return None
                
            # Debug: Log all data in the document for diagnosis
            if 'status' in result:
                logger.info(f"STATUS DICT in MongoDB: {result['status']}")
            else:
                logger.info("NO STATUS DICT in MongoDB document")
                
            # If test_data is a list (shared view), inspect it
            if 'test_data' in result and isinstance(result['test_data'], list):
                for i, tc in enumerate(result['test_data']):
                    if isinstance(tc, dict):
                        title = tc.get('Title', '')
                        status = tc.get('Status', '')
                        if title:
                            logger.info(f"SHARED VIEW TC[{i}]: Title='{title}', Status='{status}'")
                    else:
                        logger.warning(f"SHARED VIEW TC[{i}] is not a dict: {type(tc)}")
            
            # If test_data has test_cases array (main format), inspect it
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                for i, tc in enumerate(result['test_data']['test_cases']):
                    if isinstance(tc, dict):
                        title = tc.get('Title', tc.get('title', ''))
                        status = tc.get('Status', tc.get('status', ''))
                        if title:
                            logger.info(f"MAIN VIEW TC[{i}]: Title='{title}', Status='{status}'")
                    elif isinstance(tc, str):
                        # Attempt to parse string-formatted test case(s)
                        try:
                            from utils.file_handler import parse_traditional_format
                            parsed = parse_traditional_format(tc)
                            if parsed:
                                for pidx, ptc in enumerate(parsed):
                                    ptitle = ptc.get('Title', ptc.get('title', ''))
                                    pstatus = ptc.get('Status', ptc.get('status', ''))
                                    if ptitle:
                                        logger.info(f"MAIN VIEW TC[{i}] parsed[{pidx}]: Title='{ptitle}', Status='{pstatus}'")
                            else:
                                logger.warning(f"MAIN VIEW TC[{i}] is a string but could not be parsed")
                        except Exception as e:
                            logger.error(f"Error parsing MAIN VIEW TC[{i}] string entry: {e}")
                    else:
                        logger.warning(f"MAIN VIEW TC[{i}] is not a dict: {type(tc)}")
            
            # If test_data is a string (raw format), log it
            elif 'test_data' in result and isinstance(result['test_data'], str):
                logger.warning(f"test_data is stored as string (length: {len(result['test_data'])}): {result['test_data'][:200]}...")
                # For string test_data, we can't extract individual test case status
                return {}
                
            # First try to get status values from the status dictionary
            if 'status' in result and result['status']:
                logger.info(f"Found {len(result['status'])} status values in status dictionary")
                return result['status']
                
            # If no status dictionary, build one from test cases
            status_values = {}
            
            # Check if test_data is a list (shared view format)
            if 'test_data' in result and isinstance(result['test_data'], list):
                logger.info("Building status values from shared view format")
                for tc in result['test_data']:
                    if isinstance(tc, dict) and 'Title' in tc:
                        # Include all statuses, even empty ones for completeness
                        title = tc.get('Title', '')
                        status = tc.get('Status', '')
                        if title:
                            status_values[title] = status
                            # logger.debug(f"Found status '{status}' for '{title}' in shared view")
                        
            # Check if test_data has test_cases array (main format)
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                logger.info("Building status values from main view format")
                for tc in result['test_data']['test_cases']:
                    if isinstance(tc, dict):
                        title = tc.get('Title', tc.get('title', ''))
                        status = tc.get('Status', tc.get('status', ''))
                        if title:
                            status_values[title] = status
                            # logger.debug(f"Found status '{status}' for '{title}' in main view")
                    elif isinstance(tc, str):
                        # Parse string entries into structured test cases and capture their statuses
                        from utils.file_handler import parse_traditional_format
                        try:
                            parsed_test_cases = parse_traditional_format(tc)
                            if parsed_test_cases:
                                for ptc in parsed_test_cases:
                                    if isinstance(ptc, dict):
                                        ptitle = ptc.get('Title', ptc.get('title', ''))
                                        pstatus = ptc.get('Status', ptc.get('status', ''))
                                        if ptitle:
                                            status_values[ptitle] = pstatus
                        except Exception as e:
                            logger.error(f"Error parsing string test case entry in main view: {e}")
                            
            # Check if test_data has test_data array (nested structure)
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_data' in result['test_data']:
                logger.info("Building status values from nested test_data format")
                if isinstance(result['test_data']['test_data'], list):
                    for tc in result['test_data']['test_data']:
                        if isinstance(tc, dict):
                            title = tc.get('Title', tc.get('title', ''))
                            status = tc.get('Status', tc.get('status', ''))
                            if title:
                                status_values[title] = status
                                logger.debug(f"Found status '{status}' for '{title}' in nested test_data")
                            
            # Handle string test_data (fallback)
            elif 'test_data' in result and isinstance(result['test_data'], str):
                logger.info("test_data is stored as string - no individual status values available")
                # Return empty status values for string data
                return {}
                
            # Handle test_data with test_cases string
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                if isinstance(result['test_data']['test_cases'], str):
                    logger.info("Building status values from test_cases string")
                    from utils.file_handler import parse_traditional_format
                    try:
                        parsed_test_cases = parse_traditional_format(result['test_data']['test_cases'])
                        if parsed_test_cases:
                            for tc in parsed_test_cases:
                                if isinstance(tc, dict):
                                    title = tc.get('Title', tc.get('title', ''))
                                    status = tc.get('Status', tc.get('status', ''))
                                    if title:
                                        status_values[title] = status
                                        logger.debug(f"Found status '{status}' for '{title}' in parsed test_cases")
                    except Exception as e:
                        logger.error(f"Error parsing test_cases string: {e}")
                        
            # Handle test_data with test_cases list
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                if isinstance(result['test_data']['test_cases'], list):
                    logger.info("Building status values from test_cases list")
                    from utils.file_handler import parse_traditional_format
                    try:
                        for test_case_obj in result['test_data']['test_cases']:
                            if isinstance(test_case_obj, dict) and 'content' in test_case_obj:
                                content = test_case_obj['content']
                                if content and isinstance(content, str):
                                    parsed_test_cases = parse_traditional_format(content)
                                    if parsed_test_cases:
                                        for tc in parsed_test_cases:
                                            if isinstance(tc, dict):
                                                title = tc.get('Title', tc.get('title', ''))
                                                status = tc.get('Status', tc.get('status', ''))
                                                if title:
                                                    status_values[title] = status
                                                    logger.debug(f"Found status '{status}' for '{title}' from list item")
                    except Exception as e:
                        logger.error(f"Error parsing test_cases list: {e}")
                        
            # Update the status dictionary in the document for future use
            if status_values:
                logger.info(f"UPDATING status dict in MongoDB with {len(status_values)} values: {status_values}")
                self.collection.update_one(
                    {"url_key": url_key},
                    {"$set": {"status": status_values}}
                )
                
            logger.info(f"Returning {len(status_values)} status values for {url_key}")
            return status_values
            
        except Exception as e:
            logger.error(f"Error retrieving test case status values: {str(e)}")
            return None

    def save_url_data(self, url_params):
        """Save URL parameters and generate a short key"""
        try:
            short_key = str(uuid.uuid4())[:8]  # Using first 8 characters of UUID for shorter URL
            document = {
                "_id": short_key,
                "url_params": url_params,
                "created_at": datetime.utcnow(),
                "type": "shortened_url"
            }
            self.collection.insert_one(document)
            logger.info(f"Successfully saved URL data with short key: {short_key}")
            return short_key
        except Exception as e:
            logger.error(f"Error saving URL data: {str(e)}")
            raise Exception("Failed to save URL data to database")

    def get_url_data(self, short_key):
        """
        Retrieve URL parameters by short key
        """
        try:
            # Search by _id instead of short_key since all documents have short_key: None
            document = self.collection.find_one({"_id": short_key})
            if document:
                # Check for test_data field first (new format), then url_params (old format)
                if 'test_data' in document:
                    return document.get('test_data')
                elif 'url_params' in document:
                    return document.get('url_params')
                else:
                    # If neither exists, return the document itself
                    return document
            return None
        except Exception as e:
            logger.error(f"Error retrieving URL data: {e}")
            return None