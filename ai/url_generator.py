# Import error logging utilities for error tracking
from utils.error_logger import capture_exception, capture_message, set_tag, set_context
from utils.error_monitor import monitor_openai_api, monitor_critical_system

import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
import logging
from typing import Optional, List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain.callbacks.tracers.langchain import LangChainTracer
from openai import OpenAI

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up LangSmith tracer
tracer = LangChainTracer(project_name="openai-cost-tracking")

@monitor_critical_system
def get_openai_api_key():
    """Get OpenAI API key from settings"""
    try:
        from config.settings import OPENAI_API_KEY
        return OPENAI_API_KEY
    except Exception as e:
        logger.error(f"Error loading OpenAI API key: {e}")
        capture_exception(e, {"function": "get_openai_api_key"})
        return None

@monitor_critical_system
def get_openrouter_config():
    """Get OpenRouter configuration from settings"""
    try:
        from config.settings import OPENROUTER_API_KEY, OPENROUTER_SITE_URL, OPENROUTER_SITE_NAME
        return {
            "api_key": OPENROUTER_API_KEY,
            "site_url": OPENROUTER_SITE_URL,
            "site_name": OPENROUTER_SITE_NAME
        }
    except Exception as e:
        logger.error(f"Error loading OpenRouter configuration: {e}")
        capture_exception(e, {"function": "get_openrouter_config"})
        return None

@monitor_openai_api(critical=True)
def make_openrouter_call(messages: List[Dict[str, str]], config: Dict[str, str]) -> Optional[str]:
    """Make API call to OpenRouter as fallback"""
    try:
        if not config or not config.get("api_key"):
            logger.error("OpenRouter API key not available")
            return None
            
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config["api_key"],
        )

        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": config["site_url"],
                "X-Title": config["site_name"],
            },
            extra_body={},
            model="deepseek/deepseek-chat-v3.1:free",
            messages=messages
        )
        
        return completion.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Error making OpenRouter API call: {e}")
        capture_exception(e, {"function": "make_openrouter_call"})
        return None

def get_url_test_type_config(test_type: str) -> dict:
    """Get the configuration for a specific URL test type"""
    base_configs = {
        "dashboard_functional": {
            "prefix": "TC_FUNC",
            "description": "functional test cases focusing on valid inputs, form submissions, and expected behaviors",
            "max_count": 50
        },
        "dashboard_negative": {
            "prefix": "TC_NEG",
            "description": "negative test cases focusing on invalid inputs, error handling, and edge cases",
            "max_count": 50
        },
        "dashboard_ui": {
            "prefix": "TC_UI",
            "description": "UI test cases focusing on visual elements, layout, and user interface components",
            "max_count": 50
        },
        "dashboard_ux": {
            "prefix": "TC_UX",
            "description": "user experience test cases focusing on user interaction, workflow, and accessibility",
            "max_count": 50
        },
        "dashboard_compatibility": {
            "prefix": "TC_COMPAT",
            "description": "compatibility test cases across different browsers, devices, and screen sizes",
            "max_count": 50
        },
        "dashboard_performance": {
            "prefix": "TC_PERF",
            "description": "performance test cases focusing on load times, responsiveness, and optimization",
            "max_count": 50
        }
    }
    return base_configs.get(test_type, {})

def extract_website_data(url: str) -> Dict[str, Any]:
    """Extract comprehensive data from a website URL"""
    try:
        logger.info(f"Fetching content from URL: {url}")
        
        # Create session with proper headers
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract various elements
        data = {
            'url': url,
            'title': _extract_title(soup),
            'meta_description': _extract_meta_description(soup),
            'headings': _extract_headings(soup),
            'links': _extract_links(soup, url),
            'forms': _extract_forms(soup),
            'buttons': _extract_buttons(soup),
            'images': _extract_images(soup, url),
            'text_content': _extract_text_content(soup),
            'navigation': _extract_navigation(soup, url),
            'footer': _extract_footer(soup),
            'page_structure': _analyze_page_structure(soup)
        }
        
        logger.info(f"Successfully extracted data from {url}")
        return data
        
    except Exception as e:
        logger.error(f"Error fetching content from {url}: {str(e)}")
        capture_exception(e, {"url": url})
        raise

def _extract_title(soup: BeautifulSoup) -> str:
    """Extract page title"""
    title_tag = soup.find('title')
    return title_tag.get_text().strip() if title_tag else ""

def _extract_meta_description(soup: BeautifulSoup) -> str:
    """Extract meta description"""
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    return meta_desc.get('content', '') if meta_desc else ""

def _extract_headings(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract all headings with their text and level"""
    headings = []
    for tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
        for heading in soup.find_all(tag):
            headings.append({
                'level': tag,
                'text': heading.get_text().strip(),
                'id': heading.get('id', '')
            })
    return headings

def _extract_links(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
    """Extract all links with their text and href"""
    links = []
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        text = link.get_text().strip()
        if text and href:
            links.append({
                'text': text,
                'href': urljoin(base_url, href),
                'title': link.get('title', '')
            })
    return links

def _extract_forms(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract all forms with their inputs and structure"""
    forms = []
    for form in soup.find_all('form'):
        inputs = []
        for input_tag in form.find_all(['input', 'textarea', 'select']):
            input_data = {
                'type': input_tag.name,
                'name': input_tag.get('name', ''),
                'id': input_tag.get('id', ''),
                'placeholder': input_tag.get('placeholder', ''),
                'required': input_tag.get('required') is not None
            }
            if input_tag.name == 'input':
                input_data['input_type'] = input_tag.get('type', 'text')
            inputs.append(input_data)
        
        forms.append({
            'action': form.get('action', ''),
            'method': form.get('method', 'get'),
            'inputs': inputs
        })
    return forms

def _extract_buttons(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """Extract all buttons"""
    buttons = []
    for button in soup.find_all(['button', 'input']):
        if button.name == 'input' and button.get('type') not in ['button', 'submit', 'reset']:
            continue
        
        buttons.append({
            'text': button.get_text().strip() or button.get('value', ''),
            'type': button.get('type', 'button'),
            'id': button.get('id', ''),
            'class': ' '.join(button.get('class', []))
        })
    return buttons

def _extract_images(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
    """Extract all images"""
    images = []
    for img in soup.find_all('img'):
        images.append({
            'src': urljoin(base_url, img.get('src', '')),
            'alt': img.get('alt', ''),
            'title': img.get('title', '')
        })
    return images

def _extract_text_content(soup: BeautifulSoup) -> str:
    """Extract main text content"""
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text content
    text = soup.get_text()
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = ' '.join(chunk for chunk in chunks if chunk)
    return text[:2000]  # Limit to first 2000 characters

def _extract_navigation(soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
    """Extract navigation elements"""
    nav_items = []
    nav_elements = soup.find_all(['nav', 'ul', 'ol'], class_=re.compile(r'nav|menu|navigation', re.I))
    
    for nav in nav_elements:
        for link in nav.find_all('a', href=True):
            nav_items.append({
                'text': link.get_text().strip(),
                'href': urljoin(base_url, link.get('href')),
                'title': link.get('title', '')
            })
    return nav_items

def _extract_footer(soup: BeautifulSoup) -> str:
    """Extract footer content"""
    footer = soup.find(['footer', 'div'], class_=re.compile(r'footer', re.I))
    return footer.get_text().strip() if footer else ""

def _analyze_page_structure(soup: BeautifulSoup) -> Dict[str, Any]:
    """Analyze overall page structure"""
    return {
        'has_header': bool(soup.find(['header', 'nav'])),
        'has_footer': bool(soup.find(['footer'])),
        'has_sidebar': bool(soup.find(class_=re.compile(r'sidebar|aside', re.I))),
        'has_main_content': bool(soup.find(['main', 'article', 'section'])),
        'total_links': len(soup.find_all('a')),
        'total_images': len(soup.find_all('img')),
        'total_forms': len(soup.find_all('form')),
        'total_buttons': len(soup.find_all(['button', 'input[type="button"]', 'input[type="submit"]']))
    }

def generate_url_test_cases(url: str, selected_types: List[str]) -> Optional[str]:
    """Generate test cases for a website URL based on selected types"""
    logger.info("=== generate_url_test_cases called ===")
    logger.info(f"URL: {url}")
    logger.info(f"Selected types: {selected_types}")
    
    if not url:
        logger.error("No URL provided for test case generation")
        return None
        
    if not selected_types or len(selected_types) == 0:
        logger.error("No test types selected for URL test case generation")
        return None

    logger.info(f"Generating test cases for URL: {url}")
    logger.info(f"Selected test types: {selected_types}")
    
    try:
        # Extract website data
        logger.info("Starting website data extraction...")
        website_data = extract_website_data(url)
        logger.info(f"Website data extracted successfully. Keys: {list(website_data.keys())}")
        
        all_test_cases = []
        
        for test_type in selected_types:
            logger.info(f"Starting generation for test type: {test_type}")
            config = get_url_test_type_config(test_type)
            if not config:
                logger.warning(f"Skipping unknown test type: {test_type}")
                continue

            # Create comprehensive prompt for URL-based test generation
            prompt = f"""
            Website Analysis Data:
            URL: {website_data['url']}
            Title: {website_data['title']}
            Meta Description: {website_data['meta_description']}
            
            Page Structure:
            - Headings: {len(website_data['headings'])} headings found
            - Links: {len(website_data['links'])} links found
            - Forms: {len(website_data['forms'])} forms found
            - Buttons: {len(website_data['buttons'])} buttons found
            - Images: {len(website_data['images'])} images found
            
            Key Elements:
            - Main navigation: {len(website_data['navigation'])} items
            - Form inputs: {sum(len(form['inputs']) for form in website_data['forms'])} total inputs
            - Page structure: {website_data['page_structure']}
            
            Content Summary: {website_data['text_content'][:500]}...

            Generate test cases for {config['description']} (up to {config['max_count']} maximum).
            Focus specifically on testing the website's functionality, user interface, and user experience.
            
            IMPORTANT: Analyze the website data thoroughly and generate the appropriate number of relevant test cases.
            Consider the complexity and scope of the website - generate only what's truly needed.
            Do not force additional test cases just to reach the maximum.
            
            ANALYSIS REQUIREMENTS:
            - Analyze all website elements: forms, buttons, links, navigation, content
            - Consider all possible user interactions and workflows
            - Identify edge cases and boundary conditions
            - Consider different user roles and access levels
            - Think about potential failure scenarios and error conditions
            - Analyze responsive design and cross-platform compatibility
            
            For each test case:
            1. Use the prefix {config['prefix']}
            2. Focus exclusively on {test_type} scenarios for web testing
            3. Include detailed steps that a QA engineer would follow
            4. Specify expected results for web interactions
            5. Consider the actual elements found on the page (forms, buttons, links, etc.)
            6. Include cross-browser compatibility testing if relevant
            7. Include mobile responsiveness testing if applicable
            8. Do not mix with other test types
            9. Ensure each test case tests a unique scenario

            Use this format for each test case:

            Title: {config['prefix']}_[Number]_[Brief_Title]
            Scenario: [Detailed scenario description covering all aspects]
            Steps to reproduce:
            1. [Step 1]
            2. [Step 2]
            ...
            Expected Result: [What should happen]
            Actual Result: [To be filled during execution]
            Priority: [High/Medium/Low]
            
            Ensure each test case covers a unique scenario and adds value.
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
                
                # Make the API call with monitoring
                @monitor_openai_api(critical=True)
                def make_openai_call():
                    return current_llm.invoke([
                        {
                            "role": "system",
                            "content": f"You are a senior QA engineer specializing in web testing. Generate the appropriate number of {test_type} test cases (up to {config['max_count']} maximum) for the provided website by analyzing the website complexity and generating only what's truly needed. Use {config['prefix']} as the prefix and focus on the actual elements found on the page. Focus on quality and relevance over quantity."
                        },
                        {"role": "user", "content": prompt}
                    ])
                
                response = make_openai_call()
                test_cases = response.content.strip()
                if test_cases:
                    logger.info(f"Generated {test_type} test cases successfully using OpenAI")
                    # Add a section header for each test type to help with parsing
                    test_cases_with_header = f"TEST TYPE: {test_type}\n\n{test_cases}"
                    all_test_cases.append(test_cases_with_header)
                else:
                    logger.warning(f"Received empty response for {test_type} test cases")

            except Exception as e:
                logger.error(f"OpenAI API failed for {test_type} test cases: {str(e)}")
                logger.info(f"Attempting fallback to OpenRouter for {test_type} test cases")
                
                # Try OpenRouter fallback
                try:
                    openrouter_config = get_openrouter_config()
                    if not openrouter_config or not openrouter_config.get("api_key"):
                        logger.error("OpenRouter configuration not available for fallback")
                        raise ValueError("No fallback API available")
                    
                    # Prepare messages for OpenRouter
                    messages = [
                        {
                            "role": "system",
                            "content": f"You are a senior QA engineer specializing in web testing. Generate the appropriate number of {test_type} test cases (up to {config['max_count']} maximum) for the provided website by analyzing the website complexity and generating only what's truly needed. Use {config['prefix']} as the prefix and focus on the actual elements found on the page. Focus on quality and relevance over quantity."
                        },
                        {"role": "user", "content": prompt}
                    ]
                    
                    test_cases = make_openrouter_call(messages, openrouter_config)
                    if test_cases:
                        logger.info(f"Generated {test_type} test cases successfully using OpenRouter fallback")
                        # Add a section header for each test type to help with parsing
                        test_cases_with_header = f"TEST TYPE: {test_type} (Generated via OpenRouter)\n\n{test_cases}"
                        all_test_cases.append(test_cases_with_header)
                    else:
                        logger.error(f"OpenRouter fallback also failed for {test_type} test cases")
                        raise ValueError("Both OpenAI and OpenRouter failed")
                        
                except Exception as fallback_error:
                    logger.error(f"Fallback to OpenRouter also failed for {test_type} test cases: {str(fallback_error)}")
                    # Capture error in MongoDB
                    capture_exception(e, {
                        "test_type": test_type,
                        "config": config,
                        "url": url,
                        "website_data_keys": list(website_data.keys()),
                        "fallback_error": str(fallback_error)
                    })
                    continue
            
            logger.info(f"Completed generation for test type: {test_type}")

        if not all_test_cases:
            logger.error("Failed to generate any test cases")
            return None
            
        logger.info(f"Successfully generated test cases for {len(all_test_cases)} test types")
        logger.info(f"Total test cases length: {len('\n\n'.join(all_test_cases))}")
        return "\n\n" + "\n\n".join(all_test_cases)
        
    except Exception as e:
        logger.error(f"Error in URL test case generation: {str(e)}")
        capture_exception(e, {"url": url, "selected_types": selected_types})
        
        # For debugging, return a simple test case if there's an error
        logger.info("Returning debug test case due to error")
        return f"""
TEST TYPE: dashboard_functional

Title: TC_FUNC_001_Debug_Test
Scenario: Debug test case for URL generation
Steps to reproduce:
1. Navigate to {url}
2. Verify the page loads
3. Check basic functionality
Expected Result: Page should load successfully
Actual Result: To be filled during execution
Priority: Medium
"""
