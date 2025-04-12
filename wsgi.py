# wsgi.py

# --- Monkey Patching de Gevent ---
from gevent import monkey
monkey.patch_all()
# ---------------------------------

from app import create_app

# Crea la aplicación Flask/SocketIO
app = create_app()

# Gunicorn usarÃ¡ este objeto 'app'
# No aÃ±adir nada mÃ¡s aquÃ­