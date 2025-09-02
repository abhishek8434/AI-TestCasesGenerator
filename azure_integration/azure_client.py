# Import error logging utilities for error tracking
from utils.error_logger import capture_exception, capture_message, set_tag, set_context

import os
import requests
import base64
from bs4 import BeautifulSoup
from config.settings import AZURE_DEVOPS_URL, AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_PAT

class AzureClient:
    def __init__(self, azure_url=None, azure_org=None, azure_pat=None, azure_config=None):
        print(f"🔧 AzureClient constructor called with: azure_config={azure_config}")
        
        if azure_config:
            # Use config values if provided, otherwise fall back to environment variables
            self.azure_url = azure_config.get('url', AZURE_DEVOPS_URL)
            self.azure_org = azure_config.get('org', AZURE_DEVOPS_ORG)
            self.azure_project = azure_config.get('project', AZURE_DEVOPS_PROJECT)
            self.azure_pat = azure_config.get('pat', AZURE_DEVOPS_PAT)
            print(f"🔧 Using azure_config - URL: '{self.azure_url}', Org: '{self.azure_org}', Project: '{self.azure_project}', PAT: {'*' * len(self.azure_pat) if self.azure_pat else 'None'}")
        else:
            # Use direct parameters if provided
            self.azure_url = azure_url or AZURE_DEVOPS_URL
            self.azure_org = azure_org or AZURE_DEVOPS_ORG
            self.azure_project = None  # Will be set per operation
            self.azure_pat = azure_pat or AZURE_DEVOPS_PAT
            print(f"🔧 Using direct params - URL: '{self.azure_url}', Org: '{self.azure_org}', Project: '{self.azure_project}', PAT: {'*' * len(self.azure_pat) if self.azure_pat else 'None'}")
            
        self.last_error = None  # Store the last error message
        
        # Ensure azure_url is properly formatted
        if self.azure_url and isinstance(self.azure_url, str):
            # Add scheme if missing
            if not self.azure_url.startswith(('http://', 'https://')):
                self.azure_url = 'https://' + self.azure_url
            
            # Remove trailing slashes
            self.azure_url = self.azure_url.rstrip('/')
        elif not isinstance(self.azure_url, str):
            print(f"❌ Invalid azure_url type: {type(self.azure_url)}, expected string")
            self.azure_url = None

    def fetch_azure_work_items(self, work_item_ids=None):
        if not work_item_ids:
            work_item_ids = os.getenv("AZURE_DEVOPS_WORKITEM_IDS", "").split(",")
            work_item_ids = [id.strip() for id in work_item_ids if id.strip()]

        if not work_item_ids:
            print("⚠️ Work item IDs not found. Please set AZURE_DEVOPS_WORKITEM_IDS in your .env file.")
            return None

        # Validate required fields
        print(f"🔍 Validating Azure fields - URL: '{self.azure_url}', Org: '{self.azure_org}', Project: '{self.azure_project}', PAT: {'*' * len(self.azure_pat) if self.azure_pat else 'None'}")
        
        if not self.azure_url:
            self.last_error = "Azure DevOps URL cannot be empty"
            print("❌ Azure DevOps URL cannot be empty")
            return None
            
        if not self.azure_org:
            self.last_error = "Azure DevOps organization cannot be empty"
            print("❌ Azure DevOps organization cannot be empty")
            return None
            
        if not self.azure_project:
            self.last_error = "Azure DevOps project cannot be empty"
            print("❌ Azure DevOps project cannot be empty")
            return None
            
        if not self.azure_pat:
            self.last_error = "Azure DevOps Personal Access Token cannot be empty"
            print("❌ Azure DevOps Personal Access Token cannot be empty")
            return None

        results = []
        for work_item_id in work_item_ids:
            url = f"{self.azure_url}/{self.azure_org}/{self.azure_project}/_apis/wit/workitems/{work_item_id}?api-version=6.0"
            headers = {
                "Accept": "application/json",
                "Authorization": f"Basic {base64.b64encode(f':{self.azure_pat}'.encode()).decode()}"
            }

            try:
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    work_item = response.json()
                    
                    # Clean HTML tags from the description
                    def clean_html(text):
                        soup = BeautifulSoup(text, "html.parser")
                        return soup.get_text()

                    description = work_item.get("fields", {}).get("System.Description", "No Description Found")
                    description_cleaned = clean_html(description)
                    title = work_item.get("fields", {}).get("System.Title", "No Title Found")
                    
                    results.append({
                        "id": work_item_id,
                        "title": title,
                        "description": description_cleaned
                    })
                    print(f"✅ Successfully fetched work item {work_item_id}")
                else:
                    error_msg = f"Failed to fetch work item {work_item_id}: {response.status_code}"
                    self.last_error = error_msg
                    print(f"❌ {error_msg}")
            except Exception as e:
                error_msg = f"Error processing work item {work_item_id}: {str(e)}"
                self.last_error = error_msg
                print(f"❌ {error_msg}")
                # Capture error in MongoDB
                capture_exception(e, {
                    "work_item_id": work_item_id,
                    "azure_url": self.azure_url,
                    "azure_org": self.azure_org,
                    "azure_project": self.azure_project,
                    "response_status": getattr(response, 'status_code', None)
                })

        return results

    def get_project(self, project_name: str):
        """Get project information"""
        try:
            url = f"{self.azure_url}/{self.azure_org}/_apis/projects/{project_name}?api-version=6.0"
            headers = {
                "Accept": "application/json",
                "Authorization": f"Basic {base64.b64encode(f':{self.azure_pat}'.encode()).decode()}"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to get project {project_name}: {e}")
            return None

    def get_recent_work_items(self, project_name: str, limit: int = None, states=None):
        """Get recent work items for suggestions
        :param project_name: Azure DevOps project name
        :param limit: Max number of items to return (None for all, details fetch still respects this cap)
        :param states: Optional list of state names to filter by (e.g., ['Ready for QA', 'Re-open'])
        """
        try:
            print(f"🔍 Fetching work items for project: {project_name}")
            url = f"{self.azure_url}/{self.azure_org}/{project_name}/_apis/wit/wiql?api-version=6.0"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Basic {base64.b64encode(f':{self.azure_pat}'.encode()).decode()}"
            }
            
            # WIQL query to get recent work items (optionally filtered by state)
            where_clauses = [f"[System.TeamProject] = '{project_name}'"]
            if states and isinstance(states, (list, tuple)) and len(states) > 0:
                # Build an IN clause for the provided states
                # Quote each state value safely
                quoted_states = ", ".join([f"'{s}'" for s in states])
                where_clauses.append(f"[System.State] IN ({quoted_states})")

            where_sql = " AND ".join(where_clauses)
            wiql_query = (
                "SELECT [System.Id], [System.Title], [System.WorkItemType], [System.State] "
                "FROM WorkItems "
                f"WHERE {where_sql} "
                "ORDER BY [System.ChangedDate] DESC"
            )

            payload = {"query": wiql_query}
            
            print(f"🔍 Making WIQL request to: {url}")
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            print(f"🔍 WIQL response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ WIQL request failed: {response.status_code} - {response.text}")
                return []
            
            response.raise_for_status()
            result = response.json()
            work_items = result.get('workItems', [])
            print(f"🔍 Found {len(work_items)} work items in WIQL response")
            
            # Get details for each work item
            detailed_items = []
            # Use all items if limit is None, otherwise use the limit
            items_to_process = work_items if limit is None else work_items[:limit]
            for item in items_to_process:
                item_id = item['id']
                item_url = f"{self.azure_url}/{self.azure_org}/{project_name}/_apis/wit/workitems/{item_id}?api-version=6.0"
                
                item_response = requests.get(item_url, headers=headers, timeout=30)
                if item_response.status_code == 200:
                    detailed_items.append(item_response.json())
                else:
                    print(f"❌ Failed to get details for work item {item_id}: {item_response.status_code}")
            
            print(f"🔍 Successfully fetched details for {len(detailed_items)} work items")
            return detailed_items
        except Exception as e:
            print(f"❌ Failed to get recent work items: {e}")
            return []