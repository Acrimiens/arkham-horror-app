# wsgi.py

# --- Monkey Patching de Gevent ---
# ¡IMPORTANTE! Debe estar ANTES de otras importaciones (especialmente socket, ssl, flask, etc.)
from gevent import monkey
monkey.patch_all()
# ---------------------------------

from app import create_app

# Crea la aplicación Flask/SocketIO (esto ahora usarÃ¡ las versiones parcheadas)
app = create_app()

# Gunicorn usarÃ¡ este objeto 'app'
# No llamar a socketio.run() aquÃ­ para producciÃ³n con Gunicorn/Gevent

# (Opcional) Bloque para ejecuciÃ³n directa (desarrollo/testing)
if __name__ == '__main__':
    print("Iniciando servidor de desarrollo desde wsgi.py (monkey-patched)")
    # Importar socketio DESPUÉS del parcheo y creaciÃ³n de app
    from app import socketio
    # Usar socketio.run con el host/puerto apropiado para desarrollo
    socketio.run(app, host='0.0.0.0', port=5000, debug=True) # Puedes aÃ±adir debug aquÃ­ para desarrollo