# app/config.py
import os
import secrets

class Config:
    """ConfiguraciÃ³n base para la aplicaciÃ³n"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(24)
    TEMPLATES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'views/templates')
    # AÃ±adir configuraciÃ³n de Redis
    # Render proporciona REDIS_URL automÃ¡ticamente si vinculas un servicio Redis
    # Para local, puedes establecerla o usar el valor predeterminado
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

class DevelopmentConfig(Config):
    """ConfiguraciÃ³n para entorno de desarrollo"""
    DEBUG = True

class ProductionConfig(Config):
    """ConfiguraciÃ³n para entorno de producciÃ³n"""
    DEBUG = False
    # PodrÃ­as tener configuraciones de Redis especÃ­ficas aquÃ­ si fuera necesario

# ConfiguraciÃ³n segÃºn el entorno
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig
}

# Determinar configuraciÃ³n activa
def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    if os.environ.get('RENDER', '') == 'true':
        env = 'production'
    # Asegurar que siempre obtengamos una instancia de Config
    config_class = config_by_name.get(env, DevelopmentConfig)
    return config_class() # Devolver una instancia