# Initialize Sentry for Azure integration
from utils.sentry_config import init_sentry, capture_exception, capture_message, set_tag, set_context

# Initialize Sentry for the Azure integration
init_sentry("ai-test-case-generator-azure")

import os
import requests
import base64
from bs4 import BeautifulSoup
from config.settings import AZURE_DEVOPS_URL, AZURE_DEVOPS_ORG, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_PAT

class AzureClient:
    def __init__(self, azure_config=None):
        # Use config values if provided, otherwise fall back to environment variables
        self.azure_url = azure_config.get('url', AZURE_DEVOPS_URL) if azure_config else AZURE_DEVOPS_URL
        self.azure_org = azure_config.get('org', AZURE_DEVOPS_ORG) if azure_config else AZURE_DEVOPS_ORG
        self.azure_project = azure_config.get('project', AZURE_DEVOPS_PROJECT) if azure_config else AZURE_DEVOPS_PROJECT
        self.azure_pat = azure_config.get('pat', AZURE_DEVOPS_PAT) if azure_config else AZURE_DEVOPS_PAT
        self.last_error = None  # Store the last error message
        
        # Ensure azure_url is properly formatted
        if self.azure_url:
            # Add scheme if missing
            if not self.azure_url.startswith(('http://', 'https://')):
                self.azure_url = 'https://' + self.azure_url
            
            # Remove trailing slashes
            self.azure_url = self.azure_url.rstrip('/')

    def fetch_azure_work_items(self, work_item_ids=None):
        if not work_item_ids:
            work_item_ids = os.getenv("AZURE_DEVOPS_WORKITEM_IDS", "").split(",")
            work_item_ids = [id.strip() for id in work_item_ids if id.strip()]

        if not work_item_ids:
            print("⚠️ Work item IDs not found. Please set AZURE_DEVOPS_WORKITEM_IDS in your .env file.")
            return None

        # Validate required fields
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
                # Capture error in Sentry
                capture_exception(e, {
                    "work_item_id": work_item_id,
                    "azure_url": self.azure_url,
                    "azure_org": self.azure_org,
                    "azure_project": self.azure_project,
                    "response_status": getattr(response, 'status_code', None)
                })

        return results
