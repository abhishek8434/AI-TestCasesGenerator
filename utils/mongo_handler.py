from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from config.settings import MONGODB_URI, MONGODB_DB
import uuid
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class MongoHandler:
    def __init__(self):
        try:
            self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            # Verify connection
            self.client.server_info()
            self.db = self.client[MONGODB_DB]
            self.collection = self.db.test_cases
            logger.info("Successfully connected to MongoDB")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise Exception("Could not connect to MongoDB. Please check your connection settings.")

    def save_test_case(self, test_data, item_id=None):
        """Save test case data and generate unique URL"""
        try:
            unique_id = str(uuid.uuid4())
            document = {
                "_id": unique_id,
                "test_data": test_data,
                "created_at": datetime.utcnow(),
                "url_key": unique_id,
                "item_id": item_id,
                "status": {}  # Initialize empty status dictionary for test cases
            }
            self.collection.insert_one(document)
            logger.info(f"Successfully saved test case with ID: {unique_id}")
            return unique_id
        except Exception as e:
            logger.error(f"Error saving test case: {str(e)}")
            raise Exception("Failed to save test case to database")

    def update_test_case_status(self, url_key, test_case_id, status):
        try:
            # First verify the document exists
            doc = self.collection.find_one({"url_key": url_key})
            if not doc:
                logger.error(f"No document found with url_key: {url_key}")
                return False

            # Log the request details
            logger.info(f"Updating status for test case with identifier '{test_case_id}' in document {url_key}")
            
            # Always update the central status dictionary first for reliable syncing
            # This ensures all views (main and shared) use the same status values
            title_found = False
            
            # Check if we already know this is a title (most common case)
            if test_case_id and '.' not in test_case_id and '/' not in test_case_id:
                # Update the status dictionary directly using the test_case_id as title
                self.collection.update_one(
                    {"url_key": url_key},
                    {"$set": {f"status.{test_case_id}": status}}
                )
                title_found = True
                logger.info(f"Updated central status dictionary for title: {test_case_id}")
            
            # Check if this is a shared view update
            is_shared_view = False
            if 'test_data' in doc and isinstance(doc['test_data'], list):
                is_shared_view = True
                logger.info(f"Shared view update detected for {url_key}")
            
            if is_shared_view:
                # For shared views, test_data is a list of test case objects
                test_cases = doc['test_data']
                
                # Update status in the array
                found = False
                for idx, tc in enumerate(test_cases):
                    title = tc.get('Title', '')
                    
                    # Match by title (which is our primary identifier in shared views)
                    if title == test_case_id:
                        logger.info(f"Found shared view match by title: {title}")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.{idx}.Status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                        
                        found = True
                        break
                
                if not found:
                    logger.warning(f"No test case found with title '{test_case_id}' in shared view document {url_key}")
                    return False
                
                return True
                
            elif 'test_data' in doc and 'test_cases' in doc['test_data']:
                test_cases = doc['test_data']['test_cases']
                
                # Extract just the UI identifier part (e.g., TC_UI_01 from TC_UI_01_Email_Field_Presence)
                ui_identifier = None
                if '_' in test_case_id:
                    parts = test_case_id.split('_')
                    if len(parts) >= 3:
                        ui_identifier = f"{parts[0]}_{parts[1]}_{parts[2]}"
                        logger.info(f"Extracted UI identifier: {ui_identifier}")
                
                # Approach 1: Try to find the test case by matching part of the title
                for idx, tc in enumerate(test_cases):
                    title = tc.get('Title', tc.get('title', ''))
                    content = tc.get('Content', tc.get('content', ''))
                    
                    # Check if the title or content contains the test case ID
                    if title and test_case_id in title:
                        logger.info(f"Found match in title: {title}")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                        
                        if result.modified_count > 0:
                            logger.info(f"Successfully updated status by title match for {test_case_id}")
                            return True
                    
                    # Also try matching with just the UI identifier part
                    if ui_identifier and title and ui_identifier in title:
                        logger.info(f"Found match for UI identifier {ui_identifier} in title: {title}")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                        
                        if result.modified_count > 0:
                            logger.info(f"Successfully updated status by UI identifier match for {ui_identifier}")
                            return True
                    
                    # Check content field as well
                    if content and test_case_id in content:
                        logger.info(f"Found match in content")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if title and not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                        
                        if result.modified_count > 0:
                            logger.info(f"Successfully updated status by content match for {test_case_id}")
                            return True
                
                # Approach 2: Fall back to direct ID matching (for backwards compatibility)
                for idx, tc in enumerate(test_cases):
                    if tc.get('test_case_id') == test_case_id or tc.get('Test Case ID') == test_case_id:
                        logger.info(f"Found direct ID match at index {idx}")
                        title = tc.get('Title', tc.get('title', ''))
                        
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if title and not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{title}": status}}
                            )
                            
                        return result.modified_count > 0
                
                # If we got here, no match was found
                logger.warning(f"No test case found matching '{test_case_id}' in document {url_key}")
                return False
            else:
                logger.warning(f"Document {url_key} has no test cases")
                return False

        except Exception as e:
            logger.error(f"Error updating test case status: {str(e)}")
            return False

    def get_test_case(self, url_key):
        """Retrieve test case data by URL key"""
        try:
            result = self.collection.find_one({"url_key": url_key})
            if not result:
                logger.warning(f"No test case found for URL key: {url_key}")
            return result
        except Exception as e:
            logger.error(f"Error retrieving test case: {str(e)}")
            raise Exception("Failed to retrieve test case from database")
            
    def get_test_case_status_values(self, url_key, force_refresh=False):
        """Retrieve all status values for test cases in a document
        
        Args:
            url_key: The unique URL key for the document
            force_refresh: If True, forces a direct database query to get fresh data
        """
        try:
            # Debug: Print direct DB query
            # logger.info(f"DIRECT DB QUERY FOR STATUS VALUES: url_key={url_key}, force_refresh={force_refresh}")
            
            # Always get a fresh copy from the database when force_refresh is True
            result = self.collection.find_one({"url_key": url_key})
            if not result:
                logger.warning(f"No test case found for URL key: {url_key}")
                return None
                
            # Debug: Log all data in the document for diagnosis
            if 'status' in result:
                logger.info(f"STATUS DICT in MongoDB: {result['status']}")
            else:
                logger.info("NO STATUS DICT in MongoDB document")
                
            # If test_data is a list (shared view), inspect it
            if 'test_data' in result and isinstance(result['test_data'], list):
                for i, tc in enumerate(result['test_data']):
                    title = tc.get('Title', '')
                    status = tc.get('Status', '')
                    if title:
                        logger.info(f"SHARED VIEW TC[{i}]: Title='{title}', Status='{status}'")
            
            # If test_data has test_cases array (main format), inspect it
            elif 'test_data' in result and 'test_cases' in result['test_data']:
                for i, tc in enumerate(result['test_data']['test_cases']):
                    title = tc.get('Title', tc.get('title', ''))
                    status = tc.get('Status', tc.get('status', ''))
                    if title:
                        logger.info(f"MAIN VIEW TC[{i}]: Title='{title}', Status='{status}'")
                
            # First try to get status values from the status dictionary
            if 'status' in result and result['status'] and not force_refresh:
                logger.info(f"Found {len(result['status'])} status values in status dictionary")
                return result['status']
                
            # If force_refresh or no status dictionary, build one from test cases
            status_values = {}
            
            # Check if test_data is a list (shared view format)
            if 'test_data' in result and isinstance(result['test_data'], list):
                logger.info("Building status values from shared view format")
                for tc in result['test_data']:
                    if 'Title' in tc:
                        # Include all statuses, even empty ones for completeness
                        title = tc.get('Title', '')
                        status = tc.get('Status', '')
                        if title:
                            status_values[title] = status
                            # logger.debug(f"Found status '{status}' for '{title}' in shared view")
                        
            # Check if test_data has test_cases array (main format)
            elif 'test_data' in result and 'test_cases' in result['test_data']:
                logger.info("Building status values from main view format")
                for tc in result['test_data']['test_cases']:
                    title = tc.get('Title', tc.get('title', ''))
                    status = tc.get('Status', tc.get('status', ''))
                    if title:
                        status_values[title] = status
                        # logger.debug(f"Found status '{status}' for '{title}' in main view")
                        
            # Update the status dictionary in the document for future use
            if status_values:
                logger.info(f"UPDATING status dict in MongoDB with {len(status_values)} values: {status_values}")
                self.collection.update_one(
                    {"url_key": url_key},
                    {"$set": {"status": status_values}}
                )
                
            logger.info(f"Returning {len(status_values)} status values for {url_key}")
            return status_values
            
        except Exception as e:
            logger.error(f"Error retrieving test case status values: {str(e)}")
            return None

    def save_url_data(self, url_params):
        """Save URL parameters and generate a short key"""
        try:
            short_key = str(uuid.uuid4())[:8]  # Using first 8 characters of UUID for shorter URL
            document = {
                "_id": short_key,
                "url_params": url_params,
                "created_at": datetime.utcnow(),
                "type": "shortened_url"
            }
            self.collection.insert_one(document)
            logger.info(f"Successfully saved URL data with short key: {short_key}")
            return short_key
        except Exception as e:
            logger.error(f"Error saving URL data: {str(e)}")
            raise Exception("Failed to save URL data to database")

    def get_url_data(self, short_key):
        """Retrieve URL parameters by short key"""
        try:
            document = self.collection.find_one({"_id": short_key, "type": "shortened_url"})
            if document:
                return document["url_params"]
            return None
        except Exception as e:
            logger.error(f"Error retrieving URL data: {str(e)}")
            return None