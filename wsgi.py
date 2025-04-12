# wsgi.py

# --- Monkey Patching de Gevent ---
# ¡MUY IMPORTANTE! Debe estar ANTES de todo lo demás.
from gevent import monkey
monkey.patch_all()
# ---------------------------------

from app import create_app

# Crea la aplicación Flask/SocketIO (usará versiones parcheadas)
app = create_app()

# Gunicorn usarÃ¡ este objeto 'app'

# (Opcional) Ejecución directa para desarrollo
if __name__ == '__main__':
    print("Iniciando servidor de desarrollo desde wsgi.py (monkey-patched)")
    from app import socketio
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)