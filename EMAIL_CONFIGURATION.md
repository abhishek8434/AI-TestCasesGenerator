# Email Notification Configuration

This document explains how to configure email notifications for critical errors and system failures in the AI Test Case Generator.

## Overview

The system now includes automatic email notifications for:
- Critical errors and system failures
- API failures (OpenAI, Jira, Azure DevOps)
- System performance issues
- Authentication and permission errors

## Environment Variables

Add the following environment variables to your `.env` file:

```bash
# Email Notification Configuration
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_FROM_ADDRESS=your-email@gmail.com
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false

# Email Recipients (comma-separated list)
EMAIL_RECIPIENTS=admin@yourcompany.com,devops@yourcompany.com
```

## Configuration Examples

### Gmail Configuration
```bash
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=your-app-password  # Use App Password, not regular password
EMAIL_FROM_ADDRESS=your-email@gmail.com
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

### Outlook/Hotmail Configuration
```bash
EMAIL_SMTP_SERVER=smtp-mail.outlook.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@outlook.com
EMAIL_PASSWORD=your-password
EMAIL_FROM_ADDRESS=your-email@outlook.com
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

### Custom SMTP Server
```bash
EMAIL_SMTP_SERVER=mail.yourcompany.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=alerts@yourcompany.com
EMAIL_PASSWORD=your-password
EMAIL_FROM_ADDRESS=alerts@yourcompany.com
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

## Gmail Setup Instructions

1. Enable 2-Factor Authentication on your Gmail account
2. Generate an App Password:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"
   - Use this app password in the `EMAIL_PASSWORD` variable

## Testing Email Configuration

### Test Endpoints

1. **Test Email Configuration**: `GET /test-email`
   - Sends a test email to verify SMTP configuration
   - Returns success/error status

2. **Test Error Notification**: `GET /test-error-notification`
   - Simulates a critical error and sends notification email
   - Tests the complete error notification flow

### Manual Testing

You can test the email system by visiting:
- `http://localhost:5008/test-email`
- `http://localhost:5008/test-error-notification`

## Email Types

### 1. Critical Error Notifications
- **Trigger**: System errors, API failures, authentication issues
- **Subject**: `🚨 CRITICAL ERROR ALERT - [ERROR_TYPE] - AI Test Case Generator`
- **Content**: Detailed error information, stack trace, context

### 2. API Failure Notifications
- **Trigger**: OpenAI, Jira, or Azure DevOps API failures
- **Subject**: `⚠️ API FAILURE - [API_NAME] - AI Test Case Generator`
- **Content**: API endpoint, error details, request/response data

### 3. System Alerts
- **Trigger**: Performance issues, system warnings
- **Subject**: `🔴/🟡/🔵 SYSTEM ALERT - [ALERT_TYPE] - AI Test Case Generator`
- **Content**: Alert details, performance metrics, recommendations

## Monitoring Features

### Automatic Monitoring
The system automatically monitors:
- OpenAI API calls in test case generation
- Jira API calls for issue fetching
- Azure DevOps API calls for work item retrieval
- Critical system functions
- Database operations

### Error Classification
Errors are automatically classified as critical if they contain:
- Connection errors, timeouts, SSL errors
- Authentication failures, permission denied
- API key issues, service unavailable
- Memory errors, system errors

## Disabling Email Notifications

To disable email notifications, simply remove or comment out the email configuration variables. The system will log warnings but continue to function normally.

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Check username and password
   - For Gmail, ensure you're using an App Password
   - Verify 2FA is enabled for Gmail

2. **Connection Refused**
   - Check SMTP server and port
   - Verify firewall settings
   - Test network connectivity

3. **Emails Not Received**
   - Check spam/junk folders
   - Verify recipient email addresses
   - Check SMTP server logs

### Debug Mode

Enable debug logging to troubleshoot email issues:
```python
import logging
logging.getLogger('utils.email_notifier').setLevel(logging.DEBUG)
```

## Security Considerations

1. **Use App Passwords**: Never use your main email password
2. **Environment Variables**: Store credentials in environment variables, not in code
3. **Access Control**: Limit email recipient list to authorized personnel
4. **Rate Limiting**: The system includes built-in rate limiting to prevent spam

## Production Recommendations

1. **Dedicated Email Account**: Use a dedicated email account for system notifications
2. **Multiple Recipients**: Configure multiple recipients for redundancy
3. **Monitoring**: Set up monitoring for the email notification system itself
4. **Backup**: Consider backup notification methods (SMS, Slack, etc.)

## Integration with Existing Monitoring

The email notification system integrates with:
- MongoDB error logging
- Application logging
- Performance monitoring
- User context tracking

All notifications include relevant context and can be correlated with application logs for comprehensive error analysis.
