# STEP 1: Import dotenv
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)


# STEP 2: Load .env file BEFORE importing anything else
load_dotenv()

# STEP 3: Now import app (config.py will find SECRET_KEY)
from app import app

if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("QB MIGRATION SERVER - DEVELOPMENT MODE")
    logger.info("=" * 80)
    logger.info("")
    logger.info("Server starting at: http://localhost:5000")
    logger.info("")
    logger.info("Press CTRL+C to stop")
    logger.info("=" * 80)
    logger.info("")

    # FIX CRIT-02: Bind to localhost only by default for security
    # To expose to network, set DEV_HOST environment variable
    host = os.environ.get("DEV_HOST", "127.0.0.1")

    if host == "0.0.0.0":
        logger.info("WARNING: Server is binding to all interfaces (0.0.0.0)")
        logger.info("This should ONLY be used in isolated development environments!")
        logger.info("=" * 80)
        logger.info("")

    try:
        app.run(host=host, port=5000, debug=True)
    except KeyboardInterrupt:
        logger.info("\n\nServer stopped by user")
