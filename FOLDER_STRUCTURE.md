# AI Test Case Generator - Folder Structure

## 📁 Project Root Structure

```
AI-TestCaseGenerator-linkissue/
├── 📄 app.py                          # Main Flask application entry point
├── 📄 requirements.txt                # Python dependencies
├── 📄 README.md                       # Project documentation
├── 📄 .gitignore                      # Git ignore rules
├── 📄 .env                           # Environment variables (not in git)
├── 📄 FOLDER_STRUCTURE.md            # This file - folder structure documentation
│
├── 📁 ai/                            # AI/ML related modules
│   ├── 📄 __init__.py
│   ├── 📄 generator.py               # Text-based test case generation
│   └── 📄 image_generator.py         # Image-based test case generation
│
├── 📁 azure_integration/             # Azure DevOps integration
│   ├── 📄 __init__.py
│   ├── 📄 azure_client.py            # Azure DevOps API client
│   └── 📄 pipeline.py                # Pipeline and work item handling
│
├── 📁 config/                        # Configuration management
│   ├── 📄 __init__.py
│   └── 📄 settings.py                # Environment variables and settings
│
├── 📁 jira/                          # Jira integration
│   ├── 📄 __init__.py
│   └── 📄 jira_client.py             # Jira API client
│
├── 📁 static/                        # Static assets (CSS, JS, images)
│   ├── 📁 assets/
│   │   └── 📁 images/
│   │       ├── 📄 favicon.png        # Website favicon
│   │       └── 📄 eatance--logo.svg  # Company logo
│   └── 📁 js/                        # JavaScript files (currently empty)
│
├── 📁 templates/                     # HTML templates
│   ├── 📄 index.html                 # Main landing page
│   ├── 📄 results.html               # Test case results page
│   ├── 📄 view.html                  # Shared test case view
│   └── 📄 error.html                 # Error page template
│
├── 📁 tests/                         # Test files and generated content
│   ├── 📁 generated/                 # Generated test case files
│   │   ├── 📄 test_KAN-1.xlsx        # Excel test case files
│   │   ├── 📄 test_KAN-1.txt         # Text test case files
│   │   ├── 📄 test_image_*.xlsx      # Image-based test cases
│   │   └── 📄 test_image_*.txt       # Image-based test cases
│   └── 📁 images/                    # Test images (currently empty)
│
├── 📁 uploads/                       # User uploaded files
│
├── 📁 utils/                         # Utility modules
│   ├── 📄 __init__.py
│   ├── 📄 file_handler.py            # File operations and parsing
│   ├── 📄 logger.py                  # Logging configuration
│   ├── 📄 mongo_handler.py           # MongoDB database operations
│   └── 📄 error_logger.py            # MongoDB error logging
│
├── 📁 myenv/                         # Python virtual environment
└── 📁 .git/                          # Git repository data
```

## 📋 Detailed Component Descriptions

### 🚀 **Core Application Files**

#### `app.py`
- **Purpose**: Main Flask application entry point
- **Key Features**:
  - Flask routes and endpoints
  - API integrations (Jira, Azure, AI)
  - File upload handling
  - Test case generation orchestration
  - MongoDB data management
  - Error handling and logging

#### `requirements.txt`
- **Purpose**: Python package dependencies
- **Key Packages**:
  - Flask (web framework)
  - OpenAI (AI integration)
  - LangChain (AI orchestration)
  - PyMongo (MongoDB client)
  - Pandas (data manipulation)
  - OpenPyXL (Excel handling)

### 🤖 **AI Module (`ai/`)**

#### `ai/generator.py`
- **Purpose**: Text-based test case generation
- **Features**:
  - OpenAI GPT integration
  - Test case type selection
  - Structured output generation
  - Error handling and retry logic

#### `ai/image_generator.py`
- **Purpose**: Image-based test case generation
- **Features**:
  - OpenAI Vision API integration
  - Image analysis and processing
  - Test case extraction from screenshots
  - Multi-format output support

### 🔗 **Integration Modules**

#### `azure_integration/`
- **Purpose**: Azure DevOps integration
- **Files**:
  - `azure_client.py`: API client for Azure DevOps
  - `pipeline.py`: Pipeline and work item handling

#### `jira/`
- **Purpose**: Jira integration
- **Files**:
  - `jira_client.py`: Jira API client and issue fetching

### ⚙️ **Configuration (`config/`)**

#### `config/settings.py`
- **Purpose**: Environment variable management
- **Features**:
  - API key loading
  - Database connection strings
  - Environment-specific settings
  - Default value handling

### 🎨 **Frontend Assets (`static/`)**

#### `static/assets/images/`
- **Purpose**: Static image assets
- **Files**:
  - `favicon.png`: Website favicon
  - `eatance--logo.svg`: Company logo

#### `static/js/`
- **Purpose**: JavaScript files (currently empty, JS is embedded in templates)

### 📄 **HTML Templates (`templates/`)**

#### `templates/index.html`
- **Purpose**: Main landing page
- **Features**:
  - Test case generation form
  - Source type selection (Text, Jira, Azure, Image)
  - File upload interface
  - Real-time status updates

#### `templates/results.html`
- **Purpose**: Test case results display
- **Features**:
  - Test case table with status management
  - Download options (Excel, TXT)
  - Copy and share functionality
  - Status tracking and updates

#### `templates/view.html`
- **Purpose**: Shared test case viewing
- **Features**:
  - Public test case display
  - Status synchronization
  - Download capabilities

#### `templates/error.html`
- **Purpose**: Error page template
- **Features**:
  - User-friendly error messages
  - Navigation back to main page

### 📊 **Test Files (`tests/`)**

#### `tests/generated/`
- **Purpose**: Generated test case files
- **File Types**:
  - `.xlsx`: Excel format test cases
  - `.txt`: Text format test cases
  - `test_KAN-*.xlsx/txt`: Jira-based test cases
  - `test_image_*.xlsx/txt`: Image-based test cases

#### `tests/images/`
- **Purpose**: Test images (currently empty)

### 🛠️ **Utility Modules (`utils/`)**

#### `utils/file_handler.py`
- **Purpose**: File operations and parsing
- **Features**:
  - Test case parsing from text
  - Excel file generation
  - File format conversion
  - Error handling

#### `utils/mongo_handler.py`
- **Purpose**: MongoDB database operations
- **Features**:
  - Test case storage and retrieval
  - Status tracking
  - URL shortening
  - Data synchronization

#### `utils/logger.py`
- **Purpose**: Logging configuration
- **Features**:
  - Structured logging
  - Error tracking
  - Debug information

#### `utils/error_logger.py`
- **Purpose**: MongoDB error logging
- **Features**:
  - Error monitoring
  - Performance tracking
  - User feedback collection

### 📁 **Uploads (`uploads/`)**
- **Purpose**: User uploaded files
- **Features**:
  - Temporary file storage
  - Image processing queue

## 🔄 **Data Flow**

```
User Input → app.py → AI Modules → File Handler → MongoDB → Results Page
     ↓
Jira/Azure → Integration Modules → AI Processing → File Generation
     ↓
Image Upload → Image Generator → Test Cases → Storage → Display
```

## 🌐 **Deployment Structure**

### **Local Development**
- Uses `myenv/` virtual environment
- `.env` file for local configuration
- Direct file system access

### **Cloud Deployment (Render/Heroku/etc.)**
- Environment variables for configuration
- Ephemeral file system handling
- MongoDB Atlas for data persistence
- Static asset serving

## 📝 **File Naming Conventions**

### **Generated Test Files**
- `test_{ITEM_ID}.xlsx/txt` - Jira/Azure test cases
- `test_image_{TIMESTAMP}_{HASH}.xlsx/txt` - Image-based test cases
- `test_{ITEM_ID}_fixed.xlsx/txt` - Corrected test cases

### **Temporary Files**
- `*.temp.xlsx` - Temporary Excel files
- `*.temp.txt` - Temporary text files

## 🔧 **Configuration Files**

### **Environment Variables (.env)**
```bash
OPENAI_API_KEY=your_openai_api_key
MONGODB_URI=your_mongodb_connection_string
LANGSMITH_API_KEY=your_langsmith_key
```

### **Git Ignore (.gitignore)**
- `.env` - Environment variables
- `myenv/` - Virtual environment
- `__pycache__/` - Python cache
- `*.temp.*` - Temporary files

## 📊 **Database Collections (MongoDB)**

### **test_cases**
- Stores test case data
- URL shortening tokens
- Status tracking
- Sharing information

## 🚀 **Deployment Considerations**

### **Required Directories**
- `tests/generated/` - Must be writable
- `uploads/` - Must be writable
- `static/` - Must be readable

### **File Permissions**
- Read access to all template and static files
- Write access to generated and upload directories
- Execute access to Python files

This folder structure provides a clean, organized, and scalable architecture for the AI Test Case Generator application. 