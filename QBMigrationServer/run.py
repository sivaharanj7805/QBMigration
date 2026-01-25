# STEP 1: Import dotenv
from dotenv import load_dotenv
import logging

# STEP 2: Load .env file BEFORE importing anything else

logger = logging.getLogger(__name__)

load_dotenv()

# STEP 3: Now import app (config.py will find SECRET_KEY)
from app import app

if __name__ == '__main__':
    logger.info("=" * 80)
    logger.info("QB MIGRATION SERVER - DEVELOPMENT MODE")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Server starting at: http://localhost:5000")
    logger.info("")
    logger.info("Press CTRL+C to stop")
    logger.info("=" * 80)
    logger.info("")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        logger.info("\n\nServer stopped by user")