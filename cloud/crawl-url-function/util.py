from google.cloud import logging

logger = logging.Client().logger('crawl_url')
