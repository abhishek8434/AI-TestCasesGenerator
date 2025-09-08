"""
Email notification service for critical errors and system failures.
This module provides automatic email notifications when critical errors occur.
"""

import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Dict, Any, Optional, List
import os
import traceback
import json
from config.settings import (
    EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_USERNAME, EMAIL_PASSWORD,
    EMAIL_RECIPIENTS, EMAIL_FROM_ADDRESS, EMAIL_USE_TLS, EMAIL_USE_SSL
)

logger = logging.getLogger(__name__)

class EmailNotifier:
    """Email notification service for critical errors and system alerts"""
    
    def __init__(self):
        """Initialize the email notifier with SMTP configuration"""
        self.smtp_server = EMAIL_SMTP_SERVER
        self.smtp_port = EMAIL_SMTP_PORT
        self.username = EMAIL_USERNAME
        self.password = EMAIL_PASSWORD
        self.recipients = EMAIL_RECIPIENTS
        self.from_address = EMAIL_FROM_ADDRESS
        self.use_tls = EMAIL_USE_TLS
        self.use_ssl = EMAIL_USE_SSL
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate email configuration"""
        required_configs = [
            ('SMTP_SERVER', self.smtp_server),
            ('SMTP_PORT', self.smtp_port),
            ('USERNAME', self.username),
            ('PASSWORD', self.password),
            ('RECIPIENTS', self.recipients),
            ('FROM_ADDRESS', self.from_address)
        ]
        
        missing_configs = []
        for name, value in required_configs:
            if not value:
                missing_configs.append(name)
        
        if missing_configs:
            logger.warning(f"Email notification disabled - missing configuration: {', '.join(missing_configs)}")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Email notification service initialized successfully")
    
    def send_critical_error_notification(self, error_type: str, error_message: str, 
                                       context: Optional[Dict[str, Any]] = None,
                                       exception: Optional[Exception] = None,
                                       user_context: Optional[Dict[str, str]] = None,
                                       recipients: Optional[List[str]] = None) -> bool:
        """
        Send critical error notification email
        
        Args:
            error_type: Type of error (API_FAILURE, SYSTEM_ERROR, etc.)
            error_message: Error message
            context: Additional context data
            exception: Exception object if available
            user_context: User information if available
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email notifications disabled - skipping critical error notification")
            return False
        
        try:
            subject = f"🚨 CRITICAL ERROR ALERT - {error_type} - AI Test Case Generator"
            
            # Create email body
            body = self._create_error_email_body(
                error_type, error_message, context, exception, user_context
            )
            
            # Send email
            return self._send_email(subject, body, is_html=True, recipients=recipients)
            
        except Exception as e:
            logger.error(f"Failed to send critical error notification: {str(e)}")
            return False
    
    def send_api_failure_notification(self, api_name: str, endpoint: str, 
                                    error_message: str, status_code: Optional[int] = None,
                                    response_data: Optional[Dict] = None,
                                    request_data: Optional[Dict] = None) -> bool:
        """
        Send API failure notification email
        
        Args:
            api_name: Name of the API (OpenAI, Jira, Azure, etc.)
            endpoint: API endpoint that failed
            error_message: Error message
            status_code: HTTP status code if available
            response_data: API response data if available
            request_data: Request data if available
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email notifications disabled - skipping API failure notification")
            return False
        
        try:
            subject = f"⚠️ API FAILURE - {api_name} - AI Test Case Generator"
            
            # Create email body
            body = self._create_api_failure_email_body(
                api_name, endpoint, error_message, status_code, response_data, request_data
            )
            
            # Send email
            return self._send_email(subject, body, is_html=True)
            
        except Exception as e:
            logger.error(f"Failed to send API failure notification: {str(e)}")
            return False
    
    def send_system_alert(self, alert_type: str, message: str, 
                         severity: str = "WARNING", context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Send system alert notification
        
        Args:
            alert_type: Type of alert (PERFORMANCE, SECURITY, etc.)
            message: Alert message
            severity: Alert severity (INFO, WARNING, CRITICAL)
            context: Additional context data
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email notifications disabled - skipping system alert")
            return False
        
        try:
            emoji = "🔴" if severity == "CRITICAL" else "🟡" if severity == "WARNING" else "🔵"
            subject = f"{emoji} SYSTEM ALERT - {alert_type} - AI Test Case Generator"
            
            # Create email body
            body = self._create_system_alert_email_body(alert_type, message, severity, context)
            
            # Send email
            return self._send_email(subject, body, is_html=True)
            
        except Exception as e:
            logger.error(f"Failed to send system alert: {str(e)}")
            return False
    
    def _create_error_email_body(self, error_type: str, error_message: str,
                                context: Optional[Dict[str, Any]] = None,
                                exception: Optional[Exception] = None,
                                user_context: Optional[Dict[str, str]] = None) -> str:
        """Create HTML email body for critical errors"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Get traceback if exception provided
        traceback_info = ""
        if exception:
            try:
                traceback_info = ''.join(traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                ))
            except:
                traceback_info = "Unable to extract traceback"
        
        # Format context data
        context_html = ""
        if context:
            context_html = f"""
            <h3>📋 Additional Context:</h3>
            <pre style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto;">{json.dumps(context, indent=2)}</pre>
            """
        
        # Format user context
        user_html = ""
        if user_context:
            user_html = f"""
            <h3>👤 User Information:</h3>
            <ul>
                {''.join([f'<li><strong>{k}:</strong> {v}</li>' for k, v in user_context.items()])}
            </ul>
            """
        
        # Format traceback
        traceback_html = ""
        if traceback_info:
            traceback_html = f"""
            <h3>🔍 Stack Trace:</h3>
            <pre style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; font-size: 12px;">{traceback_info}</pre>
            """
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Critical Error Alert</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #dc3545; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">🚨 CRITICAL ERROR ALERT</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px;">AI Test Case Generator System</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h2 style="color: #dc3545; margin-top: 0;">Error Details</h2>
                    <p><strong>⏰ Timestamp:</strong> {timestamp}</p>
                    <p><strong>🔧 Error Type:</strong> {error_type}</p>
                    <p><strong>📝 Error Message:</strong></p>
                    <div style="background-color: #fff; padding: 15px; border-left: 4px solid #dc3545; margin: 10px 0;">
                        <code style="color: #dc3545; font-size: 14px;">{error_message}</code>
                    </div>
                </div>
                
                {user_html}
                {context_html}
                {traceback_html}
                
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-top: 20px;">
                    <h3>🔧 Recommended Actions:</h3>
                    <ul>
                        <li>Check the application logs for more details</li>
                        <li>Verify system resources and connectivity</li>
                        <li>Review recent deployments or configuration changes</li>
                        <li>Monitor system performance and user impact</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
                    <p style="color: #6c757d; font-size: 12px;">
                        This is an automated alert from the AI Test Case Generator monitoring system.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_body
    
    def _create_api_failure_email_body(self, api_name: str, endpoint: str, 
                                     error_message: str, status_code: Optional[int] = None,
                                     response_data: Optional[Dict] = None,
                                     request_data: Optional[Dict] = None) -> str:
        """Create HTML email body for API failures"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Format response data
        response_html = ""
        if response_data:
            response_html = f"""
            <h3>📤 API Response:</h3>
            <pre style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto;">{json.dumps(response_data, indent=2)}</pre>
            """
        
        # Format request data
        request_html = ""
        if request_data:
            request_html = f"""
            <h3>📥 Request Data:</h3>
            <pre style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto;">{json.dumps(request_data, indent=2)}</pre>
            """
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>API Failure Alert</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #fd7e14; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">⚠️ API FAILURE ALERT</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px;">AI Test Case Generator System</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h2 style="color: #fd7e14; margin-top: 0;">API Failure Details</h2>
                    <p><strong>⏰ Timestamp:</strong> {timestamp}</p>
                    <p><strong>🔌 API Name:</strong> {api_name}</p>
                    <p><strong>🌐 Endpoint:</strong> <code>{endpoint}</code></p>
                    {f'<p><strong>📊 Status Code:</strong> <span style="color: #dc3545;">{status_code}</span></p>' if status_code else ''}
                    <p><strong>📝 Error Message:</strong></p>
                    <div style="background-color: #fff; padding: 15px; border-left: 4px solid #fd7e14; margin: 10px 0;">
                        <code style="color: #dc3545; font-size: 14px;">{error_message}</code>
                    </div>
                </div>
                
                {request_html}
                {response_html}
                
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-top: 20px;">
                    <h3>🔧 Recommended Actions:</h3>
                    <ul>
                        <li>Check API service status and connectivity</li>
                        <li>Verify API credentials and authentication</li>
                        <li>Review API rate limits and quotas</li>
                        <li>Check for API endpoint changes or deprecations</li>
                        <li>Monitor API response times and error rates</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
                    <p style="color: #6c757d; font-size: 12px;">
                        This is an automated alert from the AI Test Case Generator monitoring system.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_body
    
    def _create_system_alert_email_body(self, alert_type: str, message: str, 
                                      severity: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Create HTML email body for system alerts"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Set color based on severity
        color = "#dc3545" if severity == "CRITICAL" else "#fd7e14" if severity == "WARNING" else "#17a2b8"
        emoji = "🔴" if severity == "CRITICAL" else "🟡" if severity == "WARNING" else "🔵"
        
        # Format context data
        context_html = ""
        if context:
            context_html = f"""
            <h3>📋 Additional Context:</h3>
            <pre style="background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto;">{json.dumps(context, indent=2)}</pre>
            """
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>System Alert</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 800px; margin: 0 auto; padding: 20px;">
                <div style="background-color: {color}; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">{emoji} SYSTEM ALERT</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px;">AI Test Case Generator System</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h2 style="color: {color}; margin-top: 0;">Alert Details</h2>
                    <p><strong>⏰ Timestamp:</strong> {timestamp}</p>
                    <p><strong>🚨 Alert Type:</strong> {alert_type}</p>
                    <p><strong>⚡ Severity:</strong> <span style="color: {color}; font-weight: bold;">{severity}</span></p>
                    <p><strong>📝 Message:</strong></p>
                    <div style="background-color: #fff; padding: 15px; border-left: 4px solid {color}; margin: 10px 0;">
                        <p style="margin: 0; color: {color}; font-size: 14px;">{message}</p>
                    </div>
                </div>
                
                {context_html}
                
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-top: 20px;">
                    <h3>🔧 Recommended Actions:</h3>
                    <ul>
                        <li>Review system logs and monitoring dashboards</li>
                        <li>Check system resources and performance metrics</li>
                        <li>Verify system configuration and dependencies</li>
                        <li>Monitor for any user impact or service degradation</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
                    <p style="color: #6c757d; font-size: 12px;">
                        This is an automated alert from the AI Test Case Generator monitoring system.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_body
    
    def _send_email(self, subject: str, body: str, is_html: bool = True, recipients: List[str] = None) -> bool:
        """
        Send email using SMTP
        
        Args:
            subject: Email subject
            body: Email body
            is_html: Whether the body is HTML format
            recipients: List of email recipients (defaults to configured recipients)
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Use provided recipients or default to configured recipients
            email_recipients = recipients if recipients else self.recipients
            
            if not email_recipients:
                logger.error("No email recipients specified")
                return False
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_address
            msg['To'] = ', '.join(email_recipients)
            
            # Add body
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            # Create SMTP session
            if self.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                if self.use_tls:
                    server.starttls()
            
            # Login and send email
            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent successfully to {', '.join(email_recipients)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def send_password_reset_email(self, email: str, reset_token: str, expires_at: datetime) -> bool:
        """
        Send password reset email
        
        Args:
            email: User's email address
            reset_token: Password reset token
            expires_at: Token expiration time
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email notifications disabled - cannot send password reset email")
            return False
        
        try:
            from config.settings import BASE_URL
            
            subject = "🔐 Password Reset Request - AI Test Case Generator"
            
            # Create reset link
            reset_link = f"{BASE_URL}/reset-password-confirm?token={reset_token}"
            
            # Format expiration time
            expires_str = expires_at.strftime("%B %d, %Y at %I:%M %p UTC")
            
            # Create email body
            body = self._create_password_reset_email_body(email, reset_link, expires_str)
            
            # Send email to the specific user
            return self._send_email(subject, body, is_html=True, recipients=[email])
            
        except Exception as e:
            logger.error(f"Failed to send password reset email: {str(e)}")
            return False

    def _create_password_reset_email_body(self, email: str, reset_link: str, expires_str: str) -> str:
        """Create HTML email body for password reset"""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Password Reset Request</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #007bff; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">🔐 Password Reset Request</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px;">AI Test Case Generator</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
                    <h2 style="color: #007bff; margin-top: 0;">Reset Your Password</h2>
                    <p>Hello,</p>
                    <p>We received a request to reset your password for your AI Test Case Generator account associated with <strong>{email}</strong>.</p>
                    
                    <div style="background-color: #fff; padding: 20px; border-radius: 5px; margin: 20px 0; text-align: center;">
                        <p style="margin: 0 0 15px 0; font-weight: bold;">Click the button below to reset your password:</p>
                        <a href="{reset_link}" style="display: inline-block; background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">
                            Reset My Password
                        </a>
                    </div>
                    
                    <p style="margin: 20px 0 10px 0;"><strong>Or copy and paste this link into your browser:</strong></p>
                    <div style="background-color: #e9ecef; padding: 10px; border-radius: 5px; word-break: break-all; font-family: monospace; font-size: 14px;">
                        {reset_link}
                    </div>
                </div>
                
                <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h3 style="color: #856404; margin-top: 0;">⚠️ Important Security Information</h3>
                    <ul style="color: #856404; margin: 0;">
                        <li>This link will expire on <strong>{expires_str}</strong></li>
                        <li>The link can only be used once</li>
                        <li>If you didn't request this password reset, please ignore this email</li>
                        <li>Your password will remain unchanged until you click the link above</li>
                    </ul>
                </div>
                
                <div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
                    <h3 style="margin-top: 0;">🔒 Security Tips</h3>
                    <ul style="margin: 0;">
                        <li>Choose a strong, unique password</li>
                        <li>Don't share your password with anyone</li>
                        <li>Log out of your account when using shared computers</li>
                        <li>Contact support if you notice any suspicious activity</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
                    <p style="color: #6c757d; font-size: 12px; margin: 0;">
                        This email was sent on {timestamp}<br>
                        If you have any questions, please contact our support team.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_body

    def test_email_configuration(self) -> bool:
        """
        Test email configuration by sending a test email
        
        Returns:
            bool: True if test email sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email notifications disabled - cannot test configuration")
            return False
        
        try:
            subject = "🧪 Email Configuration Test - AI Test Case Generator"
            body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Email Test</title>
            </head>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #28a745; color: white; padding: 20px; border-radius: 10px; text-align: center;">
                        <h1 style="margin: 0;">✅ Email Configuration Test Successful</h1>
                    </div>
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-top: 20px;">
                        <p><strong>Timestamp:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
                        <p><strong>Service:</strong> AI Test Case Generator</p>
                        <p><strong>Status:</strong> Email notifications are working correctly</p>
                    </div>
                    <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6;">
                        <p style="color: #6c757d; font-size: 12px;">
                            This is a test email to verify email notification configuration.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            return self._send_email(subject, body, is_html=True)
            
        except Exception as e:
            logger.error(f"Failed to send test email: {str(e)}")
            return False

# Global email notifier instance
email_notifier = EmailNotifier()

# Convenience functions
def send_critical_error_notification(error_type: str, error_message: str, 
                                   context: Optional[Dict[str, Any]] = None,
                                   exception: Optional[Exception] = None,
                                   user_context: Optional[Dict[str, str]] = None,
                                   recipients: Optional[List[str]] = None) -> bool:
    """Send critical error notification email"""
    return email_notifier.send_critical_error_notification(
        error_type, error_message, context, exception, user_context, recipients
    )

def send_api_failure_notification(api_name: str, endpoint: str, 
                                error_message: str, status_code: Optional[int] = None,
                                response_data: Optional[Dict] = None,
                                request_data: Optional[Dict] = None) -> bool:
    """Send API failure notification email"""
    return email_notifier.send_api_failure_notification(
        api_name, endpoint, error_message, status_code, response_data, request_data
    )

def send_system_alert(alert_type: str, message: str, 
                     severity: str = "WARNING", context: Optional[Dict[str, Any]] = None) -> bool:
    """Send system alert notification email"""
    return email_notifier.send_system_alert(alert_type, message, severity, context)

def send_password_reset_email(email: str, reset_token: str, expires_at: datetime) -> bool:
    """Send password reset email"""
    return email_notifier.send_password_reset_email(email, reset_token, expires_at)

def test_email_configuration() -> bool:
    """Test email configuration"""
    return email_notifier.test_email_configuration()
