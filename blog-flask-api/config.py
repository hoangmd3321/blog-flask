import os
from dotenv import load_dotenv
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.flaskenv'))
class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
    DISABLE_AUTH = (os.environ.get('DISABLE_AUTH'))
    ACCESS_TOKEN_EXPIRE_MINS = int(os.environ.get('ACCESS_TOKEN_EXPIRE_MINS') or '15')
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get('REFRESH_TOKEN_EXPIRE_DAYS') or '7')
    REFRESH_TOKEN_IN_COOKIE = os.environ.get('REFRESH_TOKEN_IN_COOKIE')
    REFRESH_TOKEN_IN_BODY = os.environ.get('REFRESH_TOKEN_IN_BODY')
    RESET_TOKEN_MINS = int(os.environ.get('RESET_TOKEN_MINS') or '15')
    PASSWORD_RESET_URL = os.environ.get('PASSWORD_RESET_URL') or \
        'http://localhost:3000/reset'
    USE_CORS = os.environ.get('USE_CORS')
    CORS_SUPPORTS_CREDENTIALS = True
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT')
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    DEFAULT_SENDER = ['flaskblog@example.com']
    POSTs_PER_PAGE = 25
    LANGUAGES = ['en', 'vi']
    ELASTICSEARCH_URL = os.environ.get('ELASTICSEARCH_URL')
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://'