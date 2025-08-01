
# AI Test Case Generator

This project automates the generation of detailed Selenium test cases in Python using OpenAI's GPT-4 model. It integrates with Jira, Azure DevOps, and image-based inputs to generate comprehensive test cases.

## Features

- Multi-platform integration:
  - Jira integration with REST API support
  - Azure DevOps integration with work item support
  - Image-based test case generation from UI/UX screenshots
- Comprehensive test case generation:
  - Functional test cases
  - UI/UX test cases
  - Compatibility test cases
  - Accessibility test cases
  - Responsiveness test cases
- Multiple output formats:
  - Excel reports (.xlsx)
  - Text files (.txt)
- Real-time progress indication with loader animation
- Organized file storage with unique identifiers
- Web interface for easy interaction

## Project Structure

```tree
├── .env                    # Environment variables
├── .gitignore              # Git ignore file
├── README.md               # Project documentation
├── app.py                  # Flask application
├── requirements.txt        # Python dependencies
├── ai/                     # AI integration
│   ├── generator.py        # Test case generation
│   └── image_generator.py  # Image processing
├── azure_integration/      # Azure DevOps integration
│   ├── __init__.py         # Azure integration module
│   ├── azure_client.py     # Azure client
│   └── pipeline.py         # Azure pipeline
├── config/                 # Configuration
│   └── settings.py         # Configuration settings
├── jira/                   # Jira integration
│   └── jira_client.py      # Jira client
├── templates/              # HTML templates
│   ├── index.html          # Main page
│   ├── results.html        # Result page
│   └── view.html           # View page
├── tests/                  # Test cases
│   ├── generated/          # Generated test cases
│   └── images/             # Uploaded images
├── utils/                  # Utility functions
│   ├── file_handler.py     # File handling utilities
│   ├── logger.py           # Logging utility
│   └── mongo_handler.py    # MongoDB utility
```


## Prerequisites

- Python 3.12 or higher
- OpenAI API key with GPT-4 access
- Jira/Azure DevOps credentials (if using those features)
- Jira/Azure DevOps account with API access (if using those features)

### Required Libraries

- **openai**: Integration with GPT-4 API for test case generation
- **requests**: HTTP client for Jira and Azure DevOps API integration
- **python-dotenv**: Environment variable management
- **beautifulsoup4**: HTML parsing for Azure work item descriptions
- **pandas**: Excel report generation and data handling
- **Pillow**: Image processing for image-based test case generation
- **flask**: Web application framework
- **openpyxl**: Excel file handling
- **pymongo**: MongoDB driver for Python

### Built-in Libraries Used

- **typing**: Type hints for better code documentation
- **logging**: Application logging and error tracking
- **os**: Operating system interface for file and path operations
- **base64**: Encoding for Azure DevOps authentication
- **re**: Regular expressions for text processing

### Environment Variables Required

#### For OpenAI
- `OPENAI_API_KEY`: Your OpenAI API key

#### For MongoDB
- `MONGO_URI`: MongoDB connection URI
- `MONGO_DB`: MongoDB database name
- `MONGO_COLLECTION`: MongoDB collection name

#### For Jira Integration
- `JIRA_URL`: Your Jira instance URL
- `JIRA_USER`: Jira username/email
- `JIRA_API_TOKEN`: Jira API token
- `JIRA_ISSUE_KEYS`: Comma-separated list of Jira issue keys (for batch processing)

#### For Azure DevOps Integration
- `AZURE_DEVOPS_URL`: Azure DevOps URL
- `AZURE_DEVOPS_ORG`: Your organization name
- `AZURE_DEVOPS_PROJECT`: Your project name
- `AZURE_DEVOPS_PAT`: Personal Access Token
- `AZURE_DEVOPS_WORKITEM_IDS`: Comma-separated list of work item IDs (for batch processing)
- `AZURE_DEVOPS_USER_STORY_ID`: User story ID (for processing all tasks under a user story)

#### General Settings

- A virtual environment (recommended)
- Jira account with API access (for Jira integration)
- Azure DevOps account with API access (for Azure integration)
- OpenAI API key

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ui-based-testcase-generator
   ```

2. Create a virtual environment:
    ```bash
    python -m venv myenv
    source myenv/Scripts/activate  # On Windows
    OR
    .\myenv\Scripts\activate   
    source myenv/bin/activate      # On macOS/Linux
    ```

3. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. Create a .env file in the root directory and add the following variables:
    ```bash
    # OpenAI Configuration
    OPENAI_API_KEY=<your_openai_api_key>

    ```

## Usage

1. Start the Flask server:
    ```bash
    python app.py
    ```
2.  Open http://localhost:5005 in your browser
3.  Choose input source:
  - Enter Jira ticket ID
  - Enter Azure DevOps work item ID
  - Upload UI/UX image
4. Click Generate to create test cases
5. Download generated test cases in Excel format

## Output Formats
- Excel (.xlsx) : Structured format with sections, scenarios, and steps
- Preview : Preview of the generated test cases.

## Error Handling
- Validates input sources before processing
- Provides clear error messages for invalid inputs
- Handles API timeouts and connection issues
- Ensures proper cleanup of temporary files

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Acknowledgments
- OpenAI for the GPT-4 model.
- Atlassian Jira for the Jira REST API.
- Microsoft Azure DevOps for the Work Items REST API.
