# app/__init__.py
from flask import Flask
from flask_socketio import SocketIO
from .config import get_config
import redis # Importar redis
import json # Importar json para serializar/deserializar

# Inicializar SocketIO antes de la aplicaciÃ³n
socketio = SocketIO(cors_allowed_origins="*")

# Inicializar cliente Redis (fuera de create_app para que sea global)
# Se inicializarÃ¡ con la URL de la configuraciÃ³n cuando se llame a create_app
redis_client = None

def create_app():
    """FunciÃ³n para crear y configurar la aplicaciÃ³n Flask"""
    global redis_client # Usar la variable global

    app = Flask(__name__,
                template_folder='views/templates',
                static_folder='static')

    # Aplicar configuraciÃ³n
    app_config = get_config() # Obtener la instancia de configuraciÃ³n
    app.config.from_object(app_config)

    # Inicializar y probar cliente Redis
    try:
        # Usar decode_responses=True para obtener strings en lugar de bytes
        redis_client = redis.Redis.from_url(app_config.REDIS_URL, decode_responses=True)
        redis_client.ping() # Probar conexiÃ³n
        print("Conectado a Redis exitosamente!")
    except redis.exceptions.ConnectionError as e:
        print(f"ERROR: No se pudo conectar a Redis en {app_config.REDIS_URL}")
        print(f"Detalle del error: {e}")
        # Considera quÃ© hacer aquÃ­: salir, loggear, etc.
        # Por ahora, imprimiremos el error y continuaremos (la app fallarÃ¡ mÃ¡s adelante)
        redis_client = None # Asegurar que es None si falla

    # Pasar el cliente Redis a la app (opcional pero Ãºtil)
    app.redis_client = redis_client

    # Inicializar SocketIO con la aplicaciÃ³n
    socketio.init_app(app)

    # Registrar blueprints
    from app.controllers.auth_controller import auth_bp
    from app.controllers.admin_controller import admin_bp
    from app.controllers.room_controller import room_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(room_bp)

    # (Opcional) Inicializar datos por defecto si Redis estÃ¡ vacÃ­o
    from app.models.auth import Auth
    from app.models.game_data import GameData
    if redis_client: # Solo si la conexiÃ³n fue exitosa
        Auth.initialize_defaults(redis_client)
        GameData.initialize_defaults(redis_client)
        print("VerificaciÃ³n de datos iniciales de Redis completada.")

    return app

# Ahora puedes importar redis_client desde app en otros mÃ³dulos
# from app import redis_client