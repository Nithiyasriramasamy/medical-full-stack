import os
import sys

# Ensure the project root is in the path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the app from the backend package
try:
    from backend.app import app
except ImportError:
    # Fallback for different environments
    sys.path.insert(0, os.path.join(project_root, 'backend'))
    from app import app

if __name__ == "__main__":
    app.run()
