import os
from app import create_app, socketio

app = create_app()

if __name__ == '__main__':
    # En desarrollo usamos debug=True
    socketio.run(app, debug=True, host='0.0.0.0')
