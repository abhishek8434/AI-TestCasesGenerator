# Initialize Sentry for configuration
from utils.sentry_config import init_sentry, capture_exception, capture_message, set_tag, set_context

# Initialize Sentry for the configuration
init_sentry("ai-test-case-generator-config")

import os
import logging
from dotenv import load_dotenv

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

# Optional environment variables with default values
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

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


# Only check for required variables (OpenAI API key is already handled above)
# Azure, Jira, and other settings are optional and can be configured through the frontend


# MongoDB settings
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "")
