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
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

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

def check_selenium_availability() -> bool:
    """Check if Selenium and ChromeDriver are available"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        # Try to create a Chrome driver instance
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.quit()
        return True
    except Exception as e:
        logger.warning(f"Selenium/ChromeDriver not available: {str(e)}")
        return False

def _validate_test_case_quality(test_cases: str, test_type: str, prefix: str) -> Optional[str]:
    """Validate the quality of generated test cases"""
    try:
        # Basic quality checks
        if not test_cases or len(test_cases.strip()) < 100:
            logger.warning("Test cases too short or empty")
            return None
        
        # Check for proper format elements
        required_elements = [
            "Title:",
            "Scenario:",
            "Steps to reproduce:",
            "Expected Result:",
            "Priority:"
        ]
        
        missing_elements = []
        for element in required_elements:
            if element not in test_cases:
                missing_elements.append(element)
        
        if missing_elements:
            logger.warning(f"Missing required elements: {missing_elements}")
            # Don't fail validation for missing elements, just log warning
        
        # Check for proper prefix usage
        if prefix and f"{prefix}_" not in test_cases:
            logger.warning(f"Test cases don't use proper prefix: {prefix}")
            # Don't fail validation for prefix issues, just log warning
        
        # Check for vague language
        vague_phrases = [
            "it should work",
            "page should load",
            "should be displayed",
            "should function properly",
            "should behave correctly"
        ]
        
        vague_count = sum(1 for phrase in vague_phrases if phrase.lower() in test_cases.lower())
        if vague_count > 2:
            logger.warning(f"Found {vague_count} vague phrases in test cases")
            # Don't fail validation for vague language, just log warning
        
        # Check for minimum number of test cases
        title_count = test_cases.count("Title:")
        if title_count < 3:
            logger.warning(f"Only {title_count} test cases generated, expected at least 3")
            # Don't fail validation for low count, just log warning
        
        logger.info(f"Test case quality validation passed for {test_type}")
        return test_cases
        
    except Exception as e:
        logger.error(f"Error validating test case quality: {str(e)}")
        return test_cases  # Return original if validation fails

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

def extract_website_data_with_selenium(url: str, wait_time: int = 5, scroll_pause: float = 1.0) -> Dict[str, Any]:
    """Extract comprehensive data from a website URL using Selenium for dynamic content"""
    driver = None
    try:
        logger.info(f"Fetching dynamic content from URL: {url}")
        
        # Set up Chrome options for headless browsing
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Initialize the driver
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Navigate to the URL
        driver.get(url)
        
        # Wait for initial page load
        logger.info(f"Waiting {wait_time} seconds for initial page load...")
        time.sleep(wait_time)
        
        # Scroll to load dynamic content
        logger.info("Scrolling to load dynamic content...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        scroll_attempts = 0
        max_scroll_attempts = 5
        
        while scroll_attempts < max_scroll_attempts:
            # Scroll down to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # Wait for new content to load
            time.sleep(scroll_pause)
            
            # Calculate new scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                logger.info("No more content to load, stopping scroll")
                break
                
            last_height = new_height
            scroll_attempts += 1
            logger.info(f"Scroll attempt {scroll_attempts}/{max_scroll_attempts}, new height: {new_height}")
        
        # Scroll back to top
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Wait for any lazy-loaded images or content
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except TimeoutException:
            logger.warning("Timeout waiting for body element, proceeding anyway")
        
        # Get the page source after all dynamic content is loaded
        page_source = driver.page_source
        # Ensure proper encoding handling for BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser', from_encoding='utf-8')
        
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
        
        logger.info(f"Successfully extracted dynamic data from {url}")
        logger.info(f"Found {len(data['links'])} links, {len(data['forms'])} forms, {len(data['buttons'])} buttons")
        return data
        
    except WebDriverException as e:
        logger.error(f"Selenium WebDriver error for {url}: {str(e)}")
        capture_exception(e, {"url": url, "method": "selenium"})
        raise
    except Exception as e:
        logger.error(f"Error in Selenium extraction for {url}: {str(e)}")
        capture_exception(e, {"url": url, "method": "selenium"})
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logger.warning(f"Error closing WebDriver: {e}")

def extract_website_data(url: str, use_selenium: bool = True, wait_time: int = 5, scroll_pause: float = 1.0) -> Dict[str, Any]:
    """Extract comprehensive data from a website URL with optional Selenium support"""
    
    # Check if Selenium is available and enabled
    if use_selenium and check_selenium_availability():
        try:
            logger.info(f"Attempting Selenium extraction for {url}")
            return extract_website_data_with_selenium(url, wait_time, scroll_pause)
        except Exception as selenium_error:
            logger.warning(f"Selenium extraction failed: {str(selenium_error)}")
            logger.info("Falling back to requests-based extraction...")
    elif use_selenium:
        logger.info("Selenium requested but not available, using requests-based extraction...")
    
    # Fallback to requests-based extraction
    try:
        logger.info(f"Fetching content from URL: {url} using requests")
        
        # Create session with proper headers to avoid bot detection
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Charset': 'utf-8',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
        
        # Try multiple approaches to avoid 403 errors
        response = None
        for attempt in range(3):
            try:
                if attempt == 0:
                    # First attempt: standard request
                    response = session.get(url, timeout=30)
                elif attempt == 1:
                    # Second attempt: with different user agent
                    session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    })
                    response = session.get(url, timeout=30)
                else:
                    # Third attempt: with referer header
                    session.headers.update({
                        'Referer': 'https://www.google.com/',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    })
                    response = session.get(url, timeout=30)
                
                response.raise_for_status()
                break
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403 and attempt < 2:
                    logger.warning(f"403 Forbidden on attempt {attempt + 1}, trying different approach...")
                    continue
                else:
                    raise
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Request failed on attempt {attempt + 1}, retrying...")
                    continue
                else:
                    raise
        
        if response is None:
            raise requests.exceptions.RequestException("All attempts to fetch the URL failed")
        
        # Ensure proper encoding handling for BeautifulSoup
        # Try to detect encoding from response headers or content
        encoding = response.encoding or 'utf-8'
        if not encoding or encoding.lower() == 'iso-8859-1':
            encoding = 'utf-8'
        
        # Decode content properly before passing to BeautifulSoup
        try:
            # Check if content is compressed or encoded
            content_type = response.headers.get('content-type', '').lower()
            logger.info(f"Content-Type: {content_type}")
            
            # Handle different content encodings
            if 'gzip' in response.headers.get('content-encoding', '').lower():
                import gzip
                content = gzip.decompress(response.content).decode(encoding, errors='ignore')
            elif 'deflate' in response.headers.get('content-encoding', '').lower():
                import zlib
                content = zlib.decompress(response.content).decode(encoding, errors='ignore')
            else:
                content = response.content.decode(encoding, errors='ignore')
            
            # Check if content looks like HTML
            if not content.strip().startswith('<'):
                logger.warning("Content doesn't appear to be HTML, might be compressed or encoded")
                # Try to detect if it's base64 encoded or other format
                if content.startswith('<!DOCTYPE') or '<html' in content.lower():
                    pass  # It's HTML
                else:
                    logger.warning("Content appears to be non-HTML, using fallback")
                    content = f"<html><body><p>Content from {url} - automated extraction blocked or content is not HTML</p></body></html>"
            
            soup = BeautifulSoup(content, 'html.parser')
            
        except (UnicodeDecodeError, UnicodeError) as e:
            logger.warning(f"Unicode decode error: {str(e)}, trying fallback")
            # Fallback to UTF-8 with error handling
            try:
                content = response.content.decode('utf-8', errors='ignore')
                soup = BeautifulSoup(content, 'html.parser')
            except Exception as fallback_error:
                logger.error(f"Fallback decode also failed: {str(fallback_error)}")
                # Create minimal HTML structure
                content = f"<html><body><p>Content from {url} - encoding issues prevented extraction</p></body></html>"
                soup = BeautifulSoup(content, 'html.parser')
        
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
    """Extract page title with proper encoding handling"""
    try:
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
            # Ensure proper encoding
            if isinstance(title, bytes):
                title = title.decode('utf-8', errors='ignore')
            # Remove any non-printable characters
            import string
            printable_chars = set(string.printable)
            title = ''.join(char for char in title if char in printable_chars or char.isspace())
            return title.strip()
        return ""
    except Exception as e:
        logger.warning(f"Error extracting title: {str(e)}")
        return ""

def _extract_meta_description(soup: BeautifulSoup) -> str:
    """Extract meta description with proper encoding handling"""
    try:
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            content = meta_desc.get('content', '')
            # Ensure proper encoding
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='ignore')
            # Remove any non-printable characters
            import string
            printable_chars = set(string.printable)
            content = ''.join(char for char in content if char in printable_chars or char.isspace())
            return content.strip()
        return ""
    except Exception as e:
        logger.warning(f"Error extracting meta description: {str(e)}")
        return ""

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
    """Extract main text content with proper encoding handling"""
    try:
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content with proper encoding handling
        text = soup.get_text()
        
        # Ensure text is properly encoded as UTF-8
        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='ignore')
        
        # Clean up whitespace and remove any remaining encoding artifacts
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Remove any remaining non-printable characters that might cause encoding issues
        import string
        printable_chars = set(string.printable)
        text = ''.join(char for char in text if char in printable_chars or char.isspace())
        
        # Clean up extra whitespace
        text = ' '.join(text.split())
        
        return text[:2000]  # Limit to first 2000 characters
        
    except Exception as e:
        logger.warning(f"Error extracting text content: {str(e)}")
        return "Content extraction failed due to encoding issues"

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

def generate_url_test_cases(url: str, selected_types: List[str], use_selenium: bool = True, wait_time: int = 5, scroll_pause: float = 1.0) -> Optional[str]:
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
        website_data = None
        try:
            website_data = extract_website_data(url, use_selenium, wait_time, scroll_pause)
            logger.info(f"Website data extracted successfully. Keys: {list(website_data.keys())}")
        except Exception as extraction_error:
            logger.warning(f"Website content extraction failed: {str(extraction_error)}")
            logger.info("Proceeding with fallback data extraction...")
            # Create minimal website data for fallback
            website_data = {
                'url': url,
                'title': f"Website: {urlparse(url).netloc}",
                'meta_description': "Website content could not be extracted due to access restrictions",
                'headings': [{'level': 'h1', 'text': 'Main Content', 'id': ''}],
                'links': [{'text': 'Home', 'href': url, 'title': 'Home'}],
                'forms': [],
                'buttons': [{'text': 'Submit', 'type': 'button', 'id': '', 'class': ''}],
                'images': [],
                'text_content': f"Content from {url} - automated extraction blocked",
                'navigation': [{'text': 'Home', 'href': url, 'title': 'Home'}],
                'footer': "Footer content",
                'page_structure': {
                    'has_header': True,
                    'has_footer': True,
                    'has_sidebar': False,
                    'has_main_content': True,
                    'total_links': 1,
                    'total_images': 0,
                    'total_forms': 0,
                    'total_buttons': 1
                }
            }
            logger.info("Fallback website data created successfully")
        
        all_test_cases = []
        
        for test_type in selected_types:
            logger.info(f"Starting generation for test type: {test_type}")
            config = get_url_test_type_config(test_type)
            if not config:
                logger.warning(f"Skipping unknown test type: {test_type}")
                continue

            # Create comprehensive prompt for URL-based test generation
            prompt = f"""
            🎯 WEBSITE ANALYSIS DATA:
            URL: {website_data['url']}
            Title: {website_data['title']}
            Meta Description: {website_data['meta_description']}
            
            📊 PAGE STRUCTURE ANALYSIS:
            - Headings: {len(website_data['headings'])} headings found
            - Links: {len(website_data['links'])} links found
            - Forms: {len(website_data['forms'])} forms found
            - Buttons: {len(website_data['buttons'])} buttons found
            - Images: {len(website_data['images'])} images found
            
            🔍 KEY ELEMENTS:
            - Main navigation: {len(website_data['navigation'])} items
            - Form inputs: {sum(len(form['inputs']) for form in website_data['forms'])} total inputs
            - Page structure: {website_data['page_structure']}
            
            📝 CONTENT SUMMARY: {website_data['text_content'][:500]}...
            
            🔗 SPECIFIC ELEMENTS FOUND:
            - Navigation items: {[item['text'] for item in website_data['navigation'][:10]]}
            - Form fields: {[f"{form.get('action', 'N/A')} - {[inp.get('name', inp.get('id', 'unnamed')) for inp in form.get('inputs', [])]}" for form in website_data['forms'][:5]]}
            - Button texts: {[btn['text'] for btn in website_data['buttons'][:10] if btn['text']]}
            - Key headings: {[h['text'] for h in website_data['headings'][:5]]}
            - Important links: {[link['text'] for link in website_data['links'][:10] if link['text'] and len(link['text']) > 3]}

            🎯 TASK: Generate HIGH-QUALITY test cases for {config['description']} (up to {config['max_count']} maximum).
            
            ⚡ QUALITY REQUIREMENTS:
            - Generate ONLY relevant, actionable test cases based on actual website elements
            - Each test case must be specific to the website's actual functionality
            - Avoid generic or template-based test cases
            - Focus on real user scenarios and business value
            - Consider the website's purpose and target audience
            
            🔬 DETAILED ANALYSIS REQUIREMENTS:
            - Analyze ALL website elements: forms, buttons, links, navigation, content
            - Consider ALL possible user interactions and workflows
            - Identify edge cases and boundary conditions specific to this website
            - Consider different user roles and access levels
            - Think about potential failure scenarios and error conditions
            - Analyze responsive design and cross-platform compatibility
            - Consider accessibility requirements (WCAG guidelines)
            - Think about security aspects and data validation
            
            📋 STRICT FORMAT for each test case:

            Title: {config['prefix']}_[SequentialNumber]_[Specific_Action_Being_Tested]
            Scenario: [Clear, specific scenario describing what is being tested and why it matters]
            Preconditions: [Required setup, user state, or data needed before test execution]
            Steps to Reproduce:
            1. [Specific, actionable step with exact elements to interact with]
            2. [Next specific step with expected behavior]
            3. [Continue with detailed, measurable steps]
            Expected Result: [Specific, testable outcome with measurable criteria]
            Actual Result: [Leave as 'To be filled during execution']
            Priority: [High/Medium/Low - based on business impact and user frequency]
            Test Data: [Specific input values, test accounts, or environment details if needed]
            
            ✅ QUALITY CHECKLIST:
            - Each test case covers a UNIQUE and VALUABLE scenario
            - Steps are CLEAR, ACTIONABLE, and written for a QA engineer to follow
            - Expected Results are SPECIFIC and MEASURABLE (not vague)
            - Test cases are RELEVANT to the actual website functionality
            - No duplicate or overlapping scenarios
            - Professional QA terminology used throughout
            - Consider real-world user behavior and business impact
            
            🚫 AVOID:
            - Generic test cases that could apply to any website
            - Vague expected results like "it should work" or "page should load"
            - Duplicate scenarios with minor variations
            - Test cases not relevant to the actual website content
            - Mixing different test types in one test case
            """

            try:
                # Get API key
                api_key = get_openai_api_key()
                if not api_key or api_key == "your_openai_api_key_here" or api_key == "missing_api_key":
                    error_msg = "⚠️ Invalid or missing OPENAI_API_KEY in environment variables"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                # Create LLM instance with API key - using GPT-4 for better quality
                current_llm = ChatOpenAI(
                    model="gpt-4o-mini",  # Using GPT-4o-mini for better quality at reasonable cost
                    temperature=0.3,  # Lower temperature for more consistent, focused output
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
                            "content": f"""You are a SENIOR QA ENGINEER with 10+ years of experience in web testing. Your expertise includes:

🎯 CORE RESPONSIBILITIES:
- Generate HIGH-QUALITY, ACTIONABLE test cases for {test_type} scenarios
- Focus on REAL-WORLD user scenarios and business value
- Create test cases that are SPECIFIC to the actual website functionality
- Ensure each test case is UNIQUE, VALUABLE, and EXECUTABLE

📊 QUALITY STANDARDS:
- Maximum {config['max_count']} test cases (quality over quantity)
- Use {config['prefix']} as the prefix for all test case titles
- Base test cases on ACTUAL website elements and functionality
- Avoid generic or template-based test cases
- Focus on measurable, testable outcomes

🔍 ANALYSIS APPROACH:
- Thoroughly analyze the provided website data
- Identify specific user workflows and interactions
- Consider edge cases and error conditions
- Think about different user roles and scenarios
- Focus on business-critical functionality

✅ OUTPUT REQUIREMENTS:
- Each test case must be specific to the website being tested
- Steps must be clear and actionable for QA engineers
- Expected results must be measurable and specific
- Avoid vague statements like "it should work"
- Include relevant preconditions and test data when needed

Your goal is to create test cases that a QA team can immediately execute and that provide real value in ensuring the website works correctly for its intended users."""
                        },
                        {"role": "user", "content": prompt}
                    ])
                
                response = make_openai_call()
                test_cases = response.content.strip()
                if test_cases:
                    # Validate the generated test cases quality
                    validated_test_cases = _validate_test_case_quality(test_cases, test_type, config['prefix'])
                    if validated_test_cases:
                        logger.info(f"Generated {test_type} test cases successfully using OpenAI")
                        # Add a section header for each test type to help with parsing
                        test_cases_with_header = f"TEST TYPE: {test_type}\n\n{validated_test_cases}"
                        all_test_cases.append(test_cases_with_header)
                    else:
                        logger.warning(f"Generated test cases failed quality validation for {test_type}")
                        # Use original test cases if validation fails
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
                            "content": f"""You are a SENIOR QA ENGINEER with 10+ years of experience in web testing. Your expertise includes:

🎯 CORE RESPONSIBILITIES:
- Generate HIGH-QUALITY, ACTIONABLE test cases for {test_type} scenarios
- Focus on REAL-WORLD user scenarios and business value
- Create test cases that are SPECIFIC to the actual website functionality
- Ensure each test case is UNIQUE, VALUABLE, and EXECUTABLE

📊 QUALITY STANDARDS:
- Maximum {config['max_count']} test cases (quality over quantity)
- Use {config['prefix']} as the prefix for all test case titles
- Base test cases on ACTUAL website elements and functionality
- Avoid generic or template-based test cases
- Focus on measurable, testable outcomes

🔍 ANALYSIS APPROACH:
- Thoroughly analyze the provided website data
- Identify specific user workflows and interactions
- Consider edge cases and error conditions
- Think about different user roles and scenarios
- Focus on business-critical functionality

✅ OUTPUT REQUIREMENTS:
- Each test case must be specific to the website being tested
- Steps must be clear and actionable for QA engineers
- Expected results must be measurable and specific
- Avoid vague statements like "it should work"
- Include relevant preconditions and test data when needed

Your goal is to create test cases that a QA team can immediately execute and that provide real value in ensuring the website works correctly for its intended users."""
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
        joined_test_cases = "\n\n".join(all_test_cases)
        total_length = len(joined_test_cases)
        logger.info(f"Total test cases length: {total_length}")
        return "\n\n" + joined_test_cases
        
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
