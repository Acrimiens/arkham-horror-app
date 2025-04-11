# Arkham Horror - Aplicación para el 2º Aniversario de Ignota Alicante

Aplicación web para gestionar el juego de mesa Arkham Horror durante el evento del 2º aniversario de Ignota Alicante.

## Estructura del proyecto (MVC)

El proyecto sigue una estructura similar al patrón Modelo-Vista-Controlador:

```
/
├── app/                            # Carpeta principal de la aplicación
│   ├── __init__.py                 # Inicializa la aplicación Flask
│   ├── config.py                   # Configuraciones de la aplicación
│   ├── models/                     # Modelos (datos y lógica de negocio)
│   │   ├── __init__.py
│   │   ├── auth.py                 # Modelo para autenticación y acceso
│   │   └── game_data.py            # Modelo para datos del juego
│   ├── controllers/                # Controladores (lógica de rutas)
│   │   ├── __init__.py
│   │   ├── auth_controller.py      # Controlador para autenticación
│   │   ├── admin_controller.py     # Controlador para panel de administración
│   │   └── room_controller.py      # Controlador para salas y eras
│   └── views/                      # Vistas (templates)
│       └── templates/              # Plantillas HTML
├── requirements.txt                # Dependencias
├── wsgi.py                         # Punto de entrada para producción
├── run.py                          # Script para ejecutar en desarrollo
└── render.yaml                     # Configuración para deploy en Render
```

## Requisitos

- Python 3.9+
- Flask
- Flask-SocketIO
- Pillow
- qrcode
- gunicorn (producción)
- gevent-websocket (producción)

## Instalación y ejecución en desarrollo

1. Clonar el repositorio:
```bash
git clone <repo-url>
cd arkham-horror-app
```

2. Crear un entorno virtual e instalar dependencias:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Ejecutar la aplicación en modo desarrollo:
```bash
python run.py
```

4. Acceder a la aplicación en:
```
http://localhost:5000
```

## Despliegue en producción (Render)

1. Subir el código a un repositorio Git (GitHub, GitLab, etc.)

2. Crear un nuevo Web Service en Render:
   - Conectar tu repositorio Git
   - Seleccionar el tipo de entorno: Python
   - Dejar que Render detecte automáticamente el comando de construcción y arranque basado en render.yaml

3. O configurar manualmente:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 wsgi:app`
   - Variables de entorno:
     - `RENDER`: `true`
     - `FLASK_ENV`: `production`

## Acceso a la aplicación

### Acceso como mesa de juego
- Usar el código de mesa proporcionado (formato: mesa01, mesa02, etc.)
- O escanear el código QR generado por el administrador

### Acceso como administrador
- Usuario: admin1, admin2, admin3, admin4, o admin5
- Contraseña: clave1, clave2, clave3, clave4, o clave5 respectivamente

## Características principales

- Autenticación para mesas y administradores
- Panel de administración para gestionar grupos y mesas
- Generación de códigos QR para acceso rápido
- Comunicación en tiempo real mediante WebSockets
- Gestión de recursos, anuncios y contadores del juego
