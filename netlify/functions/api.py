# netlify/functions/api.py

from mangum import Mangum
from app import app  # Importing your Flask app instance

# This handler is the entry point for Netlify's function invocation
handler = Mangum(app)
