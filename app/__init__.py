from flask import Flask
from flask_socketio import SocketIO
from .config import get_config

# Inicializar SocketIO antes de la aplicación
socketio = SocketIO(cors_allowed_origins="*")

def create_app():
    """Función para crear y configurar la aplicación Flask"""
    app = Flask(__name__, 
                template_folder='views/templates',
                static_folder='static')
    
    # Aplicar configuración
    app_config = get_config()
    app.config.from_object(app_config)
    
    # Inicializar SocketIO con la aplicación
    socketio.init_app(app)
    
    # Registrar blueprints
    from app.controllers.auth_controller import auth_bp
    from app.controllers.admin_controller import admin_bp
    from app.controllers.room_controller import room_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(room_bp)
    
    return app
