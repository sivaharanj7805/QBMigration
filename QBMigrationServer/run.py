# STEP 1: Import dotenv
from dotenv import load_dotenv
import os

# STEP 2: Load .env file BEFORE importing anything else
load_dotenv()

# STEP 3: Now import app (config.py will find SECRET_KEY)
from app import app

if __name__ == '__main__':
    print("=" * 80)
    print("QB MIGRATION SERVER - DEVELOPMENT MODE")
    print("=" * 80)
    print("")
    print("Server starting at: http://localhost:5000")
    print("")
    print("Press CTRL+C to stop")
    print("=" * 80)
    print("")

    # FIX CRIT-02: Bind to localhost only by default for security
    # To expose to network, set DEV_HOST environment variable
    host = os.environ.get('DEV_HOST', '127.0.0.1')

    if host == '0.0.0.0':
        print("WARNING: Server is binding to all interfaces (0.0.0.0)")
        print("This should ONLY be used in isolated development environments!")
        print("=" * 80)
        print("")

    try:
        app.run(host=host, port=5000, debug=True)
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")