# Initialize error logging before any other imports
from utils.error_logger import init_error_logger, capture_exception, capture_message, set_tag, set_context

# Initialize error logging for the main application
init_error_logger("ai-test-case-generator-main")

from flask import Flask, request, jsonify, send_file, render_template, after_this_request
from flask_cors import CORS
from jira.jira_client import fetch_issue
from azure_integration.azure_client import AzureClient
from ai.generator import generate_test_case
from ai.image_generator import generate_test_case_from_image
from utils.file_handler import save_test_script, save_excel_report, extract_test_type_sections, parse_traditional_format
from utils.mongo_handler import MongoHandler
import os
import json
from datetime import datetime, timedelta
import math
import re
import logging
import requests
from urllib.parse import urlparse
from threading import Lock
from functools import wraps

app = Flask(__name__)
CORS(app)

# JWT configuration
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=30)

# Add this logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    # Add cache-busting timestamp
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return render_template('index.html', timestamp=timestamp)

@app.route('/analytics')
def analytics_dashboard():
    """Analytics dashboard page"""
    return render_template('analytics.html')

@app.route('/documentation')
def documentation():
    """Documentation page"""
    return render_template('documentation.html')

@app.route('/comparison')
def comparison():
    """Competitive analysis comparison page"""
    return render_template('comparison.html')

@app.route('/signin')
def signin():
    """Sign in page"""
    return render_template('signin.html')

@app.route('/signup')
def signup():
    """Sign up page"""
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    """User dashboard page"""
    return render_template('dashboard.html')

@app.route('/reset-password')
def reset_password():
    """Reset password page"""
    return render_template('reset-password.html')

@app.route('/reset-password-confirm')
def reset_password_confirm():
    """Password reset confirmation page"""
    token = request.args.get('token')
    if not token:
        return render_template('reset-password.html', error='Invalid or missing reset token')
    
    # Verify the token
    mongo_handler = MongoHandler()
    token_result = mongo_handler.verify_password_reset_token(token)
    
    if not token_result['success']:
        return render_template('reset-password.html', error='Invalid or expired reset token')
    
    return render_template('reset-password-confirm.html', token=token, email=token_result['email'])

@app.route('/admin-dashboard')
def admin_dashboard():
    """Admin dashboard page"""
    return render_template('admin-dashboard.html')

@app.route('/test')
def test():
    logger.info("=== TEST ENDPOINT CALLED ===")
    return jsonify({'message': 'Server is working!', 'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')})

@app.route('/test-email')
def test_email():
    """Test email notification system"""
    try:
        from utils.email_notifier import test_email_configuration
        
        success = test_email_configuration()
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Test email sent successfully!',
                'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to send test email. Check email configuration.',
                'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
            }), 500
            
    except Exception as e:
        logger.error(f"Error testing email configuration: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error testing email: {str(e)}',
            'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
        }), 500

@app.route('/test-error-notification')
def test_error_notification():
    """Test critical error notification system"""
    try:
        from utils.email_notifier import send_critical_error_notification
        
        # Simulate a critical error
        test_error = Exception("This is a test critical error for email notification system")
        
        success = send_critical_error_notification(
            error_type="TEST_ERROR",
            error_message="Test critical error notification",
            context={
                "test": True,
                "endpoint": "/test-error-notification",
                "timestamp": datetime.now().isoformat()
            },
            exception=test_error
        )
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Test error notification sent successfully!',
                'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to send test error notification. Check email configuration.',
                'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
            }), 500
            
    except Exception as e:
        logger.error(f"Error testing error notification: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error testing notification: {str(e)}',
            'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
        }), 500

@app.route('/results')
def results():
    # Check for both key and token parameters
    short_key = request.args.get('key') or request.args.get('token')
    logger.info(f"Received request with key/token: {short_key}")
    
    if short_key:
        mongo_handler = MongoHandler()
        url_params = mongo_handler.get_url_data(short_key)
        logger.info(f"Retrieved URL params from MongoDB: {url_params}")
        if url_params:
            # Get the full document to access status timestamps
            document = mongo_handler.collection.find_one({"_id": short_key})
            status_timestamps = document.get('status_timestamps', {}) if document else {}
            return render_template('results.html', url_params=url_params, status_timestamps=status_timestamps)
        else:
            logger.warning(f"No data found for key/token: {short_key}")
            # Return error page instead of falling back to long URL
            return render_template('error.html', error_message="The requested test case data could not be found. The link may have expired or been invalid."), 404
    
    # If no short key/token provided, return error
    return render_template('error.html', error_message="Invalid URL. Please use a valid test case link."), 400


# Add at the top of the file with other imports
from threading import Lock

# Add after app initialization
generation_status = {
    'is_generating': False,
    'completed_types': set(),
    'total_types': set(),
    'phase': '',
    'current_test_type': '',
    'log': [],
    'progress_percentage': 0,
    'lock': Lock()
}

# Modify the generate endpoint
@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        logger.info("=== GENERATE ENDPOINT CALLED ===")
        # Handle different request content types properly
        data = None
        if request.is_json:
            try:
                data = request.json
                logger.info("Request processed as JSON")
            except Exception as e:
                logger.error(f"Failed to parse JSON request: {e}")
                return jsonify({'error': 'Invalid JSON request'}), 400
        else:
            data = request.form
            logger.info("Request processed as FormData")
            
        logger.info(f"Request data type: {type(data)}")
        logger.info(f"Request data keys: {list(data.keys()) if data else 'None'}")
        if request.files:
            logger.info(f"Request files: {list(request.files.keys())}")
            for key, file in request.files.items():
                logger.info(f"File {key}: {file.filename}, size: {len(file.read()) if hasattr(file, 'read') else 'unknown'}")
                file.seek(0)  # Reset file pointer
        
        # Get test case types with proper fallback
        selected_types = []
        if request.is_json:
            selected_types = data.get('testCaseTypes[]', data.get('testCaseTypes', []))
        else:
            # For FormData, handle both getlist and get methods
            if hasattr(data, 'getlist'):
                selected_types = data.getlist('testCaseTypes[]')
            else:
                # Fallback for regular dict-like objects
                selected_types = data.get('testCaseTypes[]', [])
                if isinstance(selected_types, str):
                    selected_types = [selected_types]
            
        # Ensure selected_types is always a list
        if isinstance(selected_types, str):
            selected_types = [selected_types]
            
        # Validate test case types
        if not selected_types:
            return jsonify({'error': 'Please select at least one test case type'}), 400

        # Check if user is authenticated
        current_user = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(' ')[1]
                mongo_handler = MongoHandler()
                user_info = mongo_handler.verify_jwt_token(token)
                if user_info and user_info.get('success'):
                    current_user = user_info['user']
            except Exception as e:
                logger.warning(f"Failed to verify auth token: {str(e)}")
                # Continue without authentication

        # Get source type and item IDs for tracking
        if not data:
            return jsonify({'error': 'No request data received'}), 400
            
        source_type = data.get('sourceType')
        if not source_type:
            return jsonify({'error': 'Source type is required'}), 400
        
        # Track generate button click with start time
        generation_start_time = datetime.utcnow()
        mongo_handler = None
        try:
            mongo_handler = MongoHandler()
            event_data = {
                "event_type": "generate_button_click",
                "event_data": {
                    "source_type": source_type,
                    "test_case_types": selected_types,
                    "item_count": len(data.get('itemId', [])) if data and data.get('itemId') else 0,
                    "generation_start_time": generation_start_time.isoformat()
                },
                "session_id": data.get('session_id'),
                "user_agent": request.headers.get('User-Agent'),
                "ip_address": request.remote_addr,
                "source_type": source_type,
                "test_case_types": selected_types,
                "item_count": len(data.get('itemId', [])) if data and data.get('itemId') else 0
            }
            
            # Add user information if available
            if current_user:
                event_data['user_id'] = current_user.get('id')
                event_data['user_role'] = current_user.get('role')
            mongo_handler.track_event(event_data)
        except Exception as e:
            logger.error(f"Failed to track generate button click: {str(e)}")
            # Continue with generation even if analytics fails
        
        # Update generation status
        with generation_status['lock']:
            generation_status['is_generating'] = True
            generation_status['completed_types'] = set()
            generation_status['phase'] = 'starting'
            generation_status['current_test_type'] = ''
            generation_status['log'] = []
            generation_status['progress_percentage'] = 0
            # Critical: clear any stale final_url_key from previous runs
            generation_status['final_url_key'] = ''
            # For multiple item IDs, track combinations of item_id and test_type
            if source_type == 'image':
                generation_status['total_types'] = set(f"image_{test_type}" for test_type in selected_types)
            elif source_type == 'url':
                # Track URL test types directly
                generation_status['total_types'] = set(f"url_{test_type}" for test_type in selected_types)
            else:
                # For Jira/Azure, create combinations of item_id and test_type
                item_ids = data.get('itemId', [])
                if isinstance(item_ids, str):
                    item_ids = [item_ids]
                generation_status['total_types'] = set(f"{item_id}_{test_type}" for item_id in item_ids for test_type in selected_types)

        # # Log the request for debugging
        # logger.info(f"Generation request - Types: {selected_types}")
        
        if source_type == 'url':
            logger.info("=== URL SOURCE TYPE DETECTED ===")
            logger.info(f"Received data: {data}")
            print(f"[DEBUG] URL request received: {data}")  # Immediate console output
            
            # Initialize item_ids for URL source type (empty list since URLs don't have item IDs)
            item_ids = []
            
            # Handle URL source type
            url_config = data.get('url_config', {})
            url = url_config.get('url', '').strip()
            logger.info(f"URL from config: {url}")
            print(f"[DEBUG] URL extracted: {url}")  # Immediate console output
            
            if not url:
                print("[DEBUG] No URL found in request")  # Immediate console output
                return jsonify({'error': 'URL is required'}), 400
                
            try:
                print(f"[DEBUG] Starting URL processing for: {url}")  # Immediate console output
                # Validate URL format
                parsed_url = urlparse(url)
                if not all([parsed_url.scheme, parsed_url.netloc]):
                    print("[DEBUG] Invalid URL format")  # Immediate console output
                    return jsonify({'error': 'Invalid URL format'}), 400
                    
                # Try to access the URL with better error handling
                print(f"[DEBUG] Testing URL accessibility: {url}")  # Immediate console output
                try:
                    response = requests.get(url, timeout=10, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    })
                    print(f"[DEBUG] URL response status: {response.status_code}")  # Immediate console output
                    # Accept any 2xx status code, not just 200
                    if response.status_code < 200 or response.status_code >= 300:
                        print(f"[DEBUG] URL not accessible, status: {response.status_code}")  # Immediate console output
                        # Don't return error, just log it and continue
                        logger.warning(f"URL returned status {response.status_code}, but continuing anyway")
                except Exception as url_error:
                    print(f"[DEBUG] URL access error: {url_error}")  # Immediate console output
                    # Don't return error, just log it and continue
                    logger.warning(f"Could not access URL: {url_error}, but continuing anyway")
                    
                # Import generator lazily
                print("[DEBUG] Importing URL generator...")  # Immediate console output
                try:
                    from ai.url_generator import generate_url_test_cases
                    logger.info("Successfully imported URL generator")
                    print("[DEBUG] URL generator imported successfully")  # Immediate console output
                except Exception as import_error:
                    logger.error(f"Error importing URL generator: {import_error}")
                    print(f"[DEBUG] Import error: {import_error}")  # Immediate console output
                    return jsonify({'error': f'Error importing URL generator: {import_error}'}), 500

                # Resolve selected test case types
                test_case_types = selected_types if selected_types else ['dashboard_functional']
                logger.info(f"Selected types from request: {selected_types}")
                logger.info(f"Test case types to generate: {test_case_types}")
                print(f"[DEBUG] Test case types: {test_case_types}")  # Immediate console output

                # Generate a unique key for the results
                import uuid
                url_key = str(uuid.uuid4())
                print(f"[DEBUG] Generated URL key: {url_key}")  # Immediate console output

                # Run URL generation asynchronously so the client can poll progress
                import threading
                print("[DEBUG] Starting async URL generation thread...")  # Immediate console output
                
                def _run_url_generation_async(target_url, types, result_key, user_id=None):
                    try:
                        print(f"[DEBUG ASYNC] Starting for URL: {target_url}, types: {types}")  # Immediate console output
                        logger.info("[URL ASYNC] Starting direct URL content generation")
                        
                        # Record generation start time for tracking
                        generation_start_time = datetime.utcnow()
                        
                        with generation_status['lock']:
                            generation_status['phase'] = 'fetching_content'
                            generation_status['log'].append(f"Fetching content from {target_url}")
                        
                        # 1) Fetch website content directly
                        print("[DEBUG ASYNC] Importing URL generator...")  # Immediate console output
                        from ai.url_generator import generate_url_test_cases
                        print(f"[DEBUG ASYNC] Fetching content from: {target_url}")  # Immediate console output
                        
                        # 2) Generate test cases directly from URL content
                        with generation_status['lock']:
                            generation_status['phase'] = 'ai_generation'
                            generation_status['log'].append(f"Generating test cases from URL content for types: {types}")
                        
                        test_cases_local = generate_url_test_cases(target_url, types)
                        logger.info(f"[URL ASYNC] Direct URL generation finished, has content: {bool(test_cases_local)}")

                        if not test_cases_local:
                            raise RuntimeError('Failed to generate test cases from URL content')

                        # 3) Save results
                        test_cases_filename_local = f"url_test_cases_{result_key}.txt"
                        # Create uploads directory if it doesn't exist
                        uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
                        os.makedirs(uploads_dir, exist_ok=True)
                        test_cases_filepath_local = os.path.join(uploads_dir, test_cases_filename_local)
                        with open(test_cases_filepath_local, 'w', encoding='utf-8') as f:
                            f.write(f"URL: {target_url}\n")
                            f.write(f"Generated Test Cases (via direct URL content analysis):\n\n")
                            f.write(test_cases_local)
                        
                        # Generate Excel file like Jira/Azure
                        file_base_name = f"url_test_cases_{result_key}"
                        excel_file = save_excel_report(test_cases_local, file_base_name)
                        logger.info(f"[URL ASYNC] Generated Excel file: {excel_file}")

                        # Create task record
                        task_local = {
                            'url_key': result_key,
                            'source_type': 'url',
                            'url': target_url,
                            'test_case_types': types,
                            'content_file': test_cases_filepath_local,
                            'status': 'completed',
                            'created_at': datetime.now()
                        }
                        try:
                            mongo_handler_local = MongoHandler()
                            # Parse the test cases into structured format like Jira/Azure
                            logger.info(f"[URL ASYNC] About to parse test cases. Type: {type(test_cases_local)}, Length: {len(test_cases_local) if test_cases_local else 0}")
                            logger.info(f"[URL ASYNC] First 500 chars of test cases: {test_cases_local[:500] if test_cases_local else 'None'}")
                            
                            structured_test_data = parse_traditional_format(test_cases_local)
                            logger.info(f"[URL ASYNC] Parsed test data. Type: {type(structured_test_data)}, Length: {len(structured_test_data) if structured_test_data else 0}")
                            
                            # Debug: Check if steps are being parsed
                            if structured_test_data:
                                for i, test_case in enumerate(structured_test_data):
                                    steps = test_case.get('Steps', [])
                                    logger.info(f"[URL ASYNC] Test case {i+1} '{test_case.get('Title', 'Unknown')}' has {len(steps)} steps")
                                    if steps:
                                        logger.info(f"[URL ASYNC] First step: {steps[0]}")
                                    else:
                                        logger.warning(f"[URL ASYNC] No steps found for test case {i+1}")
                            
                            # Ensure structured_test_data is a list, not a string
                            if isinstance(structured_test_data, str):
                                logger.error(f"[URL ASYNC] parse_traditional_format returned a string instead of a list: {structured_test_data[:200]}")
                                # Create a fallback structure
                                structured_test_data = [{
                                    'Section': 'General',
                                    'Title': 'Generated Test Case',
                                    'Scenario': 'Test scenario from URL content',
                                    'Steps': ['Step 1: Navigate to the URL', 'Step 2: Verify content'],
                                    'Expected Result': 'Content should be accessible and functional'
                                }]
                            elif not isinstance(structured_test_data, list):
                                logger.error(f"[URL ASYNC] parse_traditional_format returned unexpected type: {type(structured_test_data)}")
                                structured_test_data = []
                            
                            # Use save_test_case like Image source type to get proper URL key format
                            url_key_final = mongo_handler_local.save_test_case({
                                'test_cases': test_cases_local,
                                'source_type': 'url',
                                'url': target_url,
                                'test_case_types': types,
                                'test_data': structured_test_data  # Use structured data for frontend display
                            }, result_key, 'url', user_id)
                            logger.info(f"[URL ASYNC] Saved test case with URL key: {url_key_final}")
                        except Exception as me:
                            logger.error(f"[URL ASYNC] Failed to save test case: {me}")
                            logger.error(f"[URL ASYNC] Exception type: {type(me)}")
                            import traceback
                            logger.error(f"[URL ASYNC] Full traceback: {traceback.format_exc()}")
                            # Set a fallback URL key for tracking
                            url_key_final = result_key
                        
                        # Track successful URL test case generation (moved outside try-catch)
                        try:
                            generation_end_time = datetime.utcnow()
                            generation_duration = (generation_end_time - generation_start_time).total_seconds()
                            
                            event_data = {
                                "event_type": "test_case_generated",
                                "event_data": {
                                    "url_key": url_key_final,
                                    "source_type": "url",
                                    "test_case_types": types,
                                    "item_count": 1,  # URL generation is always 1 item
                                    "files_generated": 1,  # URL generates 1 file
                                    "generation_duration_seconds": generation_duration,
                                    "generation_start_time": generation_start_time.isoformat(),
                                    "generation_end_time": generation_end_time.isoformat(),
                                    "average_time_per_item": generation_duration
                                },
                                "session_id": None,  # URL generation doesn't have session_id in async context
                                "user_agent": "URL Generator",  # Default for async generation
                                "ip_address": "127.0.0.1",  # Default for async generation
                                "source_type": "url",
                                "test_case_types": types,
                                "item_count": 1
                            }
                            
                            # Add user information if available
                            if user_id:
                                event_data['user_id'] = user_id
                            mongo_handler_local.track_event(event_data)
                            logger.info(f"[URL ASYNC] Tracked URL test case generation event")
                        except Exception as tracking_error:
                            logger.error(f"[URL ASYNC] Failed to track URL test case generation: {tracking_error}")

                        # Mark progress completed and store the final URL key
                        with generation_status['lock']:
                            generation_status['completed_types'] = set(generation_status['total_types'])
                            generation_status['is_generating'] = False
                            generation_status['progress_percentage'] = 100
                            generation_status['phase'] = 'completed'
                            generation_status['log'].append('Generation completed')
                            generation_status['final_url_key'] = url_key_final  # Store the final URL key
                            logger.info(f"[URL ASYNC] Set final_url_key in generation status: {url_key_final}")
                    except Exception as gen_err:
                        logger.error(f"[URL ASYNC] Error: {gen_err}")
                        with generation_status['lock']:
                            generation_status['is_generating'] = False
                            generation_status['phase'] = 'error'
                            generation_status['log'].append(f"Error: {gen_err}")

                # Log in status for visibility
                with generation_status['lock']:
                    generation_status['phase'] = 'queued'
                    generation_status['log'].append(f"Queued URL generation for {url} with types: {test_case_types}")

                threading.Thread(target=_run_url_generation_async, args=(url, test_case_types, url_key, current_user.get('id') if current_user else None), daemon=True).start()

                # Immediately return so frontend can start polling progress
                return jsonify({'url_key': url_key})
                
            except requests.RequestException as e:
                with generation_status['lock']:
                    generation_status['is_generating'] = False
                return jsonify({'error': f'Failed to access URL: {str(e)}'}), 400
            except Exception as e:
                logger.error(f"Error processing URL content: {str(e)}")
                with generation_status['lock']:
                    generation_status['is_generating'] = False
                return jsonify({'error': f'Error processing URL content: {str(e)}'}), 500

        elif source_type == 'image':
            logger.info("=== IMAGE SOURCE TYPE DETECTED ===")
            logger.info(f"Request files: {list(request.files.keys())}")
            logger.info(f"Request form data: {list(request.form.keys())}")
            
            # Initialize item_ids for image source type (empty list since images don't have item IDs)
            item_ids = []
            
            # Handle image upload
            if 'imageFile' not in request.files:
                logger.error("No imageFile in request.files")
                return jsonify({'error': 'No image file uploaded'}), 400
                
            image_file = request.files['imageFile']
            logger.info(f"Image file received: {image_file.filename}, size: {len(image_file.read()) if hasattr(image_file, 'read') else 'unknown'}")
            # Reset file pointer after reading
            image_file.seek(0)
            
            if image_file.filename == '':
                logger.error("Empty filename received")
                return jsonify({'error': 'No selected file'}), 400
                
            # Create unique identifier for the image
            import uuid
            unique_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            
            # Save the uploaded image in a permanent storage
            image_storage = os.path.join(os.path.dirname(__file__), 'tests', 'images')
            os.makedirs(image_storage, exist_ok=True)
            
            # Get file extension
            file_ext = os.path.splitext(image_file.filename)[1]
            stored_filename = f"image_{unique_id}{file_ext}"
            image_path = os.path.join(image_storage, stored_filename)
            
            # Save the image
            image_file.save(image_path)
            
            try:
                # Import the image generator
                from ai.image_generator import generate_test_case_from_image
                
                # The API key verification is now handled inside the image generator function
                # No need to check here as the function will handle it properly
                
                # Use the already processed selected_types
                if not selected_types:
                    os.remove(image_path)  # Clean up if validation fails
                    # Reset the generation status
                    with generation_status['lock']:
                        generation_status['is_generating'] = False
                    return jsonify({'error': 'Please select at least one test case type'}), 400
                
                # Generate test cases from image - one type at a time
                test_cases = None
                all_types_processed = True
                error_messages = []
                
                for test_type in selected_types:
                    try:
                        # Generate one type at a time
                        logger.info(f"Generating {test_type} test cases from image")
                        type_test_case = generate_test_case_from_image(
                            image_path,
                            selected_types=[test_type]
                        )
                        
                        if type_test_case:
                            if test_cases:
                                test_cases += "\n\n" + type_test_case
                            else:
                                test_cases = type_test_case
                                
                            # Mark this type as completed
                            with generation_status['lock']:
                                # Track completion per item ID and type
                                completion_key = f"{unique_id}_{test_type}"
                                generation_status['completed_types'].add(completion_key)
                        else:
                            error_messages.append(f"Failed to generate {test_type} test cases from image")
                            logger.error(f"Failed to generate {test_type} test cases from image")
                            all_types_processed = False
                    except ValueError as e:
                        error_message = str(e)
                        error_messages.append(error_message)
                        logger.error(f"Error generating {test_type} test cases from image: {error_message}", exc_info=True)
                        all_types_processed = False
                        
                        # Check for API key errors
                        if "api key" in error_message.lower() or "authorization" in error_message.lower():
                            # Clean up the image
                            if os.path.exists(image_path):
                                os.remove(image_path)
                            # Reset generation status
                            with generation_status['lock']:
                                generation_status['is_generating'] = False
                            # Render the error page
                            return render_template('error.html', error_message=error_message), 400
                    except Exception as e:
                        error_messages.append(f"Error generating {test_type} test cases: {str(e)}")
                        logger.error(f"Error generating {test_type} test cases from image: {str(e)}", exc_info=True)
                        all_types_processed = False
                
                if not test_cases:
                    os.remove(image_path)  # Clean up if generation fails
                    # Reset the generation status
                    with generation_status['lock']:
                        generation_status['is_generating'] = False
                    
                    # Provide better error message
                    error_message = "Failed to generate test cases from image"
                    if error_messages:
                        error_message += f": {error_messages[0]}"
                        # Check for common error patterns
                        for msg in error_messages:
                            if "model_not_found" in msg or "invalid_request_error" in msg:
                                error_message = "The OpenAI model required for image processing is not available or has been deprecated. Please check your OpenAI account access."
                                break
                            elif "api key" in msg.lower() or "authorization" in msg.lower():
                                # Render the error page for API key issues
                                return render_template('error.html', error_message="OpenAI API authentication failed. Please check your API key configuration."), 400
                    
                    return jsonify({'error': error_message}), 400
                
                # Save test case files
                file_base_name = f'test_image_{unique_id}'
                txt_file = save_test_script(test_cases, file_base_name)
                excel_file = save_excel_report(test_cases, file_base_name)
                
                if txt_file and excel_file:
                    results = {
                        'txt': txt_file,
                        'excel': excel_file
                    }
                    
                    # Inside the image upload handler, before saving to MongoDB
                    formatted_test_cases = []
                    for idx, test_case in enumerate(test_cases.split('\n\n')):
                        if test_case.strip():
                            # Start test case IDs from 2 instead of 1
                            test_case_id = f"TC_KAN-1_{idx + 2}"
                            formatted_test_cases.append({
                                'test_case_id': test_case_id,
                                'content': test_case,
                                'status': ''
                            })
                        
                    # Parse the test cases into a more structured format for display
                    test_case_sections = extract_test_type_sections(test_cases)
                    
                    # If sections were found, parse each section
                    structured_test_data = []
                    if test_case_sections:
                        for section_name, section_content in test_case_sections.items():
                            parsed_cases = parse_traditional_format(section_content, default_section=section_name)
                            structured_test_data.extend(parsed_cases)
                    else:
                        # Try parsing the whole text as a single section
                        structured_test_data = parse_traditional_format(test_cases)
                    
                    # Create MongoDB handler and save test case data
                    mongo_handler = MongoHandler()
                    url_key = mongo_handler.save_test_case({
                        'test_cases': formatted_test_cases,
                        'source_type': 'image',
                        'image_id': unique_id,
                        'test_data': structured_test_data  # Add structured data for frontend display
                    }, unique_id, 'image', current_user['id'] if current_user else None)
                    
                    # Track successful image test case generation with timing
                    generation_end_time = datetime.utcnow()
                    generation_duration = (generation_end_time - generation_start_time).total_seconds()
                    
                    try:
                        if mongo_handler:
                            event_data = {
                                "event_type": "test_case_generated",
                                "event_data": {
                                    "url_key": url_key,
                                    "source_type": "image",
                                    "test_case_types": selected_types,
                                    "item_count": 1,  # Image has 1 item
                                    "files_generated": len(results),
                                    "generation_duration_seconds": generation_duration,
                                    "generation_start_time": generation_start_time.isoformat(),
                                    "generation_end_time": generation_end_time.isoformat(),
                                    "average_time_per_item": generation_duration
                                },
                                "session_id": data.get('session_id'),
                                "user_agent": request.headers.get('User-Agent'),
                                "ip_address": request.remote_addr,
                                "source_type": "image",
                                "test_case_types": selected_types,
                                "item_count": 1
                            }
                            
                            # Add user information if available
                            if current_user:
                                event_data['user_id'] = current_user.get('id')
                                event_data['user_role'] = current_user.get('role')
                            mongo_handler.track_event(event_data)
                    except Exception as e:
                        logger.error(f"Failed to track image test case generation: {str(e)}")
                    
                    # Mark all test types as completed
                    with generation_status['lock']:
                        generation_status['completed_types'] = generation_status['total_types'].copy()
                        generation_status['is_generating'] = False
                    
                    return jsonify({
                        'success': True,
                        'url_key': url_key,
                        'files': results
                    })
                else:
                    os.remove(image_path)  # Clean up if saving fails
                    # Reset the generation status
                    with generation_status['lock']:
                        generation_status['is_generating'] = False
                    return jsonify({'error': 'Failed to save test case files'}), 400
                    
            except Exception as e:
                if os.path.exists(image_path):
                    os.remove(image_path)
                # Reset the generation status
                with generation_status['lock']:
                    generation_status['is_generating'] = False
                
                # Log the full error for debugging
                logger.error(f"Image processing error: {str(e)}", exc_info=True)
                
                # Return a more specific error message
                error_message = f'Image processing error: {str(e)}. Please ensure the image is clear and in a supported format (JPG, PNG, JPEG).'
                
                # Check for common error patterns and provide better messages
                if "api key" in str(e).lower() or "authorization" in str(e).lower():
                    error_message = "OpenAI API authentication failed. Please check your API key configuration."
                elif "model_not_found" in str(e).lower() or "invalid_request_error" in str(e).lower():
                    error_message = "The OpenAI model required for image processing is not available. Please check your OpenAI account access."
                elif "quota" in str(e).lower() or "rate limit" in str(e).lower():
                    error_message = "OpenAI API quota exceeded or rate limited. Please try again later."
                
                return jsonify({'error': error_message}), 500
                
        else:
            # Existing Jira/Azure logic
            data = request.json
            source_type = data.get('sourceType', 'jira')
            item_ids = data.get('itemId', [])
            
            # Add debugging
            logger.info(f"Processing request for source_type: {source_type}")
            logger.info(f"Raw item_ids from request: {item_ids}")
            
            # Fix test case types handling for JSON requests
            selected_types = data.get('testCaseTypes[]', data.get('testCaseTypes', []))
            if isinstance(selected_types, str):
                selected_types = [selected_types]
            
            if not selected_types:
                return jsonify({'error': 'Please select at least one test case type'}), 400
            
            if isinstance(item_ids, str):
                item_ids = [item_ids]
            
            logger.info(f"Processed item_ids: {item_ids} (count: {len(item_ids)})")
            logger.info(f"Selected test types: {selected_types}")
            
            # Log batch processing info
            if len(item_ids) > 10:
                logger.info(f"Large batch detected: {len(item_ids)} items. Processing in batches...")
            elif len(item_ids) > 5:
                logger.info(f"Medium batch detected: {len(item_ids)} items.")
            else:
                logger.info(f"Small batch: {len(item_ids)} items.")
            
            results = {}
            all_types_processed = True
            
            for item_id in item_ids:
                logger.info(f"Processing item_id: {item_id}")
                test_cases = None
                
                if source_type == 'jira':
                    # Get Jira configuration from request data
                    jira_config = data.get('jira_config')
                    logger.info(f"Fetching Jira issue for item_id: {item_id}")
                    
                    try:
                        issue = fetch_issue(item_id, jira_config)
                        if not issue:
                            logger.warning(f"Failed to fetch Jira issue for {item_id}")
                            return jsonify({'error': f'Failed to fetch Jira issue {item_id}. Please check your credentials and ensure the issue exists.'}), 400
                    except Exception as e:
                        logger.error(f"Jira connection error for {item_id}: {str(e)}")
                        return jsonify({'error': f'Jira connection error: {str(e)}. Please check your Jira configuration.'}), 500
                    
                    logger.info(f"Successfully fetched Jira issue {item_id}: {issue.get('key', 'Unknown')}")
                    
                    for test_type in selected_types:
                        try:
                            logger.info(f"Generating {test_type} test cases for {item_id}")
                            # Generate one type at a time
                            type_test_case = generate_test_case(
                                description=issue['fields']['description'],
                                summary=issue['fields']['summary'],
                                selected_types=[test_type]
                            )
                            
                            if type_test_case:
                                if test_cases:
                                    test_cases += "\n\n" + type_test_case
                                else:
                                    test_cases = type_test_case
                                    
                                # Mark this type as completed
                                with generation_status['lock']:
                                    # Track completion per item ID and type
                                    completion_key = f"{item_id}_{test_type}"
                                    generation_status['completed_types'].add(completion_key)
                                    # Log progress for debugging
                                    progress = (len(generation_status['completed_types']) / len(generation_status['total_types'])) * 100
                                    logger.info(f"Progress update: {len(generation_status['completed_types'])}/{len(generation_status['total_types'])} = {progress:.1f}%")
                                logger.info(f"Successfully generated {test_type} test cases for {item_id}")
                            else:
                                logger.warning(f"No test cases generated for {test_type} for {item_id}")
                                all_types_processed = False
                                
                        except Exception as e:
                            logger.error(f"Error generating {test_type} test cases for {item_id}: {str(e)}")
                            all_types_processed = False
                            
                elif source_type == 'azure':
                    logger.info("=== AZURE SECTION ENTERED ===")
                    # Get Azure configuration from request data
                    azure_config = data.get('azure_config')
                    logger.info(f"Azure config received: {azure_config}")
                    logger.info(f"Azure config type: {type(azure_config)}")
                    
                    if azure_config:
                        logger.info(f"Azure config keys: {list(azure_config.keys()) if isinstance(azure_config, dict) else 'Not a dict'}")
                        logger.info(f"Azure config values: {list(azure_config.values()) if isinstance(azure_config, dict) else 'Not a dict'}")
                    
                    # Only use frontend config if it exists and all required values are present
                    if azure_config and all(azure_config.values()):
                        logger.info(f"Using frontend Azure config: {azure_config}")
                        azure_client = AzureClient(azure_config=azure_config)
                    else:
                        logger.info("Using environment variables for Azure config")
                        logger.info(f"Reason: azure_config exists: {bool(azure_config)}, all values present: {all(azure_config.values()) if azure_config else False}")
                        azure_client = AzureClient()  # Fall back to environment variables
                    
                    # Capture Azure-specific errors
                    try:
                        work_items = azure_client.fetch_azure_work_items([item_id])
                        
                        if not work_items or len(work_items) == 0:
                            # Check if it's an authentication issue
                            if hasattr(azure_client, 'last_error'):
                                error_msg = azure_client.last_error
                                if '401' in error_msg:
                                    return jsonify({'error': 'Azure DevOps authentication failed. Please check your Personal Access Token (PAT) and ensure it has "Work Items (Read)" permissions.'}), 401
                                elif '404' in error_msg:
                                    return jsonify({'error': f'Work item {item_id} not found in Azure DevOps. Please verify the work item ID exists in your project.'}), 404
                                else:
                                    return jsonify({'error': f'Azure DevOps error: {error_msg}'}), 400
                            else:
                                return jsonify({'error': f'Failed to fetch work item {item_id} from Azure DevOps. Please check your configuration and try again.'}), 400
                    except Exception as e:
                        logger.error(f"Azure client error for item {item_id}: {str(e)}")
                        return jsonify({'error': f'Azure DevOps connection error: {str(e)}'}), 500
                    
                    # Define work_item from the fetched items
                    work_item = work_items[0]
                    
                    for test_type in selected_types:
                        try:
                            # Generate one type at a time
                            type_test_case = generate_test_case(
                                description=work_item['description'],
                                summary=work_item['title'],
                                selected_types=[test_type]
                            )
                            
                            if type_test_case:
                                if test_cases:
                                    test_cases += "\n\n" + type_test_case
                                else:
                                    test_cases = type_test_case
                                    
                                # Mark this type as completed
                                with generation_status['lock']:
                                    # Track completion per item ID and type
                                    completion_key = f"{item_id}_{test_type}"
                                    generation_status['completed_types'].add(completion_key)
                                    # Log progress for debugging
                                    progress = (len(generation_status['completed_types']) / len(generation_status['total_types'])) * 100
                                    logger.info(f"Progress update: {len(generation_status['completed_types'])}/{len(generation_status['total_types'])} = {progress:.1f}%")
                                logger.info(f"Successfully generated {test_type} test cases for {item_id}")
                            else:
                                all_types_processed = False
                                
                        except Exception as e:
                            logger.error(f"Error generating {test_type} test cases: {str(e)}")
                            all_types_processed = False
                
                # Only proceed if test cases were generated
                if not test_cases:
                    logger.warning(f"No test cases generated for item_id: {item_id}, skipping file creation")
                    continue
                    
                logger.info(f"Generated test cases for {item_id}, saving files...")
                    
                # Save files
                safe_filename = ''.join(c for c in item_id if c.isalnum() or c in ('-', '_'))
                file_base_name = f'test_{safe_filename}'
                
                txt_file = save_test_script(test_cases, file_base_name)
                excel_file = save_excel_report(test_cases, file_base_name)
                
                if txt_file and excel_file:
                    results[item_id] = {
                        'txt': txt_file,
                        'excel': excel_file,
                        'test_cases': test_cases  # Store the test cases content
                    }
                    logger.info(f"Successfully saved files for {item_id}: txt={txt_file}, excel={excel_file}")
                else:
                    logger.error(f"Failed to save files for {item_id}: txt={txt_file}, excel={excel_file}")
            
            logger.info(f"Final results: {list(results.keys())} (total: {len(results)} items)")
            
            # After all item IDs and types are processed, update generation status
            with generation_status['lock']:
                generation_status['is_generating'] = False
            
            if not results:
                logger.error("No results generated for any item IDs")
                # Provide more specific error messages based on the source type
                if source_type == 'azure':
                    return jsonify({'error': 'No Azure DevOps work items were successfully processed. Please check your credentials and work item IDs.'}), 400
                elif source_type == 'jira':
                    return jsonify({'error': 'No Jira issues were successfully processed. Please check your credentials and issue keys.'}), 400
                elif source_type == 'image':
                    return jsonify({'error': 'Failed to process the uploaded image. Please ensure the image is clear and readable.'}), 400
                else:
                    return jsonify({'error': 'Failed to generate test cases. Please check your input and try again.'}), 400
                
            # Before returning the final response in Jira/Azure handler
            formatted_test_cases = []
            for item_id in item_ids:
                if item_id in results:  # Only process IDs that have results
                    for idx, test_case in enumerate(results[item_id].get('test_cases', '').split('\n\n')):
                        if test_case.strip():
                            # Use the correct item_id for each test case
                            test_case_id = f"TC_{item_id}_{idx + 2}"
                            formatted_test_cases.append({
                                'test_case_id': test_case_id,
                                'content': test_case,
                                'status': ''
                            })
            
                                # Create MongoDB handler and save test case data
                    mongo_handler = MongoHandler()
                    url_key = mongo_handler.save_test_case({
                        'files': results,
                        'test_cases': formatted_test_cases,
                        'source_type': source_type,
                        'item_ids': item_ids
                    }, item_ids[0] if item_ids else None, source_type, current_user['id'] if current_user else None)
                    # Expose the url_key for redirect logic
                    with generation_status['lock']:
                        generation_status['final_url_key'] = url_key
                    
                    # Track successful test case generation with timing
                    generation_end_time = datetime.utcnow()
                    generation_duration = (generation_end_time - generation_start_time).total_seconds()
                    
                    try:
                        if mongo_handler:
                            event_data = {
                                "event_type": "test_case_generated",
                                "event_data": {
                                    "url_key": url_key,
                                    "source_type": source_type,
                                    "test_case_types": selected_types,
                                    "item_count": len(item_ids),
                                    "files_generated": len(results),
                                    "generation_duration_seconds": generation_duration,
                                    "generation_start_time": generation_start_time.isoformat(),
                                    "generation_end_time": generation_end_time.isoformat(),
                                    "average_time_per_item": generation_duration / len(item_ids) if item_ids else 0
                                },
                                "session_id": data.get('session_id'),
                                "user_agent": request.headers.get('User-Agent'),
                                "ip_address": request.remote_addr,
                                "source_type": source_type,
                                "test_case_types": selected_types,
                                "item_count": len(item_ids)
                            }
                            
                            # Add user information if available
                            if current_user:
                                event_data['user_id'] = current_user.get('id')
                                event_data['user_role'] = current_user.get('role')
                            mongo_handler.track_event(event_data)
                    except Exception as e:
                        logger.error(f"Failed to track test case generation: {str(e)}")
            
            return jsonify({
                'success': True,
                'url_key': url_key,
                'files': results
            })
            
    except Exception as e:
        logger.error(f"Error during generation: {str(e)}", exc_info=True)
        # Capture error in MongoDB with context
        capture_exception(e, {
            "source_type": source_type,
            "selected_types": selected_types,
            "item_ids": item_ids,
            "user_agent": request.headers.get('User-Agent', 'Unknown'),
            "ip_address": request.remote_addr
        })
        # Reset the generation status in case of errors
        with generation_status['lock']:
            generation_status['is_generating'] = False
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<path:filename>')
def download_file(filename):
    try:
        # Track download attempt
        try:
            mongo_handler = MongoHandler()
            event_data = {
                "event_type": "file_download_attempted",
                "event_data": {
                    "filename": filename,
                    "file_type": filename.split('.')[-1] if '.' in filename else 'unknown'
                },
                "user_agent": request.headers.get('User-Agent'),
                "ip_address": request.remote_addr,
                "source_type": None,
                "test_case_types": [],
                "item_count": 0
            }
            mongo_handler.track_event(event_data)
        except Exception as e:
            logger.error(f"Failed to track download attempt: {str(e)}")
        
        # Handle cloud deployment paths
        base_dir = os.path.dirname(__file__)
        generated_dir = os.path.join(base_dir, 'tests', 'generated')
        
        # Ensure the generated directory exists
        if not os.path.exists(generated_dir):
            os.makedirs(generated_dir, exist_ok=True)
            logger.info(f"Created generated directory: {generated_dir}")
        
        file_path = os.path.join(generated_dir, filename)
        
        # Log the file path for debugging
        logger.info(f"Attempting to download file: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            # Try to find the file by searching for it in the generated directory
            logger.info(f"Searching for file in: {generated_dir}")
            
            matching_files = []
            if os.path.exists(generated_dir):
                for file in os.listdir(generated_dir):
                    if filename in file:
                        matching_files.append(file)
            
            if matching_files:
                # Use the first matching file
                filename = matching_files[0]
                file_path = os.path.join(generated_dir, filename)
                logger.info(f"Found matching file: {filename}")
            else:
                logger.error(f"No matching files found for: {filename}")
                return jsonify({'error': 'File not found'}), 404
        
        # Check if status values were provided
        status_values = request.args.get('status')
        
        # Check if a custom filename was provided
        custom_filename = request.args.get('filename')
        
        # If it's an Excel file and status values are provided, update the file
        if status_values and filename.endswith('.xlsx'):
            try:
                status_dict = json.loads(status_values)
                logger.info(f"Updating Excel file with status values: {status_dict}")
                
                # Update the Excel file with status values
                import pandas as pd
                df = pd.read_excel(file_path)
                
                # Update each row where Title matches status key
                updated_count = 0
                for index, row in df.iterrows():
                    title = row.get('Title', '')
                    if title and title in status_dict:
                        df.at[index, 'Status'] = status_dict[title]
                        updated_count += 1
                
                logger.info(f"Updated {updated_count} rows with status values")
                
                # Save to a temporary file
                temp_file_path = f"{file_path}.temp.xlsx"
                df.to_excel(temp_file_path, index=False)
                
                # Use the temporary file for download with custom filename if provided
                if custom_filename:
                    response = send_file(temp_file_path, as_attachment=True, download_name=custom_filename)
                else:
                    response = send_file(temp_file_path, as_attachment=True)
                
                # Set up cleanup after request is complete
                @after_this_request
                def remove_temp_file(response):
                    try:
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                    except Exception as e:
                        logger.error(f"Error removing temp file: {e}")
                    return response
                    
            except Exception as e:
                logger.error(f"Error updating Excel with status values: {e}")
                # Fall back to original file if error occurs
                if custom_filename:
                    response = send_file(file_path, as_attachment=True, download_name=custom_filename)
                else:
                    response = send_file(file_path, as_attachment=True)
        
        # For TXT files with status values
        elif status_values and filename.endswith('.txt'):
            try:
                status_dict = json.loads(status_values)
                logger.info(f"Updating TXT file with status values: {status_dict}")
                
                # Read the original content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Create a temporary file
                temp_file_path = f"{file_path}.temp.txt"
                
                # Write updated content with status values appended
                with open(temp_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    f.write("\n\n# STATUS VALUES\n")
                    for title, status in status_dict.items():
                        if status:  # Only include non-empty status values
                            f.write(f"{title}: {status}\n")
                
                # Use the temporary file for download with custom filename if provided
                if custom_filename:
                    response = send_file(temp_file_path, as_attachment=True, download_name=custom_filename)
                else:
                    response = send_file(temp_file_path, as_attachment=True)
                
                # Set up cleanup after request is complete
                @after_this_request
                def remove_temp_file(response):
                    try:
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                    except Exception as e:
                        logger.error(f"Error removing temp file: {e}")
                    return response
                    
            except Exception as e:
                logger.error(f"Error updating TXT with status values: {e}")
                # Fall back to original file if error occurs
                if custom_filename:
                    response = send_file(file_path, as_attachment=True, download_name=custom_filename)
                else:
                    response = send_file(file_path, as_attachment=True)
        else:
            # Default case - no status values or not a handled file type
            if custom_filename:
                response = send_file(file_path, as_attachment=True, download_name=custom_filename)
            else:
                response = send_file(file_path, as_attachment=True)
            
        # Track successful download
        try:
            event_data = {
                "event_type": "file_download_successful",
                "event_data": {
                    "filename": filename,
                    "file_type": filename.split('.')[-1] if '.' in filename else 'unknown',
                    "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    "custom_filename": custom_filename
                },
                "user_agent": request.headers.get('User-Agent'),
                "ip_address": request.remote_addr,
                "source_type": None,
                "test_case_types": [],
                "item_count": 0
            }
            mongo_handler.track_event(event_data)
        except Exception as e:
            logger.error(f"Failed to track successful download: {str(e)}")
        
        # Add cache control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<url_key>')
def get_files_for_url_key(url_key):
    """Get list of files associated with a URL key"""
    try:
        logger.info(f"Requested files for URL key: {url_key}")
        
        # Get the document from MongoDB
        mongo_handler = MongoHandler()
        doc = mongo_handler.collection.find_one({"url_key": url_key})
        
        if not doc:
            logger.error(f"No document found for URL key: {url_key}")
            return jsonify({'error': 'Document not found'}), 404
        
        files = []
        
        # Check if the document has files information
        if 'test_data' in doc and isinstance(doc['test_data'], dict):
            test_data = doc['test_data']
            
            # Check for files in the test_data
            if 'files' in test_data and isinstance(test_data['files'], dict):
                for item_id, file_info in test_data['files'].items():
                    if isinstance(file_info, dict):
                        if 'excel' in file_info:
                            files.append(file_info['excel'])
                        if 'txt' in file_info:
                            files.append(file_info['txt'])
            
            # Also check for direct file references
            if 'files' in test_data and isinstance(test_data['files'], list):
                files.extend(test_data['files'])
        
        # If no files found in document, try to find files based on source type and item_id
        if not files:
            source_type = doc.get('source_type', '')
            item_id = doc.get('item_id', '')
            
            if source_type and item_id:
                # Generate possible file names based on the source type and item_id
                base_dir = os.path.join(os.path.dirname(__file__), 'tests', 'generated')
                
                if os.path.exists(base_dir):
                    # Look for files that match the item_id pattern
                    for filename in os.listdir(base_dir):
                        if item_id in filename and (filename.endswith('.xlsx') or filename.endswith('.txt')):
                            files.append(filename)
        
        logger.info(f"Found {len(files)} files for URL key {url_key}: {files}")
        
        return jsonify({'files': files})
        
    except Exception as e:
        logger.error(f"Error getting files for URL key {url_key}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-content/<url_key>')
def get_ai_content(url_key):
    """Get AI-generated content for a URL key"""
    try:
        logger.info(f"Requested AI content for URL key: {url_key}")
        
        # Get the document from MongoDB
        mongo_handler = MongoHandler()
        doc = mongo_handler.collection.find_one({"url_key": url_key})
        
        if not doc:
            logger.error(f"No document found for URL key: {url_key}")
            return jsonify({'error': 'Document not found'}), 404
        
        # Check if the document has test_cases content
        if 'test_data' in doc and isinstance(doc['test_data'], dict):
            test_data = doc['test_data']
            
            # Look for test_cases in the test_data
            if 'test_cases' in test_data:
                content = test_data['test_cases']
                if isinstance(content, str):
                    return jsonify({'content': content})
                elif isinstance(content, list):
                    # If it's a list, join the content
                    return jsonify({'content': '\n\n'.join([str(item) for item in content])})
        
        # If no test_cases found, try to get from files
        if 'test_data' in doc and isinstance(doc['test_data'], dict):
            test_data = doc['test_data']
            
            if 'files' in test_data and isinstance(test_data['files'], dict):
                for item_id, file_info in test_data['files'].items():
                    if isinstance(file_info, dict) and 'txt' in file_info:
                        # Try to read the text file
                        try:
                            base_dir = os.path.join(os.path.dirname(__file__), 'tests', 'generated')
                            file_path = os.path.join(base_dir, file_info['txt'])
                            
                            if os.path.exists(file_path):
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                return jsonify({'content': content})
                        except Exception as e:
                            logger.warning(f"Could not read file {file_info['txt']}: {e}")
        
        logger.warning(f"No AI content found for URL key: {url_key}")
        return jsonify({'error': 'No AI content found'}), 404
        
    except Exception as e:
        logger.error(f"Error getting AI content for URL key {url_key}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/results/<url_key>/test-cases')
def get_test_cases_for_url_key(url_key):
    """Get test cases data for a URL key"""
    try:
        logger.info(f"Requested test cases for URL key: {url_key}")
        
        # Get the document from MongoDB
        mongo_handler = MongoHandler()
        doc = mongo_handler.collection.find_one({"url_key": url_key})
        
        if not doc:
            logger.error(f"No document found for URL key: {url_key}")
            return jsonify({'error': 'Document not found'}), 404
        
        # Check if the document has test_data
        if 'test_data' in doc and isinstance(doc['test_data'], list):
            # If test_data is already a list of test cases, return it directly
            return jsonify({'test_cases': doc['test_data']})
        
        # If test_data is a dict, look for structured test cases
        if 'test_data' in doc and isinstance(doc['test_data'], dict):
            test_data = doc['test_data']
            
            # First check if test_data has a test_data field that's a list
            if 'test_data' in test_data and isinstance(test_data['test_data'], list) and len(test_data['test_data']) > 0:
                return jsonify({'test_cases': test_data['test_data']})
            
            # Look for files and try to extract test cases from Excel files
            if 'files' in test_data and isinstance(test_data['files'], dict):
                for item_id, file_info in test_data['files'].items():
                    if isinstance(file_info, dict) and 'excel' in file_info:
                        # Try to read the Excel file and extract test cases
                        try:
                            base_dir = os.path.join(os.path.dirname(__file__), 'tests', 'generated')
                            file_path = os.path.join(base_dir, file_info['excel'])
                            
                            if os.path.exists(file_path):
                                import pandas as pd
                                df = pd.read_excel(file_path)
                                
                                # Convert to records and handle NaN values
                                records = []
                                for index, row in df.iterrows():
                                    record = {}
                                    for column in df.columns:
                                        value = row[column]
                                        if pd.isna(value):
                                            record[column] = None
                                        else:
                                            record[column] = value
                                    records.append(record)
                                
                                if records:
                                    return jsonify({'test_cases': records})
                        except Exception as e:
                            logger.warning(f"Could not read Excel file {file_info['excel']}: {e}")
            
            # If no files found, try to parse the test_cases string if it exists
            if 'test_cases' in test_data and isinstance(test_data['test_cases'], str):
                # Try to parse the test cases string using the traditional format parser
                try:
                    from utils.file_handler import parse_traditional_format, extract_test_type_sections
                    
                    # First try to extract sections if TEST TYPE markers exist
                    sections = extract_test_type_sections(test_data['test_cases'])
                    if sections:
                        # Parse each section separately
                        all_parsed_cases = []
                        for section_name, section_content in sections.items():
                            section_cases = parse_traditional_format(section_content, default_section=section_name)
                            all_parsed_cases.extend(section_cases)
                        
                        if all_parsed_cases:
                            return jsonify({'test_cases': all_parsed_cases})
                    else:
                        # If no sections found, try parsing the whole string
                        parsed_cases = parse_traditional_format(test_data['test_cases'])
                        if parsed_cases:
                            return jsonify({'test_cases': parsed_cases})
                except Exception as e:
                    logger.warning(f"Could not parse test cases string: {e}")
        
        logger.warning(f"No test cases found for URL key: {url_key}")
        return jsonify({'error': 'No test cases found'}), 404
        
    except Exception as e:
        logger.error(f"Error getting test cases for URL key {url_key}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-tests/<url_key>')
def get_ai_tests_for_url_key(url_key):
    """Get AI test cases for a URL key"""
    try:
        logger.info(f"Requested AI tests for URL key: {url_key}")
        
        # Get the document from MongoDB
        mongo_handler = MongoHandler()
        doc = mongo_handler.collection.find_one({"url_key": url_key})
        
        if not doc:
            logger.error(f"No document found for URL key: {url_key}")
            return jsonify({'error': 'Document not found'}), 404
        
        # Check if the document has test_data
        if 'test_data' in doc and isinstance(doc['test_data'], list):
            # If test_data is already a list of test cases, return it directly
            return jsonify({'test_cases': doc['test_data']})
        
        # If test_data is a dict, look for structured test cases
        if 'test_data' in doc and isinstance(doc['test_data'], dict):
            test_data = doc['test_data']
            
            # First check if test_data has a test_data field that's a list
            if 'test_data' in test_data and isinstance(test_data['test_data'], list) and len(test_data['test_data']) > 0:
                return jsonify({'test_cases': test_data['test_data']})
            
            # Look for files and try to extract test cases from Excel files
            if 'files' in test_data and isinstance(test_data['files'], dict):
                for item_id, file_info in test_data['files'].items():
                    if isinstance(file_info, dict) and 'excel' in file_info:
                        # Try to read the Excel file and extract test cases
                        try:
                            base_dir = os.path.join(os.path.dirname(__file__), 'tests', 'generated')
                            file_path = os.path.join(base_dir, file_info['excel'])
                            
                            if os.path.exists(file_path):
                                import pandas as pd
                                df = pd.read_excel(file_path)
                                
                                # Convert to records and handle NaN values
                                records = []
                                for index, row in df.iterrows():
                                    record = {}
                                    for column in df.columns:
                                        value = row[column]
                                        if pd.isna(value):
                                            record[column] = None
                                        else:
                                            record[column] = value
                                    records.append(record)
                                
                                if records:
                                    return jsonify({'test_cases': records})
                        except Exception as e:
                            logger.warning(f"Could not read Excel file {file_info['excel']}: {e}")
            
            # If no files found, try to parse the test_cases string if it exists
            if 'test_cases' in test_data and isinstance(test_data['test_cases'], str):
                # Try to parse the test cases string using the traditional format parser
                try:
                    from utils.file_handler import parse_traditional_format, extract_test_type_sections
                    
                    # First try to extract sections if TEST TYPE markers exist
                    sections = extract_test_type_sections(test_data['test_cases'])
                    if sections:
                        # Parse each section separately
                        all_parsed_cases = []
                        for section_name, section_content in sections.items():
                            section_cases = parse_traditional_format(section_content, default_section=section_name)
                            all_parsed_cases.extend(section_cases)
                        
                        if all_parsed_cases:
                            return jsonify({'test_cases': all_parsed_cases})
                    else:
                        # If no sections found, try parsing the whole string
                        parsed_cases = parse_traditional_format(test_data['test_cases'])
                        if parsed_cases:
                            return jsonify({'test_cases': parsed_cases})
                except Exception as e:
                    logger.warning(f"Could not parse test cases string: {e}")
        
        logger.warning(f"No AI tests found for URL key: {url_key}")
        return jsonify({'error': 'No AI tests found'}), 404
        
    except Exception as e:
        logger.error(f"Error getting AI tests for URL key {url_key}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/content/<path:filename>')
def get_file_content(filename):
    try:
        logger.info(f"Requested content for file: {filename}")
        
        # Convert undefined or None to more descriptive error
        if filename == 'undefined' or filename is None:
            logger.error(f"Invalid filename: '{filename}'")
            return jsonify({'error': 'Invalid filename provided'}), 400
            
        # Handle cloud deployment paths
        base_dir = os.path.dirname(__file__)
        generated_dir = os.path.join(base_dir, 'tests', 'generated')
        
        # Ensure the generated directory exists
        if not os.path.exists(generated_dir):
            os.makedirs(generated_dir, exist_ok=True)
            logger.info(f"Created generated directory: {generated_dir}")
            
        # Check if the file exists in the generated directory
        file_path = os.path.join(generated_dir, filename)
        logger.info(f"Looking for file at: {file_path}")
        
        if not os.path.exists(file_path):
            # Try to find the file by searching for it in the generated directory
            logger.info(f"File not found at exact path, searching in {generated_dir}")
            
            # Check if filename contains any part of actual files in the directory
            matching_files = []
            if os.path.exists(generated_dir):
                for file in os.listdir(generated_dir):
                    if filename in file:
                        matching_files.append(file)
            
            if matching_files:
                # Use the first matching file
                filename = matching_files[0]
                file_path = os.path.join(generated_dir, filename)
                logger.info(f"Found matching file: {filename}")
            else:
                logger.error(f"File not found: {file_path}")
                return jsonify({'error': 'File not found'}), 404
        
        if filename.endswith('.xlsx'):
            import pandas as pd
            import numpy as np
            import json
            
            logger.info(f"Reading Excel file: {filename}")
            
            try:
                # Read the Excel file
                df = pd.read_excel(file_path)
                logger.info(f"Excel file read successfully with {len(df)} rows and columns: {list(df.columns)}")
                
                # Get status values if provided
                status_values = request.args.get('status')
                status_dict = {}
                if status_values:
                    try:
                        status_dict = json.loads(status_values)
                        logger.info(f"Applying status values to content: {status_dict}")
                    except Exception as e:
                        logger.error(f"Error parsing status values: {e}")
                
                # Convert to records and handle NaN values
                records = []
                for index, row in df.iterrows():
                    record = {}
                    for column in df.columns:
                        value = row[column]
                        # Handle NaN, NaT, and other non-JSON-serializable values
                        if pd.isna(value):
                            record[column] = None
                        else:
                            record[column] = value
                    
                    # Update status if available
                    title = record.get('Title', '')
                    if title and title in status_dict:
                        record['Status'] = status_dict[title]
                    
                    # Parse Steps field if it's a string with numbered steps
                    if 'Steps' in record and isinstance(record['Steps'], str):
                        steps_text = record['Steps']
                        # If it looks like numbered steps, convert to array
                        if re.search(r'^\d+\.', steps_text):
                            steps = re.split(r'\n\s*\d+\.|\n', steps_text)
                            # Clean up steps
                            steps = [s.strip() for s in steps if s.strip()]
                            if steps:
                                record['Steps'] = steps
                    
                    records.append(record)
                
                logger.info(f"Converted Excel file {filename} to {len(records)} records")
                
                # If no records were found, check if it might be due to incorrect column names
                if not records or (len(records) == 1 and not any(records[0].values())):
                    logger.warning(f"No valid records found in Excel file, checking for column issues")
                    
                    # Try to read the raw data and convert manually
                    raw_data = pd.read_excel(file_path, header=None)
                    if len(raw_data) > 1:  # At least has header row + one data row
                        # Assuming first row is header
                        headers = [str(h).strip() for h in raw_data.iloc[0]]
                        
                        # Create records from remaining rows
                        manual_records = []
                        for i in range(1, len(raw_data)):
                            record = {}
                            for j, header in enumerate(headers):
                                if j < len(raw_data.columns):
                                    value = raw_data.iloc[i, j]
                                    if pd.isna(value):
                                        record[header] = None
                                    else:
                                        record[header] = value
                            manual_records.append(record)
                        
                        if manual_records:
                            logger.info(f"Manually extracted {len(manual_records)} records with headers: {headers}")
                            records = manual_records
                
                return jsonify({
                    'content': records
                })
            except Exception as e:
                logger.error(f"Error processing Excel file {filename}: {str(e)}", exc_info=True)
                return jsonify({'error': f"Error processing Excel file: {str(e)}"}), 500
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                logger.info(f"Successfully read text file: {filename} ({len(content)} characters)")
                return jsonify({'content': content})
            except Exception as e:
                logger.error(f"Error reading text file {filename}: {str(e)}")
                return jsonify({'error': f"Error reading text file: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error in get_file_content for {filename}: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 404

@app.route('/api/update-status', methods=['POST'])
def update_status():
    try:
        data = request.json
        logger.info(f"Received status update request: {data}")
        
        url_key = data.get('key')
        test_case_id = data.get('test_case_id')
        status = data.get('status')
        is_shared_view = data.get('shared_view', False)

        # Validate required parameters
        if not url_key:
            return jsonify({'error': 'Missing required parameter: key'}), 400
        if not test_case_id:
            return jsonify({'error': 'Missing required parameter: test_case_id'}), 400
        if not status:
            return jsonify({'error': 'Missing required parameter: status'}), 400
            
        # Validate status is not empty string
        if status.strip() == '':
            return jsonify({'error': 'Status cannot be empty'}), 400

        mongo_handler = MongoHandler()
        
        # First verify the document exists
        doc = mongo_handler.collection.find_one({"url_key": url_key})
        if not doc:
            error_msg = f"No document found with url_key: {url_key}"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 404
        
        # Try to update using the MongoHandler
        success = mongo_handler.update_test_case_status(url_key, test_case_id, status)
        
        if success:
            # Force an update to the status dict and test data array in a single operation
            # This ensures both copies of the data are updated
            result = mongo_handler.collection.update_one(
                {"url_key": url_key},
                {
                    "$set": {
                        f"status.{test_case_id}": status,
                        f"status_timestamps.{test_case_id}": datetime.utcnow(),
                        "status_updated_at": datetime.utcnow()
                    }
                }
            )
            
            # For shared view, we also need to update the test_data array entries directly
            if is_shared_view and 'test_data' in doc and isinstance(doc['test_data'], list):
                for i, tc in enumerate(doc['test_data']):
                    if tc.get('Title') == test_case_id:
                        # Update the Status field directly in the array
                        mongo_handler.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.{i}.Status": status}}
                        )
                        logger.info(f"Updated status in test_data array index {i}")
                        break
            
            logger.info(f"Successfully updated status for test case '{test_case_id}'")
            return jsonify({'success': True})
        else:
            error_msg = f"Failed to update status for test case {test_case_id} in document {url_key}"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 404

    except Exception as e:
        logger.error(f"Error updating status: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Initialize MongoDB handler
mongo_handler = MongoHandler()

@app.route('/api/share', methods=['POST'])
def share_test_case():
    try:
        # Check if user is authenticated
        current_user = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(' ')[1]
                auth_mongo_handler = MongoHandler()
                user_info = auth_mongo_handler.verify_jwt_token(token)
                if user_info and user_info.get('success'):
                    current_user = user_info['user']
            except Exception as e:
                logger.warning(f"Failed to verify auth token: {str(e)}")
                # Continue without authentication

        # Handle both JSON and form data for cloud compatibility
        if request.is_json:
            data = request.json
        else:
            # Fallback for form data
            data = request.form.to_dict()
            # Try to parse JSON strings in form data
            for key, value in data.items():
                if isinstance(value, str) and value.startswith('{'):
                    try:
                        data[key] = json.loads(value)
                    except:
                        pass
        
        logger.info(f"Share request data: {data}")
        
        test_data = data.get('test_data')
        item_id = data.get('item_id')
        item_ids = data.get('item_ids', [])
        status_values = data.get('status_values', {})
        source_type = data.get('source_type')  # Extract source type for proper identification
        
        if not test_data:
            return jsonify({'error': 'No test data provided'}), 400

        # Create a new MongoDB handler for this request
        mongo_handler = MongoHandler()
        if not mongo_handler:
            logger.error("MongoDB handler not initialized")
            return jsonify({'error': 'Database connection error'}), 500

        # Save the test case with status values
        # Use item_ids if provided, otherwise fall back to item_id
        if item_ids and len(item_ids) > 0:
            url_key = mongo_handler.save_test_case(test_data, item_ids[0] if len(item_ids) == 1 else item_ids, source_type, current_user['id'] if current_user else None)
        else:
            url_key = mongo_handler.save_test_case(test_data, item_id, source_type, current_user['id'] if current_user else None)
        
        # If status values were provided, save them too
        if status_values:
            try:
                mongo_handler.update_status_dict(url_key, status_values)
                logger.info(f"Saved status values for {url_key}: {status_values}")
            except Exception as e:
                logger.error(f"Error saving status values: {e}")
                # Continue without status values if there's an error
        
        # Create the share URL - use BASE_URL from settings or detect from request headers
        from config.settings import BASE_URL
        
        # Try to get the actual domain from request headers (for production)
        if request.headers.get('X-Forwarded-Host'):
            # Use the forwarded host (common in production with reverse proxies)
            base_url = f"https://{request.headers.get('X-Forwarded-Host')}"
        elif request.headers.get('X-Forwarded-Proto') and request.headers.get('Host'):
            # Use forwarded protocol and host
            protocol = request.headers.get('X-Forwarded-Proto', 'https')
            base_url = f"{protocol}://{request.headers.get('Host')}"
        elif request.headers.get('Host') and not request.headers.get('Host').startswith('127.0.0.1') and not request.headers.get('Host').startswith('localhost'):
            # Use the Host header if it's not localhost
            base_url = f"https://{request.headers.get('Host')}"
        else:
            # Fall back to BASE_URL from settings
            base_url = BASE_URL.rstrip('/')
        
        share_url = f"{base_url}/view/{url_key}"
        
        # Log URL generation details for debugging
        logger.info(f"URL generation details:")
        logger.info(f"  - X-Forwarded-Host: {request.headers.get('X-Forwarded-Host')}")
        logger.info(f"  - X-Forwarded-Proto: {request.headers.get('X-Forwarded-Proto')}")
        logger.info(f"  - Host: {request.headers.get('Host')}")
        logger.info(f"  - BASE_URL from settings: {BASE_URL}")
        logger.info(f"  - Selected base_url: {base_url}")
        logger.info(f"  - Generated share URL: {share_url}")
        logger.info(f"  - Request URL: {request.url}")
        logger.info(f"  - Request base URL: {request.base_url}")
        
        # Track successful share creation
        try:
            event_data = {
                "event_type": "share_created_successfully",
                "event_data": {
                    "url_key": url_key,
                    "share_url": share_url,
                    "test_data_count": len(test_data) if isinstance(test_data, list) else 1,
                    "has_status_values": bool(status_values),
                    "status_values_count": len(status_values) if status_values else 0
                },
                "user_agent": request.headers.get('User-Agent'),
                "ip_address": request.remote_addr,
                "source_type": None,
                "test_case_types": [],
                "item_count": 0
            }
            mongo_handler.track_event(event_data)
        except Exception as e:
            logger.error(f"Failed to track successful share creation: {str(e)}")
        
        return jsonify({
            'success': True,
            'share_url': share_url,
            'url_key': url_key
        })
    except Exception as e:
        logger.error(f"Error in share_test_case: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/view/<url_key>')
def view_shared_test_case(url_key):
    try:
        # Track view page visit
        try:
            mongo_handler = MongoHandler()
            event_data = {
                "event_type": "shared_page_visited",
                "event_data": {
                    "url_key": url_key,
                    "format": request.args.get('format', 'html')
                },
                "user_agent": request.headers.get('User-Agent'),
                "ip_address": request.remote_addr,
                "source_type": None,
                "test_case_types": [],
                "item_count": 0
            }
            mongo_handler.track_event(event_data)
        except Exception as e:
            logger.error(f"Failed to track view page visit: {str(e)}")
        
        # Check if JSON format was requested
        format_param = request.args.get('format', '').lower()
        want_json = format_param == 'json'
        
        test_case = mongo_handler.get_test_case(url_key)
        if not test_case:
            if want_json:
                return jsonify({'error': 'Test case not found'}), 404
            else:
                return render_template('404.html'), 404
        
        # Make sure the key is included in the test_case object
        test_case['key'] = url_key
        
        # Process test data to ensure it's in the right format
        if 'test_data' in test_case:
            # If test_data is a list, it's already structured
            if isinstance(test_case['test_data'], list):
                logger.info(f"Test data for {url_key} is already a list with {len(test_case['test_data'])} items")
            else:
                # If test_data is a dict with test_cases array, extract it
                if isinstance(test_case['test_data'], dict) and 'test_cases' in test_case['test_data']:
                    test_case['test_data'] = test_case['test_data']['test_cases']
                    logger.info(f"Extracted test_cases array with {len(test_case['test_data'])} items")
                # If test_data is a dict with files, try to parse the files
                elif isinstance(test_case['test_data'], dict) and 'files' in test_case['test_data']:
                    try:
                        # Get file paths
                        files = test_case['test_data'].get('files', {})
                        excel_file = files.get('excel')
                        
                        if excel_file:
                            # Try to read Excel file
                            excel_path = os.path.join(os.path.dirname(__file__), 'tests', 'generated', excel_file)
                            if os.path.exists(excel_path):
                                import pandas as pd
                                df = pd.read_excel(excel_path)
                                structured_data = df.to_dict('records')
                                test_case['test_data'] = structured_data
                                logger.info(f"Parsed Excel file into {len(structured_data)} records")
                        
                        # If we couldn't get data from Excel, check if there's a txt file
                        if not isinstance(test_case['test_data'], list) and 'txt' in files:
                            txt_file = files.get('txt')
                            if txt_file:
                                txt_path = os.path.join(os.path.dirname(__file__), 'tests', 'generated', txt_file)
                                if os.path.exists(txt_path):
                                    with open(txt_path, 'r', encoding='utf-8') as f:
                                        txt_content = f.read()
                                    
                                    # Parse the text content
                                    from utils.file_handler import extract_test_type_sections, parse_traditional_format
                                    sections = extract_test_type_sections(txt_content)
                                    
                                    structured_data = []
                                    if sections:
                                        for section_name, section_content in sections.items():
                                            parsed_cases = parse_traditional_format(section_content, default_section=section_name)
                                            structured_data.extend(parsed_cases)
                                    else:
                                        structured_data = parse_traditional_format(txt_content)
                                    
                                    if structured_data:
                                        test_case['test_data'] = structured_data
                                        logger.info(f"Parsed text file into {len(structured_data)} records")
                    except Exception as e:
                        logger.error(f"Error processing files for view: {str(e)}")
        
        # Apply any status values that might exist
        if 'status' in test_case and isinstance(test_case['status'], dict) and isinstance(test_case['test_data'], list):
            status_dict = test_case['status']
            status_timestamps = test_case.get('status_timestamps', {})
            for tc in test_case['test_data']:
                if 'Title' in tc and tc['Title'] in status_dict:
                    tc['Status'] = status_dict[tc['Title']]
                    # Add timestamp information
                    if tc['Title'] in status_timestamps:
                        tc['StatusUpdatedAt'] = status_timestamps[tc['Title']]
        
        # Return JSON or HTML based on the format parameter
        if want_json:
            # Convert ObjectId to string for JSON serialization
            if '_id' in test_case:
                test_case['_id'] = str(test_case['_id'])
                
            return jsonify(test_case)
        else:
            return render_template('view.html', test_case=test_case)
    except Exception as e:
        logger.error(f"Error in view_shared_test_case: {str(e)}", exc_info=True)
        if format_param == 'json':
            return jsonify({'error': str(e)}), 500
        else:
            return render_template('404.html'), 404

@app.route('/api/shared/excel/<url_key>')
def download_shared_excel(url_key):
    try:
        # Get the test case data from MongoDB
        test_case = mongo_handler.get_test_case(url_key)
        if not test_case:
            return jsonify({'error': 'Test case not found'}), 404
        
        # Check if a custom filename was provided in the request
        custom_filename = request.args.get('filename')
        
        # Get status values if provided in the request
        status_values = request.args.get('status')
        status_dict = {}
        if status_values:
            try:
                status_dict = json.loads(status_values)
                logger.info(f"SHARED EXCEL: Received {len(status_dict)} status values: {status_dict}")
            except Exception as e:
                logger.error(f"SHARED EXCEL: Error parsing status values: {e}")
        else:
            logger.info("SHARED EXCEL: No status values provided")
        
        # Generate default filename based on item_id or use generic name if no custom filename
        if not custom_filename:
            if test_case.get('item_id'):
                custom_filename = f"test_{test_case['item_id']}.xlsx"
            else:
                custom_filename = f"test_shared_{url_key[:8]}.xlsx"
        
        # Use item_id for the base name of the generated file
        if test_case.get('item_id'):
            file_base_name = f"test_{test_case['item_id']}"
        else:
            file_base_name = f"test_shared_{url_key[:8]}"
        
        # Format test data properly for Excel generation
        test_data = test_case['test_data']
        
        # Now format for Excel generation
        import json
        formatted_data = ""
        
        # Track which test cases have status updates
        status_updated = set()
        updated_count = 0
        
        for tc in test_data:
            formatted_data += "TEST CASE:\n"
            if 'Title' in tc:
                title = tc.get('Title', '')
                formatted_data += f"Title: {title}\n"
            if 'Scenario' in tc:
                formatted_data += f"Scenario: {tc.get('Scenario', '')}\n"
            
            # Handle steps with special care for arrays
            if 'Steps' in tc:
                steps = tc.get('Steps', '')
                formatted_data += "Steps to reproduce:\n"
                if isinstance(steps, list):
                    for i, step in enumerate(steps):
                        formatted_data += f"{i+1}. {step}\n"
                else:
                    formatted_data += f"1. {steps}\n"
            
            if 'Expected Result' in tc:
                formatted_data += f"Expected Result: {tc.get('Expected Result', '')}\n"
            
            # Explicitly include Status with extra prominence
            # Get from status_dict if available (DOM values), otherwise from test case
            title = tc.get('Title', '')
            status = ''
            if title and title in status_dict:
                status = status_dict[title]
                status_updated.add(title)
                updated_count += 1
            else:
                status = tc.get('Status', '')
            
            # Make sure status is clearly visible
            formatted_data += f"Status: {status}\n\n"
            
            if 'Priority' in tc:
                formatted_data += f"Priority: {tc.get('Priority', '')}\n"
            
            formatted_data += "\n\n"
        
        logger.info(f"SHARED EXCEL: Updated {updated_count} test cases with status values")
        
        # Add a summary of all status values at the end for debugging
        formatted_data += "\n\n# STATUS SUMMARY\n"
        for title, status in status_dict.items():
            if status:
                formatted_data += f"{title}: {status}\n"
        
        test_data_str = formatted_data
        
        # Generate Excel file
        from utils.file_handler import save_excel_report
        excel_file = save_excel_report(test_data_str, file_base_name)
        
        if not excel_file:
            return jsonify({'error': 'Failed to generate Excel file'}), 500
        
        # Return the Excel file with the custom filename
        file_path = os.path.join(os.path.dirname(__file__), 'tests', 'generated', excel_file)
        response = send_file(file_path, as_attachment=True, download_name=custom_filename)
        
        # Add aggressive cache control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Status-Updated-Count"] = str(updated_count)
        response.headers["X-Status-Update-Time"] = str(datetime.now())
        
        return response
    except Exception as e:
        logger.error(f"Error generating Excel file: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Add this after the generate endpoint
@app.route('/api/generation-status')
def get_generation_status():
    try:
        with generation_status['lock']:
            # Calculate progress percentage based on completed types vs total types
            progress_percentage = 0
            if generation_status['total_types']:
                progress_percentage = (len(generation_status['completed_types']) / len(generation_status['total_types'])) * 100
                
            # Ensure progress is a valid number between 0-100
            if math.isnan(progress_percentage) or progress_percentage < 0:
                progress_percentage = 0
            elif progress_percentage > 100:
                progress_percentage = 100
            
            response = {
                'is_generating': generation_status['is_generating'],
                'completed_types': list(generation_status['completed_types']),
                'total_types': list(generation_status['total_types']),
                'progress_percentage': progress_percentage,
                'files_ready': not generation_status['is_generating'],
                'phase': generation_status.get('phase', ''),
                'current_test_type': generation_status.get('current_test_type', ''),
                'log': list(generation_status.get('log', [])),
                'final_url_key': generation_status.get('final_url_key', '')  # Include final URL key when available
            }
            logger.info(f"Generation status response - final_url_key: {response['final_url_key']}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Error getting generation status: {str(e)}")
        return jsonify({'error': str(e), 'progress_percentage': 0, 'is_generating': False, 'files_ready': True}), 500

@app.route('/api/shared-status', methods=['GET'])
def get_shared_status():
    try:
        url_key = request.args.get('key')
        include_files = request.args.get('includeFiles', 'false').lower() == 'true'
        
        if not url_key:
            return jsonify({'error': 'Missing URL key parameter'}), 400
            
        logger.info(f"Fetching shared status for URL key: {url_key}")
        mongo_handler = MongoHandler()
        
        # Get all status values for the test cases in this document
        # Force refresh from database rather than using cached data
        status_values = mongo_handler.get_test_case_status_values(url_key, force_refresh=True)
        
        if status_values is None:
            return jsonify({'error': 'Test case not found'}), 404
        
        response_data = {
            'success': True,
            'status_values': status_values,
            'timestamp': str(datetime.now())  # Add timestamp for debugging
        }
        
        # Include file paths if requested
        if include_files:
            doc = mongo_handler.collection.find_one({"url_key": url_key})
            if doc:
                # Always include the document data for source_type and item_ids
                response_data['document'] = doc
                
                if 'test_data' in doc:
                    # Check for different document structures
                    if 'files' in doc['test_data']:
                        response_data['files'] = doc['test_data']['files']
                        
                        # Extract item IDs from files structure
                        files_data = doc['test_data']['files']
                        if files_data:
                            # Extract item IDs from file keys
                            item_ids = list(files_data.keys())
                            logger.info(f"Extracted item IDs from files: {item_ids}")
                            
                            # Update the document with proper item_ids
                            doc['item_ids'] = item_ids
                            # Remove the old item_id if it exists
                            if 'item_id' in doc:
                                del doc['item_id']
                            
                            # Add source_type from test_data if available
                            if 'source_type' in doc['test_data']:
                                doc['source_type'] = doc['test_data']['source_type']
                                logger.info(f"Added source_type to document: {doc['source_type']}")
                            else:
                                # Set default source type based on context
                                doc['source_type'] = 'Jira'
                                logger.info(f"Using default source_type: Jira")
                            
                            # Update response_data document
                            response_data['document'] = doc
                        
                        # Extract test cases from files structure
                        try:
                            from utils.file_handler import parse_traditional_format
                            # Get test cases from ALL files, not just the first one
                            all_test_cases = []
                            
                            # Process each file to get test cases
                            for file_key, file_data in files_data.items():
                                logger.info(f"Processing file: {file_key}")
                                
                                if 'test_cases' in file_data and isinstance(file_data['test_cases'], str):
                                    test_cases_content = file_data['test_cases']
                                    logger.info(f"Found test cases content for {file_key} (length: {len(test_cases_content)})")
                                    
                                    parsed_test_cases = parse_traditional_format(test_cases_content)
                                    if parsed_test_cases:
                                        # Add item identifier to test case titles to distinguish them
                                        for tc in parsed_test_cases:
                                            if 'Title' in tc:
                                                tc['Title'] = f"{tc['Title']} ({file_key})"
                                        
                                        all_test_cases.extend(parsed_test_cases)
                                        logger.info(f"Successfully parsed {len(parsed_test_cases)} test cases from {file_key}")
                                    else:
                                        logger.warning(f"No test cases parsed from {file_key}")
                                else:
                                    logger.warning(f"No test_cases string found in {file_key}")
                            
                            if all_test_cases:
                                response_data['test_data'] = all_test_cases
                                logger.info(f"Successfully combined {len(all_test_cases)} total test cases from all files")
                                # Don't process test_cases array if we successfully processed files
                                return jsonify(response_data)
                            else:
                                logger.warning("No test cases found in any files")
                        except Exception as e:
                            logger.warning(f"Error parsing test cases from files: {e}")
                            import traceback
                            logger.warning(f"Traceback: {traceback.format_exc()}")
                            
                    # Handle Image and URL source types that store test_data directly
                    elif 'test_data' in doc and isinstance(doc['test_data'], list):
                        logger.info(f"Found direct test_data list for {doc.get('source_type', 'unknown')} source type")
                        response_data['test_data'] = doc['test_data']
                        
                        # For URL source type, use the actual URL as item_id instead of file keys
                        if doc.get('source_type') == 'url' and 'url' in doc:
                            doc['item_ids'] = [doc['url']]
                            logger.info(f"Set URL as item_id: {doc['url']}")
                        # For Image source type, use a descriptive identifier
                        elif doc.get('source_type') == 'image':
                            doc['item_ids'] = ['Uploaded Image']
                            logger.info(f"Set Image item_id: Uploaded Image")
                        
                        response_data['document'] = doc
                        logger.info(f"Successfully loaded {len(doc['test_data'])} test cases from direct test_data")
                        return jsonify(response_data)
                    
                    # Handle nested test_data structure (URL generation stores data this way)
                    elif 'test_data' in doc and isinstance(doc['test_data'], dict):
                        logger.info(f"Found nested test_data dict for {doc.get('source_type', 'unknown')} source type")
                        
                        nested_test_data = doc['test_data']
                        
                        # Check if this is URL data with nested structure (only when the document itself is URL type)
                        if (
                            (doc.get('source_type') in (None, '', 'url')) 
                            and 'source_type' in nested_test_data 
                            and nested_test_data['source_type'] == 'url'
                        ):
                            logger.info(f"Found URL data with nested structure")
                            
                            # Extract the actual test cases from the nested structure
                            if 'test_data' in nested_test_data and isinstance(nested_test_data['test_data'], list):
                                response_data['test_data'] = nested_test_data['test_data']
                                
                                # Set the source type and URL from the nested structure
                                doc['source_type'] = nested_test_data['source_type']
                                doc['url'] = nested_test_data.get('url', '')
                                doc['item_ids'] = [nested_test_data.get('url', '')]
                                
                                response_data['document'] = doc
                                logger.info(f"Successfully loaded {len(nested_test_data['test_data'])} URL test cases from nested structure")
                                return jsonify(response_data)
                        
                        # Check if this is Image data with nested structure (only when the document itself is Image type)
                        elif (
                            (doc.get('source_type') in (None, '', 'image'))
                            and 'source_type' in nested_test_data 
                            and nested_test_data['source_type'] == 'image'
                        ):
                            logger.info(f"Found Image data with nested structure")
                            
                            # Extract the actual test cases from the nested structure
                            if 'test_data' in nested_test_data and isinstance(nested_test_data['test_data'], list):
                                response_data['test_data'] = nested_test_data['test_data']
                                
                                # Set the source type and image_id from the nested structure
                                doc['source_type'] = nested_test_data['source_type']
                                doc['image_id'] = nested_test_data.get('image_id', '')
                                doc['item_ids'] = ['Uploaded Image']
                                
                                response_data['document'] = doc
                                logger.info(f"Successfully loaded {len(nested_test_data['test_data'])} Image test cases from nested structure")
                                return jsonify(response_data)
                            
                    # Only process test_cases array if files processing failed
                    if 'test_cases' in doc['test_data'] and isinstance(doc['test_data']['test_cases'], list):
                        # Handle the test_cases array structure
                        test_cases_list = doc['test_data']['test_cases']
                        logger.info(f"Found test_cases list with {len(test_cases_list)} items")
                        
                        # Convert the test_cases structure to the expected format
                        converted_test_cases = []
                        for tc in test_cases_list:
                            if isinstance(tc, dict) and 'content' in tc:
                                # Parse the content string
                                content = tc.get('content', '')
                                if content and isinstance(content, str):
                                    # Try to parse this content as a test case
                                    from utils.file_handler import parse_traditional_format
                                    parsed = parse_traditional_format(content)
                                    if parsed:
                                        converted_test_cases.extend(parsed)
                                    else:
                                        # If parsing fails, create a basic test case
                                        test_case = {
                                            'Title': tc.get('test_case_id', 'Unknown'),
                                            'Scenario': 'Scenario extracted from content',
                                            'Steps': 'Steps extracted from content',
                                            'Expected Result': 'Expected result extracted from content',
                                            'Status': tc.get('status', 'Not Tested')
                                        }
                                        converted_test_cases.append(test_case)
                        
                        if converted_test_cases:
                            response_data['test_data'] = converted_test_cases
                            logger.info(f"Successfully converted {len(converted_test_cases)} test cases from test_cases structure")
                            
                    elif isinstance(doc['test_data'], list):
                        # This is a shared view document with test data array
                        response_data['test_data'] = doc['test_data']
            
        response = jsonify(response_data)
        
        # Add cache control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
    except Exception as e:
        logger.error(f"Error retrieving shared status: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Analytics tracking endpoints
@app.route('/api/analytics/track', methods=['POST'])
def track_analytics():
    """Track user events and interactions"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get client information
        event_data = {
            "event_type": data.get("event_type"),
            "event_data": data.get("event_data", {}),
            "session_id": data.get("session_id"),
            "user_agent": request.headers.get('User-Agent'),
            "ip_address": request.remote_addr,
            "source_type": data.get("source_type"),
            "test_case_types": data.get("test_case_types", []),
            "item_count": data.get("item_count", 0)
        }

        # If authenticated, attach user_id for RBAC-aware analytics
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(' ')[1]
                mh = MongoHandler()
                verification = mh.verify_jwt_token(token)
                if verification and verification.get('success'):
                    event_user = verification['user']
                    event_data['user_id'] = event_user.get('id')
                    event_data['user_role'] = event_user.get('role')
            except Exception:
                pass
        
        mongo_handler = MongoHandler()
        success = mongo_handler.track_event(event_data)
        
        if success:
            return jsonify({'success': True, 'message': 'Event tracked successfully'})
        else:
            return jsonify({'error': 'Failed to track event'}), 500
            
    except Exception as e:
        logger.error(f"Error tracking analytics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/session', methods=['POST'])
def track_session():
    """Track user session and page visits"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get client information
        session_data = {
            "session_id": data.get("session_id"),
            "user_agent": request.headers.get('User-Agent'),
            "ip_address": request.remote_addr,
            "referrer": request.headers.get('Referer'),
            "page_visited": data.get("page_visited"),
            "country": data.get("country"),
            "city": data.get("city")
        }

        # Attach user if available
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(' ')[1]
                mh = MongoHandler()
                verification = mh.verify_jwt_token(token)
                if verification and verification.get('success'):
                    user = verification['user']
                    session_data['user_id'] = user.get('id')
                    session_data['user_role'] = user.get('role')
            except Exception:
                pass
        
        mongo_handler = MongoHandler()
        success = mongo_handler.track_user_session(session_data)
        
        if success:
            return jsonify({'success': True, 'message': 'Session tracked successfully'})
        else:
            return jsonify({'error': 'Failed to track session'}), 500
            
    except Exception as e:
        logger.error(f"Error tracking session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/summary', methods=['GET'])
def get_analytics_summary():
    """Get analytics summary with RBAC: admin gets system-wide, users get their own."""
    try:
        # Verify auth token
        auth_header = request.headers.get('Authorization')
        mh = MongoHandler()
        current_user = None
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token = auth_header.split(' ')[1]
                user_info = mh.verify_jwt_token(token)
                if user_info and user_info.get('success'):
                    current_user = user_info['user']
            except Exception:
                pass

        if not current_user:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401

        # Parse date filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Parse other filters
        source_type = request.args.get('source_type')
        
        # Fallback to days parameter if no date range provided
        days = request.args.get('days', 30, type=int)
        
        mongo_handler = mh
        
        if current_user.get('role') == 'admin':
            # Admin: full system analytics
            summary = mongo_handler.get_analytics_summary(
                start_date=start_date,
                end_date=end_date,
                days=days,
                source_type=source_type
            )
        else:
            # Regular user: same summary schema but filtered by user_id
            summary = mongo_handler.get_analytics_summary(
                start_date=start_date,
                end_date=end_date,
                days=days,
                source_type=source_type,
                user_id=current_user.get('id')
            )
        
        if summary:
            return jsonify({'success': True, 'data': summary})
        else:
            return jsonify({'error': 'Failed to get analytics summary'}), 500
            
    except Exception as e:
        logger.error(f"Error getting analytics summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/detailed', methods=['GET'])
def get_detailed_analytics():
    """Get detailed analytics with filters. Admin only."""
    try:
        # RBAC: admin only
        auth_header = request.headers.get('Authorization')
        if not (auth_header and auth_header.startswith('Bearer ')):
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        mh = MongoHandler()
        token = auth_header.split(' ')[1]
        verification = mh.verify_jwt_token(token)
        if not verification or not verification.get('success') or verification['user'].get('role') != 'admin':
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        filters = {}
        
        # Parse date filters and normalize to full-day bounds
        start_date = request.args.get('start_date')
        if start_date:
            try:
                # Support plain YYYY-MM-DD by anchoring to start of day
                if len(start_date) == 10:
                    filters['start_date'] = datetime.strptime(start_date, '%Y-%m-%d')
                else:
                    filters['start_date'] = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except Exception:
                filters['start_date'] = datetime.strptime(start_date[:10], '%Y-%m-%d')
        
        end_date = request.args.get('end_date')
        if end_date:
            try:
                if len(end_date) == 10:
                    # Make end inclusive by extending to end of day
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1) - timedelta(milliseconds=1)
                    filters['end_date'] = end_dt
                else:
                    filters['end_date'] = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except Exception:
                end_dt = datetime.strptime(end_date[:10], '%Y-%m-%d') + timedelta(days=1) - timedelta(milliseconds=1)
                filters['end_date'] = end_dt
        
        # Parse other filters
        event_type = request.args.get('event_type')
        if event_type:
            filters['event_type'] = event_type
        
        source_type = request.args.get('source_type')
        if source_type:
            filters['source_type'] = source_type
        
        mongo_handler = MongoHandler()
        events = mongo_handler.get_detailed_analytics(filters)
        
        if events is not None:
            return jsonify({'success': True, 'data': events})
        else:
            return jsonify({'error': 'Failed to get detailed analytics'}), 500
            
    except Exception as e:
        logger.error(f"Error getting detailed analytics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-cases/recent', methods=['GET'])
def get_recent_test_cases():
    """Get recent test cases for the authenticated user"""
    try:
        # Verify auth token
        auth_header = request.headers.get('Authorization')
        if not (auth_header and auth_header.startswith('Bearer ')):
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        mh = MongoHandler()
        token = auth_header.split(' ')[1]
        user_info = mh.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get recent test cases for this user
        test_cases = mh.get_user_test_cases(user_id, limit=10)
        
        if test_cases:
            # Convert ObjectId to string for JSON serialization
            for tc in test_cases:
                if '_id' in tc:
                    tc['_id'] = str(tc['_id'])
                if 'created_at' in tc:
                    tc['created_at'] = tc['created_at'].isoformat()
            
            return jsonify({
                'success': True,
                'test_cases': test_cases
            })
        else:
            return jsonify({
                'success': True,
                'test_cases': []
            })
            
    except Exception as e:
        logger.error(f"Error getting recent test cases: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to retrieve test cases'}), 500

@app.route('/api/analytics/errors', methods=['GET'])
def get_error_analytics():
    """Get error analytics from MongoDB (admin only)"""
    try:
        # RBAC: admin only
        auth_header = request.headers.get('Authorization')
        if not (auth_header and auth_header.startswith('Bearer ')):
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        mh = MongoHandler()
        token = auth_header.split(' ')[1]
        verification = mh.verify_jwt_token(token)
        if not verification or not verification.get('success') or verification['user'].get('role') != 'admin':
            return jsonify({'success': False, 'message': 'Forbidden'}), 403
        
        from utils.error_logger import error_logger
        
        # Get query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        level = request.args.get('level')  # Optional filter by log level
        
        # Calculate days from date range if provided
        if start_date and end_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                # Calculate days difference
                days_diff = (end_datetime - start_datetime).days
                # Use the larger of the calculated days or 30 as fallback
                days = max(days_diff, 30)
            except Exception as e:
                logger.warning(f"Error parsing date range, using default 30 days: {e}")
                days = 30
        else:
            # Fallback to days parameter if no date range provided
            days = int(request.args.get('days', 30))
        
        # Get error summary
        error_summary = error_logger.get_error_summary(
            days=days, 
            level=level,
            start_date=start_date,
            end_date=end_date
        )
        
        if 'error' in error_summary:
            return jsonify({'error': error_summary['error']}), 500
        
        return jsonify({'success': True, 'data': error_summary})
        
    except Exception as e:
        logger.error(f"Error getting error analytics: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/mongo-document/<url_key>', methods=['GET'])
def get_mongo_document(url_key):
    """Get MongoDB document content directly"""
    try:
        if not url_key:
            return jsonify({'error': 'Missing URL key parameter'}), 400
            
        logger.info(f"Retrieving MongoDB document for URL key: {url_key}")
        mongo_handler = MongoHandler()
        
        # Try to get the document by url_key or _id (for short tokens)
        doc = mongo_handler.collection.find_one({"url_key": url_key})
        if not doc:
            doc = mongo_handler.collection.find_one({"_id": url_key})
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
            
        # Convert ObjectId to string for JSON serialization
        if '_id' in doc:
            doc['_id'] = str(doc['_id'])
            
        # Build response
        response_data = {
            'success': True,
            'document': doc
        }
        
        response = jsonify(response_data)
        
        # Add cache control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
    except Exception as e:
        logger.error(f"Error retrieving MongoDB document: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/notify-status-change', methods=['GET'])
def notify_status_change():
    try:
        url_key = request.args.get('key')
        test_case_id = request.args.get('testCaseId')
        status = request.args.get('status')
        
        if not url_key:
            return jsonify({'error': 'Missing URL key parameter'}), 400
            
        # Log the notification
        logger.info(f"Received status change notification for key={url_key}, testCaseId={test_case_id}, status={status}")
        
        # Update a special flag in MongoDB to indicate status has changed
        # This can be used to trigger immediate sync in other views
        mongo_handler.collection.update_one(
            {"url_key": url_key},
            {
                "$set": {
                    "status_updated_at": datetime.utcnow(),
                    "last_status_change": {
                        "test_case_id": test_case_id,
                        "status": status,
                        "timestamp": datetime.utcnow()
                    }
                }
            }
        )
        
        # Return success with cache control headers
        response = jsonify({
            'success': True,
            'message': 'Status change notification received'
        })
        
        # Add cache control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
        return response
    except Exception as e:
        logger.error(f"Error processing status change notification: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/force-sync', methods=['GET'])
def debug_force_sync():
    """Debug endpoint to force sync of status values between views"""
    try:
        url_key = request.args.get('key')
        if not url_key:
            return jsonify({'error': 'Missing URL key parameter'}), 400
            
        # logger.info(f"DEBUG: Forcing status sync for URL key: {url_key}")
        mongo_handler = MongoHandler()
        
        # Get the document
        doc = mongo_handler.collection.find_one({"url_key": url_key})
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
            
        # # Debug info about the document
        # logger.info(f"DEBUG: Document _id: {doc.get('_id')}")
        # logger.info(f"DEBUG: Document created_at: {doc.get('created_at')}")
        # logger.info(f"DEBUG: Document status dict: {doc.get('status', {})}")
        
        # Check if it's a shared view or main view
        is_shared_view = isinstance(doc.get('test_data'), list)
        # logger.info(f"DEBUG: Document is shared view: {is_shared_view}")
        
        # Get current status values from the document
        updated_status = {}
        
        if is_shared_view:
            # Shared view - test_data is a list of test case objects
            for i, tc in enumerate(doc['test_data']):
                title = tc.get('Title', '')
                status = tc.get('Status', '')
                if title:
                    # logger.info(f"DEBUG: Shared view TC[{i}]: {title} = {status}")
                    updated_status[title] = status
                    
            # Update all status values in the document too
            # Directly update the status field of each test case in the list
            for i, tc in enumerate(doc['test_data']):
                title = tc.get('Title', '')
                if title in updated_status:
                    # logger.info(f"DEBUG: Updating TC[{i}] status: {title} = {updated_status[title]}")
                    mongo_handler.collection.update_one(
                        {"url_key": url_key},
                        {"$set": {f"test_data.{i}.Status": updated_status[title]}}
                    )
        else:
            # Main view - test_data.test_cases is a list of test case objects
            if 'test_data' in doc and 'test_cases' in doc['test_data']:
                for i, tc in enumerate(doc['test_data']['test_cases']):
                    title = tc.get('Title', tc.get('title', ''))
                    status = tc.get('Status', tc.get('status', ''))
                    if title:
                        # logger.info(f"DEBUG: Main view TC[{i}]: {title} = {status}")
                        updated_status[title] = status
                        
                # Update all status values in the document too
                # Directly update the status field of each test case in the list
                for i, tc in enumerate(doc['test_data']['test_cases']):
                    title = tc.get('Title', tc.get('title', ''))
                    if title in updated_status:
                        # logger.info(f"DEBUG: Updating TC[{i}] status: {title} = {updated_status[title]}")
                        mongo_handler.collection.update_one(
                            {"url_key": url_key},
                            {"$set": {f"test_data.test_cases.{i}.status": updated_status[title]}}
                        )
                    
        # Update the central status dictionary
        if updated_status:
            # logger.info(f"DEBUG: Updating status dictionary with {len(updated_status)} values")
            mongo_handler.collection.update_one(
                {"url_key": url_key},
                {"$set": {"status": updated_status}}
            )
            
        # Add a flag to indicate the sync was forced
        mongo_handler.collection.update_one(
            {"url_key": url_key},
            {"$set": {
                "status_force_synced_at": datetime.now(),
                "status_force_sync_count": doc.get("status_force_sync_count", 0) + 1
            }}
        )
        
        return jsonify({
            'success': True,
            'message': 'Status values forced to sync',
            'status_values': updated_status,
            'is_shared_view': is_shared_view
        })
    except Exception as e:
        logger.error(f"Error during force sync: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint for cloud deployment"""
    try:
        # Check MongoDB connection
        mongo_status = "OK"
        try:
            if mongo_handler:
                # Try a simple operation
                mongo_handler.collection.find_one()
            else:
                mongo_status = "Not initialized"
        except Exception as e:
            mongo_status = f"Error: {str(e)}"
        
        # Check file system
        fs_status = "OK"
        try:
            base_dir = os.path.dirname(__file__)
            generated_dir = os.path.join(base_dir, 'tests', 'generated')
            if not os.path.exists(generated_dir):
                os.makedirs(generated_dir, exist_ok=True)
        except Exception as e:
            fs_status = f"Error: {str(e)}"
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'mongodb': mongo_status,
            'filesystem': fs_status,
            'environment': 'production' if os.getenv('RENDER') else 'development'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/verify-api-key')
def verify_api_key():
    """
    Endpoint to verify if the OpenAI API key is configured correctly
    """
    import openai
    import json
    
    try:
        # Get API key using lazy loading
        from config.settings import OPENAI_API_KEY
        # Check if API key exists
        if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_api_key_here" or OPENAI_API_KEY == "missing_api_key":
            return jsonify({
                'status': 'error',
                'message': 'OpenAI API key is missing or invalid',
                'details': 'Please configure a valid API key in your .env file. The API key should start with "sk-"'
            }), 400
            
        # Try to initialize the client
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Test the API key with a simple models list request
        try:
            response = client.models.list()
            
            # Check if we get a valid response
            if response:
                # Check if gpt-3.5-turbo or gpt-3.5-turbo models are available
                available_models = [model.id for model in response.data]
                vision_models = [model for model in available_models 
                                if model.startswith('gpt-4o') and 
                                ('vision' in model or model == 'gpt-4o' or model == 'gpt-4o-mini')]
                
                if vision_models:
                    return jsonify({
                        'status': 'success',
                        'message': 'API key is valid and vision models are available',
                        'available_vision_models': vision_models
                    })
                else:
                    return jsonify({
                        'status': 'warning',
                        'message': 'API key is valid but no vision models are available',
                        'details': 'Your OpenAI account may not have access to gpt-4o Vision models',
                        'available_models': available_models[:10]  # Just show a few to avoid too much data
                    }), 200
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Could not validate API key',
                    'details': 'API responded without error but no data was returned'
                }), 400
        except Exception as api_error:
            logger.error(f"Error validating API key: {str(api_error)}")
            return jsonify({
                'status': 'error',
                'message': f'API verification failed: {str(api_error)}',
                'details': 'There was an error verifying your API key with OpenAI'
            }), 400
            
    except Exception as e:
        error_message = str(e)
        error_details = "Check that your API key is valid and your account has sufficient credits"
        
        if "authentication" in error_message.lower() or "api key" in error_message.lower():
            error_details = "Invalid API key or authentication issue"
        elif "rate limit" in error_message.lower():
            error_details = "Rate limited by OpenAI. Try again later or check your usage tier."
        elif "quota" in error_message.lower():
            error_details = "You have exceeded your quota. Check your billing settings on OpenAI dashboard."
            
        return jsonify({
            'status': 'error',
            'message': f'API key verification failed: {error_message}',
            'details': error_details
        }), 400

@app.route('/setup-help')
def setup_help():
    """Page with setup instructions and API key verification"""
    return render_template('error.html', error_message="This page helps you configure your OpenAI API key")

@app.route('/api/shorten-url', methods=['POST'])
def shorten_url():
    try:
        url_params = request.json
        logger.info(f"Received URL params for shortening: {url_params}")
        
        if not url_params:
            logger.error("No URL parameters provided")
            return jsonify({'error': 'No URL parameters provided'}), 400

        # Check if this URL data already has a short key
        mongo_handler = MongoHandler()
        
        # Extract the key and files from the parameters
        existing_key = url_params.get('key')
        files = url_params.get('files')
        item_ids = url_params.get('item_ids')

        if not files:
            logger.error("No files parameter in URL data")
            return jsonify({'error': 'No files parameter provided'}), 400

        # If there's a key in the params and it's longer than 8 chars, 
        # check if we already have a short key for this data
        if existing_key and len(existing_key) > 8:
            logger.info(f"Found long key {existing_key}, checking for existing short URL")
            # Search for existing document with these params
            existing_doc = mongo_handler.collection.find_one({
                "url_params.files": files,
                "url_params.item_ids": item_ids,
                "type": "shortened_url"
            })
            if existing_doc:
                logger.info(f"Found existing short URL: {existing_doc['_id']}")
                return jsonify({
                    'shortened_url': f'/results?token={existing_doc["_id"]}'
                })

        # Generate new short URL
        short_key = mongo_handler.save_url_data(url_params)
        logger.info(f"Generated new short URL with key: {short_key}")
        
        return jsonify({
            'shortened_url': f'/results?token={short_key}'
        })
    except Exception as e:
        logger.error(f"Error creating shortened URL: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/verify-jira', methods=['POST'])
def verify_jira_connection():
    """Verify Jira connection and credentials"""
    try:
        data = request.json
        jira_url = data.get('jiraUrl', '').strip()
        jira_user = data.get('jiraUser', '').strip()
        jira_token = data.get('jiraToken', '').strip()
        
        if not jira_url or not jira_user or not jira_token:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Add https:// if missing
        if not jira_url.startswith(('http://', 'https://')):
            jira_url = 'https://' + jira_url
        
        # Test connection by fetching user info
        from jira.jira_client import JiraClient
        jira_client = JiraClient(jira_url, jira_user, jira_token)
        
        # Try to get current user info
        user_info = jira_client.get_current_user()
        
        if user_info:
            logger.info(f"Jira connection successful for user: {user_info.get('displayName', 'Unknown')}")
            return jsonify({
                'success': True,
                'message': 'Connection successful',
                'user': user_info.get('displayName', 'Unknown')
            })
        else:
            return jsonify({'success': False, 'error': 'Could not authenticate with Jira'}), 401
            
    except Exception as e:
        logger.error(f"Jira verification error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test-url', methods=['POST'])
def test_url():
    """Test if a URL is accessible"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
            
        try:
            # Try to validate the URL format
            parsed_url = urlparse(url)
            if not all([parsed_url.scheme, parsed_url.netloc]):
                return jsonify({'success': False, 'error': 'Invalid URL format'}), 400
                
            # Try to access the URL
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return jsonify({'success': True, 'message': 'URL is accessible'})
            else:
                return jsonify({'success': False, 'error': 'URL is not accessible'}), response.status_code
                
        except requests.RequestException as e:
            return jsonify({'success': False, 'error': 'Failed to connect to URL'}), 400
            
    except Exception as e:
        logger.error(f"URL test error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/verify-azure', methods=['POST'])
def verify_azure_connection():
    """Verify Azure DevOps connection and credentials"""
    try:
        data = request.json
        azure_url = data.get('azureUrl', '').strip()
        azure_org = data.get('azureOrg', '').strip()
        azure_project = data.get('azureProject', '').strip()
        azure_pat = data.get('azurePat', '').strip()
        
        if not azure_url or not azure_org or not azure_project or not azure_pat:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Add https:// if missing
        if not azure_url.startswith(('http://', 'https://')):
            azure_url = 'https://' + azure_url
        
        # Test connection by fetching project info
        from azure_integration.azure_client import AzureClient
        azure_client = AzureClient(azure_url, azure_org, azure_pat)
        
        # Try to get project info
        project_info = azure_client.get_project(azure_project)
        
        if project_info:
            logger.info(f"Azure connection successful for project: {project_info.get('name', 'Unknown')}")
            return jsonify({
                'success': True,
                'message': 'Connection successful',
                'project': project_info.get('name', 'Unknown')
            })
        else:
            return jsonify({'success': False, 'error': 'Could not authenticate with Azure DevOps'}), 401
            
    except Exception as e:
        logger.error(f"Azure verification error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fetch-jira-items', methods=['POST'])
def fetch_jira_items():
    """Fetch recent Jira items for suggestions"""
    try:
        data = request.json
        jira_url = data.get('jiraUrl', '').strip()
        jira_user = data.get('jiraUser', '').strip()
        jira_token = data.get('jiraToken', '').strip()
        
        if not jira_url or not jira_user or not jira_token:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Add https:// if missing
        if not jira_url.startswith(('http://', 'https://')):
            jira_url = 'https://' + jira_url
        
        from jira.jira_client import JiraClient
        jira_client = JiraClient(jira_url, jira_user, jira_token)
        
        # Fetch all issues filtered by desired statuses
        desired_statuses = [
            'To Do',
            'Ready for QA',
            'Ready for Qa',  # case/variant safety
            'Ready For QA'
        ]
        issues = jira_client.get_recent_issues(limit=None, statuses=desired_statuses)
        
        if issues:
            # Format items for suggestions
            items = []
            for issue in issues:
                items.append({
                    'id': issue.get('key', ''),
                    'title': issue.get('fields', {}).get('summary', ''),
                    'type': issue.get('fields', {}).get('issuetype', {}).get('name', 'Issue'),
                    'status': issue.get('fields', {}).get('status', {}).get('name', '')
                })
            
            logger.info(f"Fetched {len(items)} Jira items for suggestions")
            return jsonify({
                'success': True,
                'items': items
            })
        else:
            return jsonify({'success': False, 'error': 'No issues found'}), 404
            
    except Exception as e:
        logger.error(f"Error fetching Jira items: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fetch-azure-items', methods=['POST'])
def fetch_azure_items():
    """Fetch recent Azure DevOps work items for suggestions"""
    try:
        data = request.json
        logger.info(f"Received Azure data: {data}")
        
        azure_url = data.get('azureUrl', '').strip()
        azure_org = data.get('azureOrg', '').strip()
        azure_project = data.get('azureProject', '').strip()
        azure_pat = data.get('azurePat', '').strip()
        
        logger.info(f"Processed Azure fields - URL: '{azure_url}', Org: '{azure_org}', Project: '{azure_project}', PAT: {'*' * len(azure_pat) if azure_pat else 'None'}")
        
        if not azure_url or not azure_org or not azure_project or not azure_pat:
            logger.error(f"Missing Azure fields - URL: {bool(azure_url)}, Org: {bool(azure_org)}, Project: {bool(azure_project)}, PAT: {bool(azure_pat)}")
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Add https:// if missing
        if not azure_url.startswith(('http://', 'https://')):
            azure_url = 'https://' + azure_url
        
        from azure_integration.azure_client import AzureClient
        azure_client = AzureClient(azure_url, azure_org, azure_pat)
        
        # Set the project for this operation
        azure_client.azure_project = azure_project
        
        # Test project access first
        logger.info(f"Testing Azure project access: {azure_project}")
        project_info = azure_client.get_project(azure_project)
        if not project_info:
            logger.error(f"Failed to access Azure project: {azure_project}")
            return jsonify({'success': False, 'error': f'Cannot access project {azure_project}. Please check your permissions.'}), 403
        
        logger.info(f"Successfully accessed Azure project: {project_info.get('name', azure_project)}")
        
        # Fetch all work items filtered by QA-ready/reopen states
        logger.info(f"Fetching Azure work items for project: {azure_project} with QA-ready filters")
        desired_states = [
            'Ready for QA',
            'Re-open',
            'Reopened',
            'Re-opened'  # include common variants
        ]
        work_items = azure_client.get_recent_work_items(azure_project, limit=None, states=desired_states)
        logger.info(f"Retrieved {len(work_items) if work_items else 0} Azure work items")
        
        if work_items:
            # Format items for suggestions
            items = []
            for item in work_items:
                items.append({
                    'id': str(item.get('id', '')),
                    'title': item.get('fields', {}).get('System.Title', ''),
                    'type': item.get('fields', {}).get('System.WorkItemType', 'Work Item'),
                    'status': item.get('fields', {}).get('System.State', '')
                })
            
            logger.info(f"Fetched {len(items)} Azure work items for suggestions")
            return jsonify({
                'success': True,
                'items': items
            })
        else:
            return jsonify({'success': False, 'error': 'No work items found'}), 404
            
    except Exception as e:
        logger.error(f"Error fetching Azure items: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export-excel', methods=['POST'])
def export_excel():
    """Export test cases to Excel file"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        test_cases = data.get('test_cases', [])
        status_values = data.get('status_values', {})
        source_type = data.get('source_type', 'Unknown')
        item_ids = data.get('item_ids', [])
        
        if not test_cases:
            return jsonify({'error': 'No test cases provided'}), 400
        
        logger.info(f"Exporting {len(test_cases)} test cases to Excel for {source_type}")
        
        # Create Excel file
        from utils.file_handler import create_excel_report
        excel_data = create_excel_report(test_cases, status_values, source_type, item_ids)
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"test_cases_{source_type}_{timestamp}.xlsx"
        
        # Create response
        from flask import Response
        response = Response(
            excel_data,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting to Excel: {str(e)}")
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

# Authentication API routes
@app.route('/api/auth/signup', methods=['POST'])
def signup_api():
    """Handle user registration"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        # Validation
        if not name or len(name) < 2:
            return jsonify({'success': False, 'message': 'Name must be at least 2 characters long'}), 400
        
        if not email or '@' not in email:
            return jsonify({'success': False, 'message': 'Please provide a valid email address'}), 400
        
        if not password or len(password) < 8:
            return jsonify({'success': False, 'message': 'Password must be at least 8 characters long'}), 400
        
        # Create user
        mongo_handler = MongoHandler()
        result = mongo_handler.create_user(email, password, name)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Account created successfully! Please sign in.'
            })
        else:
            return jsonify({'success': False, 'message': result['message']}), 400
            
    except Exception as e:
        logger.error(f"Error in signup API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred during registration'}), 500

@app.route('/api/auth/signin', methods=['POST'])
def signin_api():
    """Handle user login"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        # Validation
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400
        
        # Authenticate user
        mongo_handler = MongoHandler()
        result = mongo_handler.authenticate_user(email, password)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Login successful!',
                'token': result['token'],
                'user': result['user']
            })
        else:
            return jsonify({'success': False, 'message': result['message']}), 401
            
    except Exception as e:
        logger.error(f"Error in signin API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred during login'}), 500

@app.route('/api/auth/dashboard', methods=['GET'])
def dashboard_api():
    """Get user dashboard data"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get user's test cases
        test_cases = mongo_handler.get_user_test_cases(user_id)
        
        # Calculate statistics with robust datetime handling
        total_count = len(test_cases)
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        this_month_count = 0
        last_generated = 'Never'
        
        if test_cases:
            for tc in test_cases:
                created_at = tc.get('created_at')
                if created_at:
                    try:
                        # Handle both string and datetime objects
                        if isinstance(created_at, str):
                            # Try parsing as ISO format
                            parsed_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        else:
                            # It's already a datetime object
                            parsed_date = created_at
                        
                        # Check if it's from current month/year
                        if parsed_date.month == current_month and parsed_date.year == current_year:
                            this_month_count += 1
                            
                    except Exception as e:
                        logger.warning(f"Failed to parse date for test case {tc.get('_id')}: {str(e)}")
                        continue
            
            # Find the latest test case
            try:
                latest = max(test_cases, key=lambda x: x.get('created_at', datetime.min))
                if latest.get('created_at'):
                    created_at = latest['created_at']
                    if isinstance(created_at, str):
                        last_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        last_date = created_at
                    last_generated = last_date.strftime('%B %d, %Y')
            except Exception as e:
                logger.warning(f"Failed to determine latest test case: {str(e)}")
                last_generated = 'Unknown'
        
        stats = {
            'total': total_count,
            'this_month': this_month_count,
            'last_generated': last_generated
        }
        
        return jsonify({
            'success': True,
            'test_cases': test_cases,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error in dashboard API: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'An error occurred while loading dashboard'}), 500

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password_api():
    """Handle password reset request"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        email = data.get('email', '').strip()
        
        # Validation
        if not email or '@' not in email:
            return jsonify({'success': False, 'message': 'Please provide a valid email address'}), 400
        
        # Check if user exists
        mongo_handler = MongoHandler()
        user = mongo_handler.users_collection.find_one({'email': email})
        
        if not user:
            # Don't reveal if user exists or not for security
            return jsonify({
                'success': True,
                'message': 'If an account with that email exists, a password reset link has been sent.'
            })
        
        # Generate a secure reset token
        token_result = mongo_handler.create_password_reset_token(email)
        
        if not token_result['success']:
            logger.error(f"Failed to create reset token for {email}: {token_result.get('message', 'Unknown error')}")
            return jsonify({
                'success': True,
                'message': 'If an account with that email exists, a password reset link has been sent.'
            })
        
        # Send password reset email
        try:
            from utils.email_notifier import send_password_reset_email
            
            email_sent = send_password_reset_email(
                email=email,
                reset_token=token_result['token'],
                expires_at=token_result['expires_at']
            )
            
            if email_sent:
                logger.info(f"Password reset email sent successfully to: {email}")
            else:
                logger.error(f"Failed to send password reset email to: {email}")
                
        except Exception as email_error:
            logger.error(f"Error sending password reset email to {email}: {str(email_error)}")
            # Don't fail the request if email sending fails
        
        logger.info(f"Password reset requested for email: {email}")
        
        return jsonify({
            'success': True,
            'message': 'If an account with that email exists, a password reset link has been sent. Please check your email.'
        })
            
    except Exception as e:
        logger.error(f"Error in reset password API: {str(e)}")
        capture_exception(e, {"endpoint": "/api/auth/reset-password", "email": data.get('email', '') if data else ''})
        return jsonify({'success': False, 'message': 'An error occurred during password reset'}), 500

@app.route('/api/auth/reset-password-confirm', methods=['POST'])
def reset_password_confirm_api():
    """Handle password reset confirmation"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        token = data.get('token', '').strip()
        new_password = data.get('new_password', '').strip()
        confirm_password = data.get('confirm_password', '').strip()
        
        # Validation
        if not token:
            return jsonify({'success': False, 'message': 'Reset token is required'}), 400
        
        if not new_password:
            return jsonify({'success': False, 'message': 'New password is required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match'}), 400
        
        # Use the reset token to change password
        mongo_handler = MongoHandler()
        result = mongo_handler.use_password_reset_token(token, new_password)
        
        if result['success']:
            logger.info(f"Password reset successfully completed for token: {token[:10]}...")
            return jsonify({
                'success': True,
                'message': 'Password reset successfully. You can now sign in with your new password.'
            })
        else:
            logger.warning(f"Password reset failed for token: {token[:10]}... - {result.get('message', 'Unknown error')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to reset password')
            }), 400
            
    except Exception as e:
        logger.error(f"Error in reset password confirm API: {str(e)}")
        capture_exception(e, {"endpoint": "/api/auth/reset-password-confirm", "token": data.get('token', '')[:10] if data else ''})
        return jsonify({'success': False, 'message': 'An error occurred during password reset'}), 500

# Admin API endpoints
@app.route('/api/auth/system-overview', methods=['GET'])
def system_overview_api():
    """Get system overview (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get system overview
        system_overview = mongo_handler.get_system_overview(user_id)
        
        if system_overview['success']:
            return jsonify(system_overview)
        else:
            return jsonify({'success': False, 'message': system_overview['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in system overview API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while loading system overview'}), 500

@app.route('/api/auth/recent-users', methods=['GET'])
def recent_users_api():
    """Get recent users (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get recent users
        users = mongo_handler.get_all_users(user_id)
        
        if users['success']:
            # Return only first 10 users for recent users
            recent_users = users['users'][:10] if 'users' in users else []
            return jsonify({
                'success': True,
                'users': recent_users
            })
        else:
            return jsonify({'success': False, 'message': users['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in recent users API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while loading recent users'}), 500

@app.route('/api/auth/all-users', methods=['GET'])
def all_users_api():
    """Get all users with pagination (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get pagination parameters
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        # Get all users
        users = mongo_handler.get_all_users_paginated(user_id, page, per_page)
        
        if users['success']:
            return jsonify(users)
        else:
            return jsonify({'success': False, 'message': users['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in all users API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while loading users'}), 500

@app.route('/api/auth/system-health', methods=['GET'])
def system_health_api():
    """Get system health status (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get system health
        health = mongo_handler.get_system_health(user_id)
        
        if health['success']:
            return jsonify(health)
        else:
            return jsonify({'success': False, 'message': health['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in system health API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while checking system health'}), 500

@app.route('/api/auth/user-analytics', methods=['GET'])
def user_analytics_api():
    """Get detailed user analytics (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get user analytics
        analytics = mongo_handler.get_detailed_user_analytics(user_id)
        
        if analytics['success']:
            return jsonify(analytics)
        else:
            return jsonify({'success': False, 'message': analytics['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in user analytics API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while loading user analytics'}), 500

@app.route('/api/auth/create-user', methods=['POST'])
def create_user_api():
    """Create a new user (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get user data from request
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Create user
        result = mongo_handler.create_user_by_admin(user_id, data)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': result['message']}), 400
            
    except Exception as e:
        logger.error(f"Error in create user API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while creating user'}), 500

@app.route('/api/auth/export-data', methods=['GET'])
def export_data_api():
    """Export system data (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Export data
        export_result = mongo_handler.export_system_data(user_id)
        
        if export_result['success']:
            from flask import Response
            from bson import json_util
            # Use BSON json_util to safely serialize datetime and ObjectId types
            payload = json_util.dumps(export_result['data'], indent=2)
            return Response(
                payload,
                mimetype='application/json',
                headers={
                    'Content-Disposition': f'attachment; filename=system-export-{datetime.now().strftime("%Y%m%d")}.json'
                }
            )
        else:
            return jsonify({'success': False, 'message': export_result['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in export data API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while exporting data'}), 500

@app.route('/api/auth/system-logs', methods=['GET'])
def system_logs_api():
    """Get system logs (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get system logs
        logs = mongo_handler.get_system_logs(user_id)
        
        if logs['success']:
            return jsonify(logs)
        else:
            return jsonify({'success': False, 'message': logs['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in system logs API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while loading system logs'}), 500

@app.route('/api/auth/backup-system', methods=['POST'])
def backup_system_api():
    """Create system backup (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Create backup
        backup_result = mongo_handler.create_system_backup(user_id)
        
        if backup_result['success']:
            return jsonify(backup_result)
        else:
            return jsonify({'success': False, 'message': backup_result['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in backup system API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while creating backup'}), 500

@app.route('/api/auth/system-settings', methods=['POST'])
def system_settings_api():
    """Update system settings (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        user_id = user_info['user']['id']
        
        # Get settings data from request
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Update settings
        result = mongo_handler.update_system_settings(user_id, data)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': result['message']}), 400
            
    except Exception as e:
        logger.error(f"Error in system settings API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while updating settings'}), 500

@app.route('/api/auth/user-details/<user_id>', methods=['GET'])
def user_details_api(user_id):
    """Get user details (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        admin_user_id = user_info['user']['id']
        
        # Get user details
        result = mongo_handler.get_user_details(admin_user_id, user_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': result['message']}), 403
            
    except Exception as e:
        logger.error(f"Error in user details API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while loading user details'}), 500

@app.route('/api/auth/update-user/<user_id>', methods=['PUT'])
def update_user_api(user_id):
    """Update user (admin only)"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authorization token required'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Verify token and get user info
        mongo_handler = MongoHandler()
        user_info = mongo_handler.verify_jwt_token(token)
        
        if not user_info or not user_info.get('success'):
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        admin_user_id = user_info['user']['id']
        
        # Get user data from request
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        # Update user
        result = mongo_handler.update_user_by_admin(admin_user_id, user_id, data)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': result['message']}), 400
            
    except Exception as e:
        logger.error(f"Error in update user API: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while updating user'}), 500

# Error handlers for custom error pages
@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 Not Found errors"""
    logger.warning(f"404 error: {request.url}")
    # Return JSON for API endpoints, HTML for regular pages
    if request.path.startswith('/api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    return render_template('error.html', error_message="The page you're looking for doesn't exist. Please check the URL and try again."), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 Internal Server errors"""
    logger.error(f"500 error: {str(error)}")
    # Return JSON for API endpoints, HTML for regular pages
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error occurred'}), 500
    return render_template('error.html', error_message="Something went wrong on our end. Please try again later."), 500

@app.errorhandler(403)
def forbidden_error(error):
    """Handle 403 Forbidden errors"""
    logger.warning(f"403 error: {request.url}")
    # Return JSON for API endpoints, HTML for regular pages
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Access forbidden'}), 403
    return render_template('error.html', error_message="You don't have permission to access this resource."), 403

@app.errorhandler(400)
def bad_request_error(error):
    """Handle 400 Bad Request errors"""
    logger.warning(f"400 error: {request.url}")
    # Return JSON for API endpoints, HTML for regular pages
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Bad request'}), 400
    return render_template('error.html', error_message="The request was invalid. Please check your input and try again."), 400

@app.after_request
def add_global_no_cache_headers(response):
    try:
        if 'Cache-Control' not in response.headers:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        if 'Pragma' not in response.headers:
            response.headers["Pragma"] = "no-cache"
        if 'Expires' not in response.headers:
            response.headers["Expires"] = "0"
    except Exception:
        # Fail-safe: never break the response pipeline due to header issues
        pass
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=5008)
