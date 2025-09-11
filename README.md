
# AI Test Case Generator

A comprehensive web-based application that automates the generation of detailed Selenium test cases using AI. The system integrates with multiple platforms including Jira, Azure DevOps, and supports image-based and URL-based test case generation with advanced analytics and sharing capabilities.

## 🚀 Features

### Multi-Platform Integration
- **Jira Integration**: REST API support for fetching requirements and user stories
- **Azure DevOps Integration**: Work item support with comprehensive task analysis
- **Image-Based Generation**: UI/UX screenshot analysis for test case creation
- **URL-Based Generation**: Web page analysis for automated test case generation

### Comprehensive Test Case Types
- **Functional Tests**: Positive and negative test scenarios
- **UI/UX Tests**: User interface and experience validation
- **Compatibility Tests**: Cross-browser and device compatibility
- **Performance Tests**: Load and stress testing scenarios
- **Accessibility Tests**: WCAG compliance and accessibility validation
- **Responsiveness Tests**: Mobile and responsive design validation

### Advanced Analytics Dashboard
- **Real-time Metrics**: Total sessions, generation clicks, success rates
- **Performance Analytics**: Average and maximum generation times
- **Source Distribution**: Visual breakdown of test case sources
- **Test Case Type Usage**: Comprehensive usage statistics
- **Recent Activity Tracking**: User interaction monitoring
- **Interactive Charts**: Donut charts and bar graphs with filtering

### Sharing & Collaboration
- **Share Test Cases**: Generate shareable URLs for test case distribution
- **Public Viewing**: Secure access to shared test cases without authentication
- **Status Management**: Real-time status updates (Pass, Fail, Blocked, Not Tested)
- **Excel Export**: Download test cases with current status values
- **Collaborative Analytics**: Shared analytics for team insights

### Multiple Output Formats
- **Excel Reports** (.xlsx): Structured format with sections, scenarios, and steps
- **Text Files** (.txt): Plain text format for easy sharing
- **Real-time Preview**: Live preview of generated test cases
- **Status Tracking**: Integrated status management with export capabilities

## 📁 Project Structure

```
AI-TestCaseGenerator/
├── .env                    # Environment variables
├── .gitignore              # Git ignore file
├── README.md               # Project documentation
├── app.py                  # Flask application (main server)
├── requirements.txt        # Python dependencies
├── ai/                     # AI integration modules
│   ├── generator.py        # Core test case generation logic
│   ├── image_generator.py  # Image processing and analysis
│   └── url_generator.py    # URL-based test case generation
├── azure_integration/      # Azure DevOps integration
│   ├── __init__.py
│   ├── azure_client.py     # Azure DevOps API client
│   └── pipeline.py         # Pipeline and work item processing
├── config/                 # Configuration management
│   └── settings.py         # Application settings and constants
├── jira/                   # Jira integration
│   ├── __init__.py
│   └── jira_client.py      # Jira REST API client
├── templates/              # HTML templates
│   ├── index.html          # Main generator interface
│   ├── results.html        # Results and analytics dashboard
│   ├── view.html           # Shared test case viewer
│   ├── analytics.html      # Comprehensive analytics dashboard
│   └── error.html          # Error page template
├── static/                 # Static assets
│   ├── assets/             # Images and icons
│   └── js/                 # JavaScript files
├── tests/                  # Generated test cases
│   ├── generated/          # Generated test case files
│   └── images/             # Uploaded images for processing
├── uploads/                # User uploaded files
└── utils/                  # Utility functions
    ├── file_handler.py     # File processing and Excel generation
    ├── logger.py           # Logging configuration
    ├── mongo_handler.py    # MongoDB operations and analytics
    ├── error_logger.py     # Error logging to MongoDB
    └── web_screenshot.py   # Web page screenshot capture
```

## 🛠️ Prerequisites

### System Requirements
- **Python**: 3.12 or higher
- **Memory**: Minimum 4GB RAM (8GB recommended)
- **Storage**: 1GB free space for generated files
- **Network**: Internet connection for API access

### API Keys & Credentials
- **OpenAI API Key**: Access to gpt-3.5-turbo or gpt-4 models
- **Jira Credentials**: URL, username, and API token (for Jira integration)
- **Azure DevOps PAT**: Personal Access Token (for Azure integration)
- **MongoDB Connection**: URI for analytics and data storage

## 📦 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd AI-TestCaseGenerator
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv myenv
myenv\Scripts\activate

# macOS/Linux
python -m venv myenv
source myenv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the root directory:

```bash
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# MongoDB Configuration (for analytics)
MONGO_URI=mongodb://localhost:27017/
MONGO_DB=testcase_generator
MONGO_COLLECTION=analytics

# Jira Configuration (optional)
JIRA_URL=https://your-domain.atlassian.net
JIRA_USER=your_email@domain.com
JIRA_API_TOKEN=your_jira_api_token

# Azure DevOps Configuration (optional)
AZURE_DEVOPS_URL=https://dev.azure.com
AZURE_DEVOPS_ORG=your_organization
AZURE_DEVOPS_PROJECT=your_project
AZURE_DEVOPS_PAT=your_personal_access_token

# Application Settings
BASE_URL=http://localhost:5008
FLASK_ENV=development
```

## 🚀 Usage

### 1. Start the Application
```bash
python app.py
```

### 2. Access the Application
Open your browser and navigate to: `http://localhost:5008`

### 3. Generate Test Cases

#### Option A: Jira Integration
1. Select "Jira" as the source type
2. Enter Jira ticket ID (e.g., PROJ-123)
3. Click "Generate Test Cases"
4. Wait for AI processing and generation

#### Option B: Azure DevOps Integration
1. Select "Azure DevOps" as the source type
2. Enter work item ID or user story ID
3. Click "Generate Test Cases"
4. Monitor progress and download results

#### Option C: Image-Based Generation
1. Select "Image" as the source type
2. Upload UI/UX screenshot or mockup
3. Click "Generate Test Cases"
4. Review and download generated test cases

#### Option D: URL-Based Generation
1. Select "URL" as the source type
2. Enter website URL for analysis
3. Click "Generate Test Cases"
4. Get comprehensive web-based test cases

### 4. Analytics & Monitoring
- Access analytics dashboard at `/analytics`
- View real-time metrics and performance data
- Filter data by date range and source type
- Monitor user activity and generation patterns

### 5. Sharing & Collaboration
- Click "Share" to generate shareable URL
- Share URL with team members
- View shared test cases without authentication
- Update test case statuses collaboratively
- Export updated test cases with current status

## 📊 Analytics Dashboard

The analytics dashboard provides comprehensive insights into:

### Key Metrics
- **Total Sessions**: Number of user sessions
- **Generate Clicks**: Test case generation attempts
- **Successful Generations**: Successfully completed generations
- **Success Rate**: Percentage of successful generations
- **Average Generation Time**: Mean time for test case generation
- **Maximum Generation Time**: Peak generation duration

### Test Case Analytics
- **Total Test Cases Generated**: Overall test case count
- **Source Distribution**: Breakdown by Jira, Azure, Image, URL
- **Test Case Type Usage**: Distribution across test types
- **Performance Trends**: Generation time analysis

### Interactive Features
- **Date Range Filtering**: Customizable time periods
- **Source Type Filtering**: Filter by specific platforms
- **Real-time Updates**: Live data refresh
- **Export Capabilities**: Download analytics data

## 🔧 Configuration

### Advanced Settings
```python
# In config/settings.py
MAX_TOKENS = 4000                    # Maximum tokens for AI generation
TEMPERATURE = 0.7                    # AI creativity level
MODEL_NAME = "gpt-3.5-turbo"         # OpenAI model to use
MAX_RETRIES = 3                      # API retry attempts
TIMEOUT_SECONDS = 120                # Request timeout
```

### Custom Test Case Templates
Modify the AI prompts in `ai/generator.py` to customize:
- Test case structure and format
- Test scenario generation logic
- Output formatting preferences
- Platform-specific adaptations

## 🐛 Troubleshooting

### Common Issues

#### OpenAI API Errors
```bash
# Check API key configuration
echo $OPENAI_API_KEY

# Verify API quota and billing
# Visit: https://platform.openai.com/account/billing
```

#### MongoDB Connection Issues
```bash
# Verify MongoDB is running
mongod --version

# Check connection string format
# Format: mongodb://username:password@host:port/database
```

#### Jira/Azure Integration Problems
```bash
# Test Jira connection
curl -u username:api_token https://your-domain.atlassian.net/rest/api/2/myself

# Test Azure DevOps connection
curl -u :pat https://dev.azure.com/organization/project/_apis/wit/workitems/1
```

### Performance Optimization
- **Increase Memory**: Allocate more RAM for large test case generation
- **Optimize Network**: Use faster internet connection for API calls
- **Database Indexing**: Add indexes to MongoDB collections for faster queries
- **Caching**: Implement Redis caching for frequently accessed data

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Guidelines
- Follow PEP 8 style guidelines
- Add comprehensive docstrings
- Include unit tests for new features
- Update documentation for API changes
- Test across different platforms

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **OpenAI**: For providing the GPT models that power test case generation
- **Atlassian**: For Jira REST API and integration support
- **Microsoft**: For Azure DevOps Work Items API
- **Flask**: For the web framework that powers the application
- **MongoDB**: For robust data storage and analytics capabilities
- **Chart.js**: For beautiful and interactive data visualizations

## 📞 Support

For support and questions:
- **Issues**: Create an issue on GitHub
- **Documentation**: Check the inline code documentation
- **Community**: Join our discussion forum

---

**Made with ❤️ for the testing community**
