"""
Centralized Sentry configuration for the AI Test Case Generator application.
This module provides a single point of configuration for Sentry error tracking.
"""

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging
import os

def init_sentry(service_name: str = "ai-test-case-generator"):
    """
    Initialize Sentry with consistent configuration across all modules.
    
    Args:
        service_name (str): Name of the service for Sentry tagging
    """
    # Check if Sentry is already initialized
    if sentry_sdk.Hub.current.client is not None:
        return
    
    # Get environment-specific configuration
    environment = os.getenv("SENTRY_ENVIRONMENT", "development")
    
    sentry_sdk.init(
        dsn="https://ce0ca81a1ce6cadb7b4d69bb43cb3ffb@o4509711455420416.ingest.us.sentry.io/4509769068314624",
        
        # Environment configuration
        environment=environment,
        
        # Enable Flask integration for web requests
        integrations=[
            FlaskIntegration(),
            LoggingIntegration(
                level=logging.INFO,        # Capture info and above as breadcrumbs
                event_level=logging.ERROR  # Send errors as events
            ),
        ],
        
        # Performance monitoring
        traces_sample_rate=1.0,
        
        # Data collection settings
        send_default_pii=True,  # Include user data like IP, headers
        
        # Before send filter to remove sensitive data
        before_send=lambda event, hint: filter_sensitive_data(event, hint),
        
        # Debug mode for development
        debug=environment == "development",
        
        # Disable default integrations to avoid conflicts
        default_integrations=False
    )
    
    # Set tags after initialization
    sentry_sdk.set_tag("service", service_name)
    sentry_sdk.set_tag("version", "1.0.0")

def filter_sensitive_data(event, hint):
    """
    Filter out sensitive data before sending to Sentry.
    
    Args:
        event: The event to be sent to Sentry
        hint: Additional context about the event
        
    Returns:
        The filtered event or None to drop the event
    """
    # Remove sensitive data from request context
    if 'request' in event:
        # Remove API keys from headers
        if 'headers' in event['request']:
            sensitive_headers = ['authorization', 'x-api-key', 'api-key']
            for header in sensitive_headers:
                if header in event['request']['headers']:
                    event['request']['headers'][header] = '[REDACTED]'
    
    # Remove sensitive data from extra context
    if 'extra' in event:
        sensitive_keys = ['api_key', 'password', 'token', 'secret']
        for key in sensitive_keys:
            if key in event['extra']:
                event['extra'][key] = '[REDACTED]'
    
    return event

def capture_exception(exception, context=None):
    """
    Capture an exception with additional context.
    
    Args:
        exception: The exception to capture
        context (dict): Additional context to include
    """
    if context:
        sentry_sdk.set_context("additional_context", context)
    
    sentry_sdk.capture_exception(exception)

def capture_message(message, level="info", context=None):
    """
    Capture a message with specified level and context.
    
    Args:
        message (str): The message to capture
        level (str): Log level (debug, info, warning, error)
        context (dict): Additional context to include
    """
    if context:
        sentry_sdk.set_context("additional_context", context)
    
    sentry_sdk.capture_message(message, level=level)

def set_user_context(user_id=None, email=None, username=None):
    """
    Set user context for Sentry events.
    
    Args:
        user_id (str): User ID
        email (str): User email
        username (str): Username
    """
    user_data = {}
    if user_id:
        user_data['id'] = user_id
    if email:
        user_data['email'] = email
    if username:
        user_data['username'] = username
    
    if user_data:
        sentry_sdk.set_user(user_data)

def set_tag(key, value):
    """
    Set a tag for Sentry events.
    
    Args:
        key (str): Tag key
        value (str): Tag value
    """
    sentry_sdk.set_tag(key, value)

def set_context(name, data):
    """
    Set context data for Sentry events.
    
    Args:
        name (str): Context name
        data (dict): Context data
    """
    sentry_sdk.set_context(name, data) 
