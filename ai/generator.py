# Initialize Sentry for AI module
from utils.sentry_config import init_sentry, capture_exception, capture_message, set_tag, set_context

# Initialize Sentry for the AI generator
init_sentry("ai-test-case-generator-ai")

from langchain_openai import ChatOpenAI
from langchain.callbacks.tracers.langchain import LangChainTracer
import os
import logging
from typing import Optional, List, Dict, Any

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

def get_test_type_config(test_type: str) -> dict:
    """Get the configuration for a specific test type"""
    base_configs = {
        "dashboard_functional": {
            "prefix": "TC_FUNC",
            "description": "functional test cases focusing on valid inputs and expected behaviors",
            "count": 20
        },
        "dashboard_negative": {
            "prefix": "TC_NEG",
            "description": "negative test cases focusing on invalid inputs, error handling, and edge cases",
            "count": 20
        },
        "dashboard_ui": {
            "prefix": "TC_UI",
            "description": "UI test cases focusing on visual elements and layout",
            "count": 15
        },
        "dashboard_ux": {
            "prefix": "TC_UX",
            "description": "user experience test cases focusing on user interaction and workflow",
            "count": 15
        },
        "dashboard_compatibility": {
            "prefix": "TC_COMPAT",
            "description": "compatibility test cases across different browsers and platforms",
            "count": 15
        },
        "dashboard_performance": {
            "prefix": "TC_PERF",
            "description": "performance test cases focusing on load times and responsiveness",
            "count": 15
        }
    }
    return base_configs.get(test_type, {})

def generate_test_case(description: str, summary: str = "", selected_types: List[str] = None) -> Optional[str]:
    """Generate test cases based on user-selected types"""
    if not description:
        logger.error("No description provided for test case generation")
        return None
        
    if not selected_types or len(selected_types) == 0:
        logger.error("No test types selected for test case generation")
        return None

    logger.info(f"Generating test cases for types: {selected_types}")
    logger.info(f"Summary: {summary}")
    logger.info(f"Description length: {len(description)} characters")
    
    all_test_cases = []
    
    for test_type in selected_types:
        logger.info(f"Starting generation for test type: {test_type}")
        config = get_test_type_config(test_type)
        if not config:
            logger.warning(f"Skipping unknown test type: {test_type}")
            continue

        prompt = f"""
        Task Title: {summary}
        Task Description: {description}

        Generate EXACTLY {config['count']} test cases for {config['description']}.
        
        For each test case:
        1. Use the prefix {config['prefix']}
        2. Focus exclusively on {test_type} scenarios
        3. Include detailed steps
        4. Specify expected results
        5. Do not mix with other test types

        Use this EXACT format for each test case:

        Title: {config['prefix']}_[Number]_[Brief_Title]
        Scenario: [Detailed scenario description]
        Steps to reproduce:
        1. [Step 1]
        2. [Step 2]
        ...
        Expected Result: [What should happen]
        Actual Result: [To be filled during execution]
        Priority: [High/Medium/Low]
        """

        try:
            # Get API key
            api_key = get_openai_api_key()
            if not api_key or api_key == "your_openai_api_key_here" or api_key == "missing_api_key":
                error_msg = "⚠️ Invalid or missing OPENAI_API_KEY in environment variables"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Create LLM instance with API key
            current_llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0.7,
                openai_api_key=api_key,
                callbacks=[tracer]
            )
            
            logger.info(f"Sending request to OpenAI for {test_type} test cases")
            response = current_llm.invoke([
                {
                    "role": "system",
                    "content": f"You are a QA engineer. Generate EXACTLY {config['count']} {test_type} test cases. Use {config['prefix']} as the prefix."
                },
                {"role": "user", "content": prompt}
            ])
            test_cases = response.content.strip()
            if test_cases:
                logger.info(f"Generated {test_type} test cases successfully")
                # Add a section header for each test type to help with parsing
                test_cases_with_header = f"TEST TYPE: {test_type}\n\n{test_cases}"
                all_test_cases.append(test_cases_with_header)
            else:
                logger.warning(f"Received empty response for {test_type} test cases")

        except Exception as e:
            logger.error(f"Error generating {test_type} test cases: {str(e)}")
            # Capture error in Sentry
            capture_exception(e, {
                "test_type": test_type,
                "config": config,
                "summary": summary,
                "description_length": len(description) if description else 0
            })
            continue
        
        logger.info(f"Completed generation for test type: {test_type}")

    if not all_test_cases:
        logger.error("Failed to generate any test cases")
        return None
        
    logger.info(f"Successfully generated test cases for {len(all_test_cases)} test types")
    return "\n\n" + "\n\n".join(all_test_cases)