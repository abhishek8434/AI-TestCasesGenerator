# Import error logging utilities
from utils.error_logger import capture_exception, capture_message, set_tag, set_context

import pymongo
from pymongo import MongoClient
from bson import ObjectId
import json
from datetime import datetime, timedelta
import hashlib
import string
import random
import logging
from config.settings import MONGODB_URI, MONGODB_DB
import uuid

logger = logging.getLogger(__name__)

class MongoHandler:
    def __init__(self):
        try:
            self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
            # Verify connection
            self.client.server_info()
            self.db = self.client[MONGODB_DB]
            self.collection = self.db.test_cases
            self.analytics_collection = self.db.analytics
            self.user_sessions_collection = self.db.user_sessions
            logger.info("Successfully connected to MongoDB")
        except (pymongo.errors.ConnectionFailure, pymongo.errors.ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise Exception("Could not connect to MongoDB. Please check your connection settings.")

    def save_test_case(self, test_data, item_id=None, source_type=None):
        """Save test case data and generate unique URL"""
        try:
            unique_id = str(uuid.uuid4())
            document = {
                "_id": unique_id,
                "test_data": test_data,
                "created_at": datetime.utcnow(),
                "url_key": unique_id,
                "item_id": item_id,
                "source_type": source_type,  # Preserve source type for proper identification
                "status": {}  # Initialize empty status dictionary for test cases
            }
            self.collection.insert_one(document)
            logger.info(f"Successfully saved test case with ID: {unique_id}, source_type: {source_type}")
            return unique_id
        except Exception as e:
            logger.error(f"Error saving test case: {str(e)}")
            raise Exception("Failed to save test case to database")

    def update_status_dict(self, url_key, status_values):
        """Update the status dictionary for a test case document"""
        try:
            result = self.collection.update_one(
                {"url_key": url_key},
                {"$set": {"status": status_values}}
            )
            if result.modified_count > 0:
                logger.info(f"Successfully updated status dict for {url_key}")
                return True
            else:
                logger.warning(f"No document found to update status for {url_key}")
                return False
        except Exception as e:
            logger.error(f"Error updating status dict: {str(e)}")
            return False

    def track_user_session(self, session_data):
        """Track user session and page visits"""
        try:
            session_doc = {
                "session_id": session_data.get("session_id"),
                "user_agent": session_data.get("user_agent"),
                "ip_address": session_data.get("ip_address"),
                "referrer": session_data.get("referrer"),
                "page_visited": session_data.get("page_visited"),
                "timestamp": datetime.utcnow(),
                "country": session_data.get("country"),
                "city": session_data.get("city")
            }
            self.user_sessions_collection.insert_one(session_doc)
            logger.info(f"Tracked user session: {session_data.get('session_id')}")
            return True
        except Exception as e:
            logger.error(f"Error tracking user session: {str(e)}")
            return False

    def track_event(self, event_data):
        """Track user events and interactions"""
        try:
            event_doc = {
                "event_type": event_data.get("event_type"),
                "event_data": event_data.get("event_data", {}),
                "session_id": event_data.get("session_id"),
                "user_agent": event_data.get("user_agent"),
                "ip_address": event_data.get("ip_address"),
                "timestamp": datetime.utcnow(),
                "source_type": event_data.get("source_type"),
                "test_case_types": event_data.get("test_case_types", []),
                "item_count": event_data.get("item_count", 0)
            }
            self.analytics_collection.insert_one(event_doc)
            logger.info(f"Tracked event: {event_data.get('event_type')}")
            return True
        except Exception as e:
            logger.error(f"Error tracking event: {str(e)}")
            return False

    def get_analytics_summary(self, start_date=None, end_date=None, days=30, source_type=None):
        """Get analytics summary for the specified date range or number of days with optional filters"""
        try:
            if start_date and end_date:
                # Convert string dates to datetime objects
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)  # Include end date
                date_filter = {"timestamp": {"$gte": start_datetime, "$lt": end_datetime}}
            else:
                # Fallback to days parameter
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                date_filter = {"timestamp": {"$gte": cutoff_date}}
            
            # Build base filter with date and optional filters
            base_filter = {**date_filter}
            if source_type:
                base_filter["source_type"] = source_type
            
            # Get total sessions (sessions don't have event_type or source_type, so use date filter only)
            total_sessions = self.user_sessions_collection.count_documents(date_filter)
            
            # Get total events with filters
            total_events = self.analytics_collection.count_documents(base_filter)
            
            # Get generate button clicks with filters
            generate_filter = {**base_filter, "event_type": "generate_button_click"}
            generate_clicks = self.analytics_collection.count_documents(generate_filter)
            
            # Get successful generations with filters
            success_filter = {**base_filter, "event_type": "test_case_generated"}
            successful_generations = self.analytics_collection.count_documents(success_filter)
            
            # Get source type distribution - only count successful test case generations
            source_type_pipeline = [
                {"$match": {**base_filter, "event_type": "test_case_generated"}},
                {"$addFields": {
                    "effective_source_type": {
                        "$cond": {
                            "if": {"$and": [
                                {"$ne": ["$source_type", None]},
                                {"$ne": ["$source_type", ""]}
                            ]},
                            "then": "$source_type",
                            "else": "$event_data.source_type"
                        }
                    }
                }},
                {"$match": {"effective_source_type": {"$exists": True, "$ne": None, "$ne": ""}}},
                {"$group": {"_id": "$effective_source_type", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            source_type_stats = list(self.analytics_collection.aggregate(source_type_pipeline))
            
            # Get test case type distribution - only count successful test case generations
            test_case_type_pipeline = [
                {"$match": {**base_filter, "event_type": "test_case_generated", "test_case_types": {"$exists": True, "$ne": []}}},
                {"$unwind": "$test_case_types"},
                {"$group": {"_id": "$test_case_types", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            test_case_type_stats = list(self.analytics_collection.aggregate(test_case_type_pipeline))
            
            # Get daily activity
            daily_activity_pipeline = [
                {"$match": base_filter},
                {"$group": {
                    "_id": {
                        "year": {"$year": "$timestamp"},
                        "month": {"$month": "$timestamp"},
                        "day": {"$dayOfMonth": "$timestamp"}
                    },
                    "events": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ]
            daily_activity = list(self.analytics_collection.aggregate(daily_activity_pipeline))
            
            # Get generation timing statistics
            timing_pipeline = [
                {"$match": {
                    **base_filter,
                    "event_type": "test_case_generated",
                    "event_data.generation_duration_seconds": {"$exists": True}
                }},
                {"$group": {
                    "_id": None,
                    "avg_generation_time": {"$avg": "$event_data.generation_duration_seconds"},
                    "min_generation_time": {"$min": "$event_data.generation_duration_seconds"},
                    "max_generation_time": {"$max": "$event_data.generation_duration_seconds"},
                    "total_generations": {"$sum": 1}
                }}
            ]
            timing_stats = list(self.analytics_collection.aggregate(timing_pipeline))
            
            # Get timing by source type
            timing_by_source_pipeline = [
                {"$match": {
                    **base_filter,
                    "event_type": "test_case_generated",
                    "event_data.generation_duration_seconds": {"$exists": True}
                }},
                {"$addFields": {
                    "effective_source_type": {
                        "$cond": {
                            "if": {"$and": [
                                {"$ne": ["$source_type", None]},
                                {"$ne": ["$source_type", ""]}
                            ]},
                            "then": "$source_type",
                            "else": "$event_data.source_type"
                        }
                    }
                }},
                {"$match": {"effective_source_type": {"$exists": True, "$ne": None, "$ne": ""}}},
                {"$group": {
                    "_id": "$effective_source_type",
                    "avg_generation_time": {"$avg": "$event_data.generation_duration_seconds"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"avg_generation_time": -1}}
            ]
            timing_by_source = list(self.analytics_collection.aggregate(timing_by_source_pipeline))
            
            # Get timing by item count
            timing_by_items_pipeline = [
                {"$match": {
                    **base_filter,
                    "event_type": "test_case_generated",
                    "event_data.generation_duration_seconds": {"$exists": True},
                    "item_count": {"$exists": True, "$ne": 0}
                }},
                {"$group": {
                    "_id": {
                        "item_range": {
                            "$cond": {
                                "if": {"$lte": ["$item_count", 5]},
                                "then": "1-5 items",
                                "else": {
                                    "$cond": {
                                        "if": {"$lte": ["$item_count", 10]},
                                        "then": "6-10 items",
                                        "else": {
                                            "$cond": {
                                                "if": {"$lte": ["$item_count", 20]},
                                                "then": "11-20 items",
                                                "else": "20+ items"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "avg_generation_time": {"$avg": "$event_data.generation_duration_seconds"},
                    "avg_time_per_item": {"$avg": "$event_data.average_time_per_item"},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id.item_range": 1}}
            ]
            timing_by_items = list(self.analytics_collection.aggregate(timing_by_items_pipeline))
            
            return {
                "total_sessions": total_sessions,
                "total_events": total_events,
                "generate_clicks": generate_clicks,
                "successful_generations": successful_generations,
                "success_rate": min((successful_generations / generate_clicks * 100) if generate_clicks > 0 else 0, 100),
                "source_type_distribution": source_type_stats,
                "test_case_type_distribution": test_case_type_stats,
                "daily_activity": daily_activity,
                "generation_timing": timing_stats[0] if timing_stats else None,
                "timing_by_source": timing_by_source,
                "timing_by_items": timing_by_items,
                "period_days": days
            }
        except Exception as e:
            logger.error(f"Error getting analytics summary: {str(e)}")
            return None

    def get_detailed_analytics(self, filters=None):
        """Get detailed analytics with optional filters"""
        try:
            match_criteria = {}
            if filters:
                if filters.get("start_date"):
                    match_criteria["timestamp"] = {"$gte": filters["start_date"]}
                if filters.get("end_date"):
                    if "timestamp" in match_criteria:
                        match_criteria["timestamp"]["$lte"] = filters["end_date"]
                    else:
                        match_criteria["timestamp"] = {"$lte": filters["end_date"]}
                if filters.get("event_type"):
                    match_criteria["event_type"] = filters["event_type"]
                if filters.get("source_type"):
                    match_criteria["source_type"] = filters["source_type"]
            
            # Get events with pagination
            events = list(self.analytics_collection.find(
                match_criteria,
                {"_id": 0}  # Exclude MongoDB _id
            ).sort("timestamp", -1).limit(1000))
            
            return events
        except Exception as e:
            logger.error(f"Error getting detailed analytics: {str(e)}")
            return None

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
                    
                    # If no title field, try to extract title from content
                    if not title and content:
                        # Look for "Title:" in the content
                        lines = content.split('\n')
                        for line in lines:
                            if line.strip().startswith('Title:'):
                                title = line.strip().replace('Title:', '').strip()
                                break
                        
                        # If still no title, try to extract from the first line that looks like a test case ID
                        if not title:
                            lines = content.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and (line.startswith('TC_') or line.startswith('TC_FUNC_') or line.startswith('TC_UI_')):
                                    title = line
                                    break
                    
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
                    
                    # Check if the test case ID (without the item suffix) matches the title
                    # e.g., "TC_FUNC_01_Verify_Dashboard_Display_Payable_Amount" should match
                    # "TC_FUNC_01_Verify_Dashboard_Display_Payable_Amount (KAN-4)"
                    if title and '(' in test_case_id:
                        # Extract the base title (before the parentheses)
                        base_title = test_case_id.split('(')[0].strip()
                        if title == base_title:
                            logger.info(f"Found match by base title: {base_title}")
                            result = self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"test_data.test_cases.{idx}.status": status}}
                            )
                            
                            # Also update the status in the status dictionary for syncing
                            if not title_found:
                                self.collection.update_one(
                                    {"url_key": url_key},
                                    {"$set": {f"status.{test_case_id}": status}}
                                )
                            
                            if result.modified_count > 0:
                                logger.info(f"Successfully updated status by base title match for {test_case_id}")
                                return True
                    
                    # Fallback: Check if the test case ID appears anywhere in the content
                    if content and test_case_id in content:
                        logger.info(f"Found match in content for test case ID: {test_case_id}")
                        result = self.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{idx}.status": status}}
                        )
                        
                        # Also update the status in the status dictionary for syncing
                        if not title_found:
                            self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"status.{test_case_id}": status}}
                            )
                        
                        if result.modified_count > 0:
                            logger.info(f"Successfully updated status by content match for {test_case_id}")
                            return True
                    
                    # Also try matching with just the UI identifier part (more precise matching)
                    if ui_identifier and title:
                        # Check if the title starts with the UI identifier followed by underscore or space
                        # This prevents partial matches like TC_FUNC_2 matching TC_FUNC_20
                        if (title.startswith(ui_identifier + '_') or 
                            title.startswith(ui_identifier + ' ') or
                            title == ui_identifier):
                            logger.info(f"Found match for UI identifier {ui_identifier} in title: {title}")
                            result = self.collection.update_one(
                                {"url_key": url_key},
                                {"$set": {f"test_data.test_cases.{idx}.status": status}}
                            )
                            
                            # Also update the status in the status dictionary for syncing
                            if not title_found:
                                self.collection.update_one(
                                    {"url_key": url_key},
                                    {"$set": {f"status.{test_case_id}": status}}
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
                # Try to find by _id as fallback
                result = self.collection.find_one({"_id": url_key})
                if result:
                    logger.info(f"Found document by _id: {url_key}")
                else:
                    logger.warning(f"No test case found for URL key or _id: {url_key}")
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
                # Try to find by _id as fallback
                result = self.collection.find_one({"_id": url_key})
                if result:
                    logger.info(f"Found document by _id: {url_key}")
                else:
                    logger.warning(f"No test case found for URL key or _id: {url_key}")
                    return None
                
            # Debug: Log all data in the document for diagnosis
            if 'status' in result:
                logger.info(f"STATUS DICT in MongoDB: {result['status']}")
            else:
                logger.info("NO STATUS DICT in MongoDB document")
                
            # If test_data is a list (shared view), inspect it
            if 'test_data' in result and isinstance(result['test_data'], list):
                for i, tc in enumerate(result['test_data']):
                    if isinstance(tc, dict):
                        title = tc.get('Title', '')
                        status = tc.get('Status', '')
                        if title:
                            logger.info(f"SHARED VIEW TC[{i}]: Title='{title}', Status='{status}'")
                    else:
                        logger.warning(f"SHARED VIEW TC[{i}] is not a dict: {type(tc)}")
            
            # If test_data has test_cases array (main format), inspect it
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                for i, tc in enumerate(result['test_data']['test_cases']):
                    if isinstance(tc, dict):
                        title = tc.get('Title', tc.get('title', ''))
                        status = tc.get('Status', tc.get('status', ''))
                        if title:
                            logger.info(f"MAIN VIEW TC[{i}]: Title='{title}', Status='{status}'")
                    elif isinstance(tc, str):
                        # Attempt to parse string-formatted test case(s)
                        try:
                            from utils.file_handler import parse_traditional_format
                            parsed = parse_traditional_format(tc)
                            if parsed:
                                for pidx, ptc in enumerate(parsed):
                                    ptitle = ptc.get('Title', ptc.get('title', ''))
                                    pstatus = ptc.get('Status', ptc.get('status', ''))
                                    if ptitle:
                                        logger.info(f"MAIN VIEW TC[{i}] parsed[{pidx}]: Title='{ptitle}', Status='{pstatus}'")
                            else:
                                logger.warning(f"MAIN VIEW TC[{i}] is a string but could not be parsed")
                        except Exception as e:
                            logger.error(f"Error parsing MAIN VIEW TC[{i}] string entry: {e}")
                    else:
                        logger.warning(f"MAIN VIEW TC[{i}] is not a dict: {type(tc)}")
            
            # If test_data is a string (raw format), log it
            elif 'test_data' in result and isinstance(result['test_data'], str):
                logger.warning(f"test_data is stored as string (length: {len(result['test_data'])}): {result['test_data'][:200]}...")
                # For string test_data, we can't extract individual test case status
                return {}
                
            # First try to get status values from the status dictionary
            if 'status' in result and result['status']:
                logger.info(f"Found {len(result['status'])} status values in status dictionary")
                return result['status']
                
            # If no status dictionary, build one from test cases
            status_values = {}
            
            # Check if test_data is a list (shared view format)
            if 'test_data' in result and isinstance(result['test_data'], list):
                logger.info("Building status values from shared view format")
                for tc in result['test_data']:
                    if isinstance(tc, dict) and 'Title' in tc:
                        # Include all statuses, even empty ones for completeness
                        title = tc.get('Title', '')
                        status = tc.get('Status', '')
                        if title:
                            status_values[title] = status
                            # logger.debug(f"Found status '{status}' for '{title}' in shared view")
                        
            # Check if test_data has test_cases array (main format)
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                logger.info("Building status values from main view format")
                for tc in result['test_data']['test_cases']:
                    if isinstance(tc, dict):
                        title = tc.get('Title', tc.get('title', ''))
                        status = tc.get('Status', tc.get('status', ''))
                        if title:
                            status_values[title] = status
                            # logger.debug(f"Found status '{status}' for '{title}' in main view")
                    elif isinstance(tc, str):
                        # Parse string entries into structured test cases and capture their statuses
                        from utils.file_handler import parse_traditional_format
                        try:
                            parsed_test_cases = parse_traditional_format(tc)
                            if parsed_test_cases:
                                for ptc in parsed_test_cases:
                                    if isinstance(ptc, dict):
                                        ptitle = ptc.get('Title', ptc.get('title', ''))
                                        pstatus = ptc.get('Status', ptc.get('status', ''))
                                        if ptitle:
                                            status_values[ptitle] = pstatus
                        except Exception as e:
                            logger.error(f"Error parsing string test case entry in main view: {e}")
                            
            # Check if test_data has test_data array (nested structure)
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_data' in result['test_data']:
                logger.info("Building status values from nested test_data format")
                if isinstance(result['test_data']['test_data'], list):
                    for tc in result['test_data']['test_data']:
                        if isinstance(tc, dict):
                            title = tc.get('Title', tc.get('title', ''))
                            status = tc.get('Status', tc.get('status', ''))
                            if title:
                                status_values[title] = status
                                logger.debug(f"Found status '{status}' for '{title}' in nested test_data")
                            
            # Handle string test_data (fallback)
            elif 'test_data' in result and isinstance(result['test_data'], str):
                logger.info("test_data is stored as string - no individual status values available")
                # Return empty status values for string data
                return {}
                
            # Handle test_data with test_cases string
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                if isinstance(result['test_data']['test_cases'], str):
                    logger.info("Building status values from test_cases string")
                    from utils.file_handler import parse_traditional_format
                    try:
                        parsed_test_cases = parse_traditional_format(result['test_data']['test_cases'])
                        if parsed_test_cases:
                            for tc in parsed_test_cases:
                                if isinstance(tc, dict):
                                    title = tc.get('Title', tc.get('title', ''))
                                    status = tc.get('Status', tc.get('status', ''))
                                    if title:
                                        status_values[title] = status
                                        logger.debug(f"Found status '{status}' for '{title}' in parsed test_cases")
                    except Exception as e:
                        logger.error(f"Error parsing test_cases string: {e}")
                        
            # Handle test_data with test_cases list
            elif 'test_data' in result and isinstance(result['test_data'], dict) and 'test_cases' in result['test_data']:
                if isinstance(result['test_data']['test_cases'], list):
                    logger.info("Building status values from test_cases list")
                    from utils.file_handler import parse_traditional_format
                    try:
                        for test_case_obj in result['test_data']['test_cases']:
                            if isinstance(test_case_obj, dict) and 'content' in test_case_obj:
                                content = test_case_obj['content']
                                if content and isinstance(content, str):
                                    parsed_test_cases = parse_traditional_format(content)
                                    if parsed_test_cases:
                                        for tc in parsed_test_cases:
                                            if isinstance(tc, dict):
                                                title = tc.get('Title', tc.get('title', ''))
                                                status = tc.get('Status', tc.get('status', ''))
                                                if title:
                                                    status_values[title] = status
                                                    logger.debug(f"Found status '{status}' for '{title}' from list item")
                    except Exception as e:
                        logger.error(f"Error parsing test_cases list: {e}")
                        
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
        """
        Retrieve URL parameters by short key
        """
        try:
            # Search by _id instead of short_key since all documents have short_key: None
            document = self.collection.find_one({"_id": short_key})
            if document:
                # Check for test_data field first (new format), then url_params (old format)
                if 'test_data' in document:
                    return document.get('test_data')
                elif 'url_params' in document:
                    return document.get('url_params')
                else:
                    # If neither exists, return the document itself
                    return document
            return None
        except Exception as e:
            logger.error(f"Error retrieving URL data: {e}")
            return None