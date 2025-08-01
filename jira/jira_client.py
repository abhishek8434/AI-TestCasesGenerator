import requests
from typing import Optional, Dict, Any
from config.settings import JIRA_URL, JIRA_USER, JIRA_API_TOKEN

def fetch_issue(issue_key: str, jira_config: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    """Fetch issue details from Jira.

    Args:
        issue_key (str): The Jira issue key
        jira_config (Optional[Dict[str, str]]): Optional Jira configuration override

    Returns:
        Optional[Dict[str, Any]]: Issue details or None if fetch fails
    """
    if not issue_key:
        print("❌ Issue key cannot be empty")
        return None

    # Use config values if provided, otherwise fall back to environment variables
    jira_url = jira_config.get('url', JIRA_URL) if jira_config else JIRA_URL
    jira_user = jira_config.get('user', JIRA_USER) if jira_config else JIRA_USER
    jira_token = jira_config.get('token', JIRA_API_TOKEN) if jira_config else JIRA_API_TOKEN
    
    # Ensure jira_url is not empty and has a proper scheme
    if not jira_url:
        print("❌ Jira URL cannot be empty")
        return None
    
    # Ensure URL has a scheme (http:// or https://)
    if not jira_url.startswith(('http://', 'https://')):
        jira_url = 'https://' + jira_url
    
    # Remove trailing slashes
    jira_url = jira_url.rstrip('/')

    url = f"{jira_url}/rest/api/3/issue/{issue_key}"
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(
            url,
            auth=(jira_user, jira_token),
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to fetch issue: {e}")
        return None
    except requests.exceptions.JSONDecodeError as e:
        print(f"❌ Error decoding JSON: {e}")
        return None
