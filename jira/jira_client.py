# Import error logging utilities for error tracking
from utils.error_logger import capture_exception, capture_message, set_tag, set_context
from utils.error_monitor import monitor_jira_api, monitor_critical_system

import requests
from typing import Optional, Dict, Any, List
from config.settings import JIRA_URL, JIRA_USER, JIRA_API_TOKEN

@monitor_critical_system
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
        # Make the API call with monitoring
        @monitor_jira_api(critical=True)
        def make_jira_request():
            return requests.get(
                url,
                auth=(jira_user, jira_token),
                headers=headers,
                timeout=30
            )
        
        response = make_jira_request()
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to fetch issue: {e}")
        return None
    except requests.exceptions.JSONDecodeError as e:
        print(f"❌ Error decoding JSON: {e}")
        return None

class JiraClient:
    """Jira API client for connection testing and item fetching"""
    
    def __init__(self, jira_url: str, jira_user: str, jira_token: str):
        self.jira_url = jira_url.rstrip('/')
        self.jira_user = jira_user
        self.jira_token = jira_token
        self.headers = {"Accept": "application/json"}
    
    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get current user information"""
        try:
            url = f"{self.jira_url}/rest/api/3/myself"
            response = requests.get(
                url,
                auth=(self.jira_user, self.jira_token),
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to get current user: {e}")
            return None
    
    def get_recent_issues(self, limit: int = None, statuses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get recent issues for suggestions
        :param limit: maximum number of issues to return (None for all)
        :param statuses: optional list of status names to filter by (e.g., ["To Do", "Ready for QA"]) 
        """
        try:
            url = f"{self.jira_url}/rest/api/3/search"
            jql_clauses = []
            if statuses:
                quoted_statuses = ", ".join([f'"{s}"' for s in statuses])
                jql_clauses.append(f"status in ({quoted_statuses})")
            # Always order by last updated
            jql_clauses.append("ORDER BY updated DESC")
            jql = " ".join(jql_clauses)
            
            # Use a large number if limit is None to get all results
            max_results = limit if limit is not None else 1000
            
            payload = {
                "jql": jql,
                "maxResults": max_results,
                "fields": ["summary", "issuetype", "status"]
            }
            
            response = requests.post(
                url,
                auth=(self.jira_user, self.jira_token),
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get('issues', [])
        except Exception as e:
            print(f"❌ Failed to get recent issues: {e}")
            return []
