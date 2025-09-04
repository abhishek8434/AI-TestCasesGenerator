# Import error logging utilities for error tracking
from utils.error_logger import capture_exception, capture_message, set_tag, set_context

from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain.callbacks.tracers.langchain import LangChainTracer
from typing import Optional, List
import base64
import requests
import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up LangSmith tracer
tracer = LangChainTracer(project_name="openai-cost-tracking")

def get_openai_api_key():
    """Get OpenAI API key from settings"""
    try:
        from config.settings import OPENAI_API_KEY
        return OPENAI_API_KEY
    except Exception as e:
        logger.error(f"Error loading OpenAI API key: {e}")
        return None

def encode_image_from_url(image_url: str) -> Optional[str]:
    """Encode image from URL to base64."""
    try:
        response = requests.get(image_url)
        return base64.b64encode(response.content).decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding image from URL: {e}")
        return None

def encode_image_from_path(image_path: str) -> Optional[str]:
    """Encode image from local path to base64."""
    try:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding image from path: {e}")
        return None

def get_test_type_config(test_type: str) -> dict:
    """Get the configuration for a specific test type"""
    # Map frontend form values to internal test type names
    form_to_internal = {
        "dashboard_functional": "dashboard_functional",
        "dashboard_negative": "dashboard_negative", 
        "dashboard_ui": "dashboard_ui",
        "dashboard_ux": "dashboard_ux",
        "dashboard_compatibility": "dashboard_compatibility",
        "dashboard_performance": "dashboard_performance",
        # Add mappings for form values
        "Functional - Positive Tests": "dashboard_functional",
        "Functional - Negative Test": "dashboard_negative",
        "UI Tests": "dashboard_ui",
        "UX Tests": "dashboard_ux",
        "Compatibility Tests": "dashboard_compatibility", 
        "Performance Tests": "dashboard_performance"
    }
    
    # Convert form value to internal name if needed
    internal_type = form_to_internal.get(test_type, test_type)
    
    base_configs = {
        "dashboard_functional": {
            "prefix": "TC_FUNC",
            "description": "functional test cases focusing on valid inputs and expected behaviors",
            "max_count": 20
        },
        "dashboard_negative": {
            "prefix": "TC_NEG",
            "description": "negative test cases focusing on invalid inputs, error handling, and edge cases",
            "max_count": 20
        },
        "dashboard_ui": {
            "prefix": "TC_UI",
            "description": "UI test cases focusing on visual elements and layout",
            "max_count": 15
        },
        "dashboard_ux": {
            "prefix": "TC_UX",
            "description": "user experience test cases focusing on user interaction and workflow",
            "max_count": 15
        },
        "dashboard_compatibility": {
            "prefix": "TC_COMPAT",
            "description": "compatibility test cases across different browsers and platforms",
            "max_count": 15
        },
        "dashboard_performance": {
            "prefix": "TC_PERF",
            "description": "performance test cases focusing on load times and responsiveness",
            "max_count": 15
        }
    }
    
    config = base_configs.get(internal_type, {})
    if not config:
        logger.warning(f"Unknown test type: {test_type} (mapped to {internal_type})")
    return config

def generate_test_case_from_image(image_path: str, selected_types: List[str] = None) -> Optional[str]:
    """Generate test cases from an image using OpenAI Vision API"""
    if not image_path:
        logger.error("No image path provided for test case generation")
        return None

    if not selected_types or len(selected_types) == 0:
        logger.error("No test types selected for test case generation")
        return None
    
    # Get API key
    api_key = get_openai_api_key()
    if not api_key or api_key == "your_openai_api_key_here" or api_key == "missing_api_key":
        error_msg = "⚠️ Invalid or missing OPENAI_API_KEY in environment variables"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Generating test cases from image for types: {selected_types}")
    logger.info(f"Image path: {image_path}")
    
    # List of models to try in order of preference
    vision_models = ["gpt-4o"]
    
    try:
        # Verify image exists
        if not os.path.exists(image_path):
            error_msg = f"Image file not found at path: {image_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        base64_image = encode_image_from_path(image_path)
        if not base64_image:
            logger.error("Failed to encode image")
            return None

        all_test_cases = []
        
        for test_type in selected_types:
            logger.info(f"Starting generation for test type: {test_type}")
            config = get_test_type_config(test_type)
            if not config:
                logger.warning(f"Skipping unknown test type: {test_type}")
                continue

            # prompt = f"""
            # Analyze the image thoroughly and generate test cases for {test_type} (up to {config['max_count']} maximum).
            # Focus ONLY on {config['description']}.
            
            # IMPORTANT: Analyze the image content thoroughly and generate the appropriate number of relevant test cases.
            # Consider the complexity and scope of the image - generate only what's truly needed.
            # Do not force additional test cases just to reach the maximum.
            
            # ANALYSIS REQUIREMENTS:
            # - Analyze all visual elements: buttons, forms, text, images, icons, layout
            # - Consider all possible user interactions visible in the image
            # - Identify edge cases and boundary conditions
            # - Consider different user roles and access levels if visible
            # - Think about potential failure scenarios and error conditions
            # - Analyze responsive design and cross-platform compatibility if applicable

            # Use this format for each test case:

            # Title: {config['prefix']}_[Number]_[Brief_Title]
            # Scenario: [Detailed scenario description covering all aspects visible in the image]
            # Steps to reproduce:
            # 1. [Step 1]
            # 2. [Step 2]
            # ...
            # Expected Result: [What should happen]
            # Priority: [High/Medium/Low]
            
            # Ensure each test case covers a unique scenario and adds value.
            # Focus on the most important and relevant test scenarios.
            # """
            prompt = f"""
            You are a senior QA engineer. Your task is to create **clear, detailed, and professional test cases** based on the provided image.

            Generate test cases for {test_type} (up to {config['max_count']} maximum).  
            Focus **exclusively** on {config['description']}.

            ⚡ GUIDELINES:
            - Analyze the image carefully before generating test cases.
            - Consider usability, workflows, and potential points of failure.
            - Only generate test cases that are **realistic, relevant, and valuable**.
            - Do not add filler cases to reach the maximum.

            🔍 ANALYSIS CHECKLIST:
            1. Identify all visible UI elements: buttons, inputs, menus, text, images, icons, layout.
            2. Consider different user interactions and workflows the image suggests.
            3. Think about role-based access or permission levels if implied.
            4. Include edge cases, error states, and unusual user behaviors.
            5. Consider platform variations (desktop, mobile, tablet) if applicable.
            6. Prioritize scenarios that impact **core functionality or user experience**.

            ✅ STRICT FORMAT for each test case:

            Title: {config['prefix']}_[SequentialNumber]_[Meaningful_Brief_Title]  
            Scenario: [One or two sentences describing the purpose of the test]  
            Preconditions: [Any setup, environment, or assumptions required before execution]  
            Steps to Reproduce:  
            1. [Step 1 in clear, action-oriented language]  
            2. [Step 2]  
            ...  
            Expected Result: [Specific, measurable expected behavior]  
            Priority: [High / Medium / Low]  
            Test Data: [If applicable – include input values, file names, sample data, etc.]  

            ⚡ RULES:
            - Every test case must be **unique and non-redundant**.  
            - Write in a way that a QA engineer can **immediately execute without assumptions**.  
            - Expected results should be **precise, not vague**.  
            - Include **positive, negative, and edge cases** where applicable.  
            - Keep the output structured and professional.

            """



            test_cases = None
            last_error = None
            
            # Try each model in sequence until one works
            for model in vision_models:
                if test_cases:
                    break  # Already succeeded with a previous model
                
                try:
                    logger.info(f"Sending request to OpenAI Vision API using model {model} for {test_type} test cases")
                    
                    # Create LLM instance with API key
                    current_llm = ChatOpenAI(
                        model=model,
                        temperature=0.7,
                        openai_api_key=api_key,
                        max_tokens=3000,
                        callbacks=[tracer]  # Add tracer for cost tracking
                    )
                    
                    response = current_llm.invoke([
                        {
                            "role": "system",
                            "content": f"You are a senior QA engineer generating test cases from the provided image. Analyze the image thoroughly and generate the appropriate number of test cases based on the image complexity. Focus on quality and relevance over quantity."
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ])
                    
                    test_cases = response.content.strip()
                    if test_cases:
                        logger.info(f"Successfully generated {test_type} test cases using model {model}")
                        # Add a section header for each test type to help with parsing
                        test_cases_with_header = f"TEST TYPE: {test_type}\n\n{test_cases}"
                        all_test_cases.append(test_cases_with_header)
                        break
                    else:
                        logger.warning(f"Received empty response for {test_type} test cases using model {model}")
                
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Error using model {model} for {test_type} test cases: {last_error}")
                    continue  # Try next model
            
            # If all models failed, log the last error and raise an exception
            if not test_cases and last_error:
                error_msg = ""
                # Provide more detailed error message for common errors
                if "model_not_found" in last_error or "invalid_request_error" in last_error:
                    error_msg = f"Error with all OpenAI models for {test_type} test cases: {last_error}"
                    logger.error(error_msg)
                    logger.error("Please check if your OpenAI account has access to gpt-4o models with vision capabilities.")
                    raise ValueError("The OpenAI model required for image processing is not available. Please check your OpenAI account access.")
                elif "authorization" in last_error.lower() or "api key" in last_error.lower():
                    error_msg = f"Authorization error for {test_type} test cases: {last_error}"
                    logger.error(error_msg)
                    logger.error("Please check your OpenAI API key in the configuration.")
                    raise ValueError("OpenAI API authorization failed. Please check your API key.")
                else:
                    error_msg = f"Error generating {test_type} test cases with all models: {last_error}"
                    logger.error(error_msg)
                    raise ValueError(f"Failed to generate test cases: {last_error}")
                
            logger.info(f"Completed generation for test type: {test_type}")

        if not all_test_cases:
            logger.error("Failed to generate any test cases")
            return None

        logger.info(f"Successfully generated test cases for {len(all_test_cases)} test types")
        return "\n\n" + "\n\n".join(all_test_cases)

    except Exception as e:
        logger.error(f"Error in generate_test_case_from_image: {str(e)}", exc_info=True)
        # Capture error in MongoDB
        capture_exception(e, {
            "image_path": image_path,
            "selected_types": selected_types,
            "vision_models": vision_models
        })
        # Re-raise the exception with the error message
        raise ValueError(f"Failed to generate test cases from image: {str(e)}")