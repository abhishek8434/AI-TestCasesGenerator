# Import error logging utilities for error tracking
from utils.error_logger import capture_exception, capture_message, set_tag, set_context

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
    return base_configs.get(test_type, {})

def generate_test_case(description: str, summary: str = "", selected_types: List[str] = None, source_type: str = None, url: str = None) -> Optional[str]:
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

        # # Prepare the prompt based on source type
        # base_prompt = f"""
        # Use this format for each test case:

        # Title: {config['prefix']}_[Number]_[Brief_Title]
        # Scenario: [Detailed scenario description]
        # Steps to reproduce:
        # 1. [Step 1]
        # 2. [Step 2]
        # ...
        # Expected Result: [What should happen]
        # Actual Result: [To be filled during execution]
        # Priority: [High/Medium/Low]
        
        # Ensure each test case covers a unique scenario and adds value.
        # """

        # if source_type == 'url':
        #     prompt = f"""
        #     Website URL: {url}
        #     Content Description: {description}

        #     Generate test cases for {config['description']} (up to {config['max_count']} maximum).
        #     Focus on testing the website's functionality, user interface, and user experience.
            
        #     IMPORTANT: Analyze the content thoroughly and generate the appropriate number of relevant test cases.
        #     Consider the complexity and scope of the content - generate only what's truly needed.
        #     Do not force additional test cases just to reach the maximum.
            
        #     For each test case:
        #     1. Use the prefix {config['prefix']}
        #     2. Focus exclusively on {test_type} scenarios for web testing
        #     3. Include detailed steps that a QA engineer would follow
        #     4. Specify expected results for web interactions
        #     5. Consider cross-browser compatibility if relevant
        #     6. Include mobile responsiveness testing if applicable
        #     7. Do not mix with other test types
        #     8. Ensure each test case covers a unique scenario

        #     {base_prompt}
        #     """
        # else:
        #     prompt = f"""
        #     Task Title: {summary}
        #     Task Description: {description}

        #     Generate test cases for {config['description']} (up to {config['max_count']} maximum).
            
        #     IMPORTANT: Analyze the content thoroughly and generate the appropriate number of relevant test cases.
        #     Consider the complexity and scope of the content - generate only what's truly needed.
        #     Do not force additional test cases just to reach the maximum.
            
        #     ANALYSIS REQUIREMENTS:
        #     - Read and analyze the task description completely
        #     - Identify all functional components mentioned
        #     - Consider all possible user interactions
        #     - Think about edge cases and boundary conditions
        #     - Identify potential failure scenarios
        #     - Consider different user roles and permissions if applicable
            
        #     For each test case:
        #     1. Use the prefix {config['prefix']}
        #     2. Focus exclusively on {test_type} scenarios
        #     3. Include detailed steps
        #     4. Specify expected results
        #     5. Do not mix with other test types
        #     6. Ensure each test case tests a unique scenario

        #     {base_prompt}
        #     """


        # Prepare the prompt based on source type
        base_prompt = f"""
        You are an expert QA engineer. Your task is to create **clear, detailed, and professional test cases**.

        ✅ STRICT FORMAT for each test case:

        Title: {config['prefix']}_[SequentialNumber]_[Meaningful_Brief_Title]
        Scenario: [One or two lines describing the intent of the test]
        Preconditions: [State assumptions, setup, or required data before execution]
        Steps to Reproduce:
        1. [Step 1 in action-oriented language]
        2. [Step 2]
        ...
        Expected Result: [Clear, testable outcome of the steps]
        Actual Result: [Leave as 'To be filled during execution']
        Priority: [High / Medium / Low]
        Test Data: [If applicable – specify input values, files, or environment details]

        ⚡ RULES:
        - Each test case must cover a **unique and valuable scenario**.
        - Steps must be **clear, actionable, and written like instructions to a QA engineer**.
        - Expected Results must be **specific and measurable** (not vague like “It should work”).
        - Do NOT duplicate scenarios.
        - Do NOT mix with other test types.
        - Use professional QA terminology.
        """

        if source_type == 'url':
            prompt = f"""
            Website URL: {url}
            Content Description: {description}

            Generate **up to {config['max_count']} test cases** for {config['description']}.

            ⚡ ANALYSIS REQUIREMENTS:
            - Carefully review the website’s structure and functionality
            - Think about real-world user workflows and how they may fail
            - Consider UI, UX, and interaction edge cases
            - Include cross-browser compatibility (Chrome, Firefox, Safari, Edge)
            - Consider mobile responsiveness (desktop vs. mobile behavior)

            ⚡ TEST CASE REQUIREMENTS:
            1. Prefix all test case titles with {config['prefix']}
            2. Focus **only** on {test_type} test scenarios for web testing
            3. Write **detailed, step-by-step instructions** that can be executed by QA
            4. Specify **exact expected results** for every step or final outcome
            5. Ensure scenarios are **unique and non-overlapping**
            6. Include both **happy paths and edge cases**
            7. Add **test data** where necessary

            {base_prompt}
            """
        else:
            prompt = f"""
            Task Title: {summary}
            Task Description: {description}

            Generate **up to {config['max_count']} test cases** for {config['description']}.

            ⚡ ANALYSIS REQUIREMENTS:
            - Carefully analyze the task description
            - Identify **all functional components and user actions**
            - Think about positive, negative, and edge case scenarios
            - Consider different **user roles, permissions, and data inputs**
            - Anticipate possible **failure points** or boundary conditions

            ⚡ TEST CASE REQUIREMENTS:
            1. Prefix all test case titles with {config['prefix']}
            2. Focus **only** on {test_type} scenarios
            3. Write **step-by-step reproducible instructions**
            4. Provide **clear and measurable expected results**
            5. Ensure each case is **unique and does not overlap**
            6. Include **test data** where relevant
            7. Include **priority level** for execution planning

            {base_prompt}
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
                    "content": f"You are a senior QA engineer. Generate the appropriate number of {test_type} test cases (up to {config['max_count']} maximum) by analyzing the content complexity and generating only what's truly needed. Use {config['prefix']} as the prefix. Focus on quality and relevance over quantity."
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
            # Capture error in MongoDB
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