import os
import secrets

class Config:
    """Configuración base para la aplicación"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(24)
    TEMPLATES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'views/templates')
    
class DevelopmentConfig(Config):
    """Configuración para entorno de desarrollo"""
    DEBUG = True

class ProductionConfig(Config):
    """Configuración para entorno de producción"""
    DEBUG = False

# Configuración según el entorno
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig
}

# Determinar configuración activa
def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    if os.environ.get('RENDER', '') == 'true':
        env = 'production'
    return config_by_name[env]
