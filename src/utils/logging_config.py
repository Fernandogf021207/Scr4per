import logging
import os

def setup_logging():
    """Configure logging for the project"""
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/scraper.log'),
            logging.StreamHandler()
        ],
        force=True,
    )
    for logger_name in ('api', 'src', 'uvicorn.error'):
        logging.getLogger(logger_name).setLevel(logging.INFO)
    return logging.getLogger(__name__)