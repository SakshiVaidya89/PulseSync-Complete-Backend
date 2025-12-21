import os
from datetime import timedelta

class Config:
    """Base configuration"""
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/pulsesync')
    JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-this')
    JWT_EXPIRATION = timedelta(days=30)
    CORS_ORIGINS = [
        'http://localhost:3000',  # Auth frontend default
        'http://localhost:3001',  # Patient module
        'http://localhost:3002',  # Hospital module
        'http://localhost:5173',  # Vite dev server
        'http://localhost:5174',  # Alternative Vite dev server
        'http://127.0.0.1:3000',
        'http://127.0.0.1:3001',
        'http://127.0.0.1:3002',
        'http://127.0.0.1:5173',
        'http://127.0.0.1:5174',
    ]
    # Allow overriding via environment variable
    if os.getenv('CORS_ORIGINS'):
        CORS_ORIGINS = os.getenv('CORS_ORIGINS').split(',')

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
