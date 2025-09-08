import os
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Only OpenAI API key is required from .env
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.error("⚠️ Missing OPENAI_API_KEY in environment variables")
    # Don't raise exception here, let the application handle it
    # instead of crashing at startup
    OPENAI_API_KEY = "missing_api_key"

# OpenRouter API configuration for fallback
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:5008")
OPENROUTER_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", "AI Test Case Generator")

# Optional environment variables with default values
BASE_URL = os.getenv("BASE_URL", "http://localhost:5008")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
LOG_FILE = os.getenv("LOG_FILE", "app.log")

# Jira settings (optional, will be set through frontend)
JIRA_URL = os.getenv("JIRA_URL", "")
JIRA_USER = os.getenv("JIRA_USER", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

# Azure DevOps settings (optional, will be set through frontend)
AZURE_DEVOPS_URL = os.getenv("AZURE_DEVOPS_URL", "")
AZURE_DEVOPS_ORG = os.getenv("AZURE_DEVOPS_ORG", "")
AZURE_DEVOPS_PROJECT = os.getenv("AZURE_DEVOPS_PROJECT", "")
AZURE_DEVOPS_PAT = os.getenv("AZURE_DEVOPS_PAT", "")
AZURE_DEVOPS_WORKITEM_ID = os.getenv("AZURE_DEVOPS_WORKITEM_ID", "")


# Only check for truly required variables
required_vars = [OPENAI_API_KEY]
missing_vars = [name for name, value in zip(["OPENAI_API_KEY"], required_vars) if not value or value == "missing_api_key"]

if missing_vars:
    logger.warning(f"⚠️ Missing required environment variables: {', '.join(missing_vars)}")
    logger.warning("⚠️ The application may not function properly without these variables.")


# MongoDB settings
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "")

# Email notification settings
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"

# Email recipients (comma-separated list)
EMAIL_RECIPIENTS_STR = os.getenv("EMAIL_RECIPIENTS", "")
EMAIL_RECIPIENTS = [email.strip() for email in EMAIL_RECIPIENTS_STR.split(",") if email.strip()] if EMAIL_RECIPIENTS_STR else []