"""
Centralized error logging configuration for the AI Test Case Generator application.
This module provides error tracking functionality using MongoDB instead of Sentry.
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
import pymongo
from pymongo import MongoClient
from config.settings import MONGODB_URI, MONGODB_DB

logger = logging.getLogger(__name__)

class ErrorLogger:
    def __init__(self):
        """Initialize the error logger with MongoDB connection"""
        try:
            self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            # Verify connection
            self.client.server_info()
            self.db = self.client[MONGODB_DB]
            self.error_collection = self.db.error_logs
            logger.info("Error logger initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize error logger: {str(e)}")
            self.client = None
            self.db = None
            self.error_collection = None

    def _log_error(self, error_type: str, message: str, level: str = "error", 
                   context: Optional[Dict[str, Any]] = None, tags: Optional[Dict[str, str]] = None,
                   user_context: Optional[Dict[str, str]] = None):
        """
        Internal method to log errors to MongoDB
        
        Args:
            error_type: Type of error (exception, message, etc.)
            message: Error message or description
            level: Log level (debug, info, warning, error, critical)
            context: Additional context data
            tags: Tags for categorization
            user_context: User information
        """
        try:
            if self.error_collection is None:
                logger.error("Error collection not available, falling back to standard logging")
                logger.error(f"{error_type}: {message}")
                return

            error_doc = {
                "timestamp": datetime.utcnow(),
                "error_type": error_type,
                "message": message,
                "level": level,
                "environment": os.getenv("FLASK_ENV", "development"),
                "service": "ai-test-case-generator"
            }

            if context:
                error_doc["context"] = context
            
            if tags:
                error_doc["tags"] = tags
            
            if user_context:
                error_doc["user_context"] = user_context

            self.error_collection.insert_one(error_doc)
            logger.info(f"Error logged to MongoDB: {error_type} - {message}")
            
        except Exception as e:
            logger.error(f"Failed to log error to MongoDB: {str(e)}")
            # Fallback to standard logging
            logger.error(f"{error_type}: {message}")

    def capture_exception(self, exception: Exception, context: Optional[Dict[str, Any]] = None):
        """
        Capture an exception with additional context.
        
        Args:
            exception: The exception to capture
            context: Additional context to include
        """
        error_context = {
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "traceback": self._get_traceback(exception)
        }
        
        if context:
            error_context.update(context)
        
        self._log_error(
            error_type="exception",
            message=str(exception),
            level="error",
            context=error_context
        )

    def capture_message(self, message: str, level: str = "info", context: Optional[Dict[str, Any]] = None):
        """
        Capture a message with specified level and context.
        
        Args:
            message: The message to capture
            level: Log level (debug, info, warning, error, critical)
            context: Additional context to include
        """
        self._log_error(
            error_type="message",
            message=message,
            level=level,
            context=context
        )

    def set_tag(self, key: str, value: str):
        """
        Set a tag for error events.
        
        Args:
            key: Tag key
            value: Tag value
        """
        # Store tags in a class variable for use in subsequent log calls
        if not hasattr(self, '_current_tags'):
            self._current_tags = {}
        self._current_tags[key] = value

    def set_context(self, name: str, data: Dict[str, Any]):
        """
        Set context data for error events.
        
        Args:
            name: Context name
            data: Context data
        """
        # Store context in a class variable for use in subsequent log calls
        if not hasattr(self, '_current_context'):
            self._current_context = {}
        self._current_context[name] = data

    def set_user_context(self, user_id: Optional[str] = None, email: Optional[str] = None, 
                        username: Optional[str] = None):
        """
        Set user context for error events.
        
        Args:
            user_id: User ID
            email: User email
            username: Username
        """
        user_data = {}
        if user_id:
            user_data['id'] = user_id
        if email:
            user_data['email'] = email
        if username:
            user_data['username'] = username
        
        if user_data:
            self._current_user_context = user_data

    def _get_traceback(self, exception: Exception) -> str:
        """Extract traceback information from exception"""
        import traceback
        try:
            return ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        except:
            return "Unable to extract traceback"

    def get_error_summary(self, days: int = 30, level: Optional[str] = None, 
                         start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a summary of errors from MongoDB
        
        Args:
            days: Number of days to look back (used if start_date/end_date not provided)
            level: Filter by log level
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dictionary with error summary statistics
        """
        try:
            if self.error_collection is None:
                return {"error": "Error collection not available"}

            from datetime import timedelta
            
            # Build date filter
            if start_date and end_date:
                try:
                    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                    end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)  # Include end date
                    filter_criteria = {"timestamp": {"$gte": start_datetime, "$lt": end_datetime}}
                    # Calculate actual days for display
                    days = (end_datetime - start_datetime).days
                except Exception as e:
                    logger.warning(f"Error parsing date range, falling back to days: {e}")
                    cutoff_date = datetime.utcnow() - timedelta(days=days)
                    filter_criteria = {"timestamp": {"$gte": cutoff_date}}
            else:
                # Fallback to days parameter
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                filter_criteria = {"timestamp": {"$gte": cutoff_date}}
            
            if level:
                filter_criteria["level"] = level

            # Get total errors
            total_errors = self.error_collection.count_documents(filter_criteria)
            
            # Get errors by level
            level_pipeline = [
                {"$match": filter_criteria},
                {"$group": {"_id": "$level", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            errors_by_level = list(self.error_collection.aggregate(level_pipeline))
            
            # Get errors by type
            type_pipeline = [
                {"$match": filter_criteria},
                {"$group": {"_id": "$error_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            errors_by_type = list(self.error_collection.aggregate(type_pipeline))
            
            # Get recent errors
            recent_errors = list(self.error_collection.find(
                filter_criteria,
                {"_id": 0, "timestamp": 1, "error_type": 1, "message": 1, "level": 1}
            ).sort("timestamp", -1).limit(10))
            
            return {
                "total_errors": total_errors,
                "errors_by_level": errors_by_level,
                "errors_by_type": errors_by_type,
                "recent_errors": recent_errors,
                "period_days": days
            }
            
        except Exception as e:
            logger.error(f"Error getting error summary: {str(e)}")
            return {"error": str(e)}

# Global error logger instance
error_logger = ErrorLogger()

# Convenience functions that mirror Sentry API
def capture_exception(exception: Exception, context: Optional[Dict[str, Any]] = None):
    """Capture an exception with additional context."""
    error_logger.capture_exception(exception, context)

def capture_message(message: str, level: str = "info", context: Optional[Dict[str, Any]] = None):
    """Capture a message with specified level and context."""
    error_logger.capture_message(message, level, context)

def set_tag(key: str, value: str):
    """Set a tag for error events."""
    error_logger.set_tag(key, value)

def set_context(name: str, data: Dict[str, Any]):
    """Set context data for error events."""
    error_logger.set_context(name, data)

def set_user_context(user_id: Optional[str] = None, email: Optional[str] = None, username: Optional[str] = None):
    """Set user context for error events."""
    error_logger.set_user_context(user_id, email, username)

def init_error_logger(service_name: str = "ai-test-case-generator"):
    """
    Initialize error logger (compatibility function for Sentry API)
    
    Args:
        service_name: Name of the service for tagging
    """
    error_logger.set_tag("service", service_name)
    error_logger.set_tag("version", "1.0.0")
    logger.info(f"Error logger initialized for service: {service_name}")
