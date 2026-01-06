# STEP 1: Import dotenv
from dotenv import load_dotenv

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
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")