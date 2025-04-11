# wsgi.py
from app import create_app

# Crea la aplicación Flask/SocketIO
app = create_app()

# NO llames a socketio.run(app) aquí cuando uses Gunicorn
# Simplemente asegúrate de que 'app' esté definido.
# Gunicorn usarÃ¡ este objeto 'app' cuando lo inicies con 'gunicorn wsgi:app ...'

# Puedes mantener esto si quieres poder ejecutar 'python wsgi.py' directamente
# para pruebas locales (aunque 'run.py' es mejor para eso),
# pero Gunicorn no lo usarÃ¡.
if __name__ == '__main__':
    # Esto es mÃ¡s para el servidor de desarrollo de Flask/SocketIO
    # No se recomienda para producciÃ³n con Gunicorn/Gevent
    print("Iniciando servidor de desarrollo desde wsgi.py (NO RECOMENDADO PARA PRODUCCIÓN)")
    from app import socketio # Importar socketio especÃ­ficamente aquÃ­
    socketio.run(app, host='0.0.0.0', port=5000)