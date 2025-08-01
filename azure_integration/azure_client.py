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
            print("❌ Azure DevOps URL cannot be empty")
            return None
            
        if not self.azure_org:
            print("❌ Azure DevOps organization cannot be empty")
            return None
            
        if not self.azure_project:
            print("❌ Azure DevOps project cannot be empty")
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
                    print(f"❌ Failed to fetch work item {work_item_id}: {response.status_code}")
            except Exception as e:
                print(f"❌ Error processing work item {work_item_id}: {str(e)}")

        return results
