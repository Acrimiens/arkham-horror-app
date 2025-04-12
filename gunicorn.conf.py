# gunicorn.conf.py

# Tipo de worker
# ¡Esta es la configuración clave!
worker_class = 'gevent'

# Número de workers (empezamos con 1, luego puedes aumentar)
workers = 1

# Dirección y puerto en los que Gunicorn escucha
# Render normalmente expone en el puerto 10000 internamente
bind = '0.0.0.0:10000'

# Nivel de log (puedes cambiar a 'debug' si necesitas más info)
loglevel = 'info'

# Timeout del worker (puedes ajustarlo si es necesario, pero 30s es razonable)
timeout = 30

# (Opcional) Archivos de log si quieres registrar en archivos dentro del contenedor
# accesslog = '-' # '-' significa stdout
# errorlog = '-'  # '-' significa stderr

# (Opcional) Recargar workers si el código cambia (útil en desarrollo, NO recomendado en producción)
# reload = False