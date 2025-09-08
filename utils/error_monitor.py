"""
Error monitoring decorators and middleware for automatic error detection and notification.
This module provides decorators to automatically monitor API calls and system functions for errors.
"""

import functools
import logging
import time
import traceback
from typing import Dict, Any, Optional, Callable, Union
from datetime import datetime
import requests
from utils.error_logger import capture_exception, capture_message
from utils.email_notifier import (
    send_critical_error_notification, 
    send_api_failure_notification, 
    send_system_alert
)

logger = logging.getLogger(__name__)

class ErrorMonitor:
    """Error monitoring class with decorators and utilities"""
    
    @staticmethod
    def monitor_api_call(api_name: str, critical: bool = True, 
                        include_request_data: bool = True,
                        include_response_data: bool = True):
        """
        Decorator to monitor API calls and send notifications on failure
        
        Args:
            api_name: Name of the API (OpenAI, Jira, Azure, etc.)
            critical: Whether this API call is critical (sends email notification)
            include_request_data: Whether to include request data in notifications
            include_response_data: Whether to include response data in notifications
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                endpoint = "unknown"
                request_data = None
                response_data = None
                status_code = None
                
                try:
                    # Extract endpoint information if possible
                    if args and hasattr(args[0], 'url'):
                        endpoint = args[0].url
                    elif 'url' in kwargs:
                        endpoint = kwargs['url']
                    elif 'endpoint' in kwargs:
                        endpoint = kwargs['endpoint']
                    
                    # Extract request data if requested
                    if include_request_data:
                        request_data = {
                            'args': str(args)[:500] if args else None,  # Limit size
                            'kwargs': {k: str(v)[:200] for k, v in kwargs.items()} if kwargs else None
                        }
                    
                    logger.info(f"Making API call to {api_name}: {endpoint}")
                    
                    # Execute the function
                    result = func(*args, **kwargs)
                    
                    # Calculate execution time
                    execution_time = time.time() - start_time
                    
                    # Log successful API call
                    capture_message(
                        f"API call successful: {api_name}",
                        level="info",
                        context={
                            "api_name": api_name,
                            "endpoint": endpoint,
                            "execution_time": execution_time,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )
                    
                    return result
                    
                except requests.exceptions.RequestException as e:
                    # Handle HTTP/API specific errors
                    execution_time = time.time() - start_time
                    error_message = str(e)
                    
                    # Extract status code if available
                    if hasattr(e, 'response') and e.response is not None:
                        status_code = e.response.status_code
                        if include_response_data:
                            try:
                                response_data = e.response.json() if e.response.content else None
                            except:
                                response_data = {"error": "Unable to parse response"}
                    
                    # Log the error
                    capture_exception(e, {
                        "api_name": api_name,
                        "endpoint": endpoint,
                        "status_code": status_code,
                        "execution_time": execution_time,
                        "request_data": request_data,
                        "response_data": response_data
                    })
                    
                    # Send email notification if critical
                    if critical:
                        send_api_failure_notification(
                            api_name=api_name,
                            endpoint=endpoint,
                            error_message=error_message,
                            status_code=status_code,
                            response_data=response_data,
                            request_data=request_data
                        )
                    
                    # Re-raise the exception
                    raise
                    
                except Exception as e:
                    # Handle other types of errors
                    execution_time = time.time() - start_time
                    error_message = str(e)
                    
                    # Log the error
                    capture_exception(e, {
                        "api_name": api_name,
                        "endpoint": endpoint,
                        "execution_time": execution_time,
                        "request_data": request_data,
                        "error_type": type(e).__name__
                    })
                    
                    # Send email notification if critical
                    if critical:
                        send_critical_error_notification(
                            error_type=f"API_ERROR_{api_name}",
                            error_message=error_message,
                            context={
                                "api_name": api_name,
                                "endpoint": endpoint,
                                "execution_time": execution_time,
                                "request_data": request_data
                            },
                            exception=e
                        )
                    
                    # Re-raise the exception
                    raise
                    
            return wrapper
        return decorator
    
    @staticmethod
    def monitor_critical_function(function_name: str, 
                                include_context: bool = True,
                                alert_on_failure: bool = True):
        """
        Decorator to monitor critical system functions
        
        Args:
            function_name: Name of the function for logging/notification
            include_context: Whether to include function context in notifications
            alert_on_failure: Whether to send email alerts on failure
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                context = None
                
                try:
                    # Prepare context if requested
                    if include_context:
                        context = {
                            "function_name": function_name,
                            "args_count": len(args),
                            "kwargs_keys": list(kwargs.keys()) if kwargs else [],
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    
                    logger.info(f"Executing critical function: {function_name}")
                    
                    # Execute the function
                    result = func(*args, **kwargs)
                    
                    # Calculate execution time
                    execution_time = time.time() - start_time
                    
                    # Log successful execution
                    capture_message(
                        f"Critical function executed successfully: {function_name}",
                        level="info",
                        context={
                            "function_name": function_name,
                            "execution_time": execution_time,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )
                    
                    return result
                    
                except Exception as e:
                    # Handle errors
                    execution_time = time.time() - start_time
                    error_message = str(e)
                    
                    # Prepare error context
                    error_context = {
                        "function_name": function_name,
                        "execution_time": execution_time,
                        "error_type": type(e).__name__,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    if context:
                        error_context.update(context)
                    
                    # Log the error
                    capture_exception(e, error_context)
                    
                    # Send email notification if requested
                    if alert_on_failure:
                        send_critical_error_notification(
                            error_type=f"CRITICAL_FUNCTION_ERROR",
                            error_message=f"Critical function '{function_name}' failed: {error_message}",
                            context=error_context,
                            exception=e
                        )
                    
                    # Re-raise the exception
                    raise
                    
            return wrapper
        return decorator
    
    @staticmethod
    def monitor_system_health(component_name: str, 
                            alert_threshold: float = 5.0,
                            alert_on_slow_execution: bool = True):
        """
        Decorator to monitor system health and performance
        
        Args:
            component_name: Name of the system component
            alert_threshold: Execution time threshold in seconds for alerts
            alert_on_slow_execution: Whether to send alerts for slow execution
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    # Execute the function
                    result = func(*args, **kwargs)
                    
                    # Calculate execution time
                    execution_time = time.time() - start_time
                    
                    # Check for slow execution
                    if execution_time > alert_threshold and alert_on_slow_execution:
                        send_system_alert(
                            alert_type="PERFORMANCE_WARNING",
                            message=f"Slow execution detected in {component_name}: {execution_time:.2f}s (threshold: {alert_threshold}s)",
                            severity="WARNING",
                            context={
                                "component_name": component_name,
                                "execution_time": execution_time,
                                "threshold": alert_threshold,
                                "function_name": func.__name__
                            }
                        )
                    
                    # Log performance metrics
                    capture_message(
                        f"System component executed: {component_name}",
                        level="info",
                        context={
                            "component_name": component_name,
                            "execution_time": execution_time,
                            "function_name": func.__name__,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )
                    
                    return result
                    
                except Exception as e:
                    # Handle errors
                    execution_time = time.time() - start_time
                    error_message = str(e)
                    
                    # Log the error
                    capture_exception(e, {
                        "component_name": component_name,
                        "execution_time": execution_time,
                        "function_name": func.__name__,
                        "error_type": type(e).__name__
                    })
                    
                    # Send system alert
                    send_system_alert(
                        alert_type="COMPONENT_FAILURE",
                        message=f"System component '{component_name}' failed: {error_message}",
                        severity="CRITICAL",
                        context={
                            "component_name": component_name,
                            "execution_time": execution_time,
                            "function_name": func.__name__,
                            "error_type": type(e).__name__
                        }
                    )
                    
                    # Re-raise the exception
                    raise
                    
            return wrapper
        return decorator

# Convenience decorators
def monitor_openai_api(critical: bool = True):
    """Monitor OpenAI API calls"""
    return ErrorMonitor.monitor_api_call("OpenAI", critical=critical)

def monitor_jira_api(critical: bool = True):
    """Monitor Jira API calls"""
    return ErrorMonitor.monitor_api_call("Jira", critical=critical)

def monitor_azure_api(critical: bool = True):
    """Monitor Azure DevOps API calls"""
    return ErrorMonitor.monitor_api_call("Azure DevOps", critical=critical)

def monitor_critical_system(func=None, *, function_name: str = None):
    """Monitor critical system functions"""
    def decorator(f):
        name = function_name or f.__name__
        return ErrorMonitor.monitor_critical_function(name)(f)
    
    if func is None:
        return decorator
    else:
        return decorator(func)

def monitor_system_performance(component_name: str = None, threshold: float = 5.0):
    """Monitor system performance"""
    def decorator(func):
        name = component_name or func.__name__
        return ErrorMonitor.monitor_system_health(name, alert_threshold=threshold)
    return decorator

# Global error monitor instance
error_monitor = ErrorMonitor()
