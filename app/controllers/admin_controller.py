from flask import Blueprint, render_template, redirect, url_for, session, flash, request, jsonify, send_file
from app.models.auth import Auth
from app.models.game_data import GameData
from app import socketio
import qrcode
import io
import base64
from PIL import Image, ImageDraw, ImageFont

# Crear blueprint para rutas de administración
admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin_panel')
def panel():
    """Página principal del panel de administración"""
    # Verificar que sea un admin
    if 'is_admin' not in session or not session['is_admin']:
        flash('No tienes permiso para acceder al panel de administración.', 'error')
        return redirect(url_for('auth.index'))
    
    return render_template('admin_panel.html', 
                          rooms=Auth.get_all_rooms(), 
                          mesa_access_codes=Auth.get_all_mesa_codes())

@admin_bp.route('/add_room', methods=['POST'])
def add_room():
    """Añade una nueva sala/grupo"""
    # Verificar si es admin
    if not ('is_admin' in session and session['is_admin']):
        flash('No tienes permiso para añadir grupos.', 'error')
        return redirect(url_for('auth.index'))
    
    # Añadir nueva sala
    new_room = Auth.add_room()
    
    # Emitir evento de actualización de salas a todos los administradores
    socketio.emit('room_update', {
        'rooms': Auth.get_all_rooms()
    }, room='admin_room')
    
    flash(f'Grupo {new_room["id"]} creado con éxito junto con sus códigos de mesa.', 'success')
    return redirect(url_for('admin.panel'))

@admin_bp.route('/reset_server', methods=['POST'])
def reset_server():
    """Resetea todos los datos del servidor"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        flash('No tienes permiso para realizar esta acción.', 'error')
        return redirect(url_for('auth.index'))
    
    # Resetear todos los datos del juego
    GameData.reset_all_data()
    
    # Emitir evento de actualización global
    socketio.emit('server_reset', {
        'message': 'El servidor ha sido reiniciado completamente'
    })
    
    flash('El servidor ha sido reiniciado completamente.', 'success')
    
    # Determinar si la solicitud fue AJAX o normal
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'El servidor ha sido reiniciado completamente'
        })
    else:
        return redirect(url_for('admin.panel'))

@admin_bp.route('/reset_perdicion_cycle', methods=['POST'])
def reset_perdicion_cycle():
    """Reinicia el ciclo de perdición"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    # Reiniciar el ciclo y el contador global
    global_counters = GameData.initialize_global_counters()
    global_counters["perdicion_cycle"] = 1
    global_counters["perdicion"] = 0
    
    # Reiniciar el contador de perdición en todas las salas
    for key in GameData._game_data:
        if key.startswith('room_'):
            room_id = int(key.split('_')[1])
            # Obtener los datos de columna de la sala
            column_totals = GameData.initialize_room_column_totals(room_id)
            
            # Reiniciar el contador de perdición en todas las eras
            for era in ["pasado", "presente", "futuro"]:
                column_totals[era]["perdicion"] = 0
                
                # Emitir evento para actualizar la interfaz en todos los clientes de esta sala y era
                socketio.emit('column_resource_update', {
                    'room_id': room_id,
                    'era': era,
                    'columnTotals': column_totals[era],
                    'perdicionCycle': global_counters["perdicion_cycle"]
                }, room=f"room_{room_id}")
    
    # Emitir evento global a todos los clientes conectados
    socketio.emit('global_counter_update', {
        'globalTotals': global_counters,
        'enablePerdicionControls': True
    })
    
    return jsonify({
        "success": True,
        "message": "Ciclo de perdición reiniciado correctamente",
        "globalTotals": global_counters,
        "enablePerdicionControls": True
    })

@admin_bp.route('/generate_qr/<mesa_code>', methods=['GET'])
def generate_qr(mesa_code):
    """Genera un código QR para una mesa específica"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        flash('No tienes permiso para realizar esta acción.', 'error')
        return redirect(url_for('auth.index'))
    
    # Verificar que el código de mesa exista
    mesa_access_codes = Auth.get_all_mesa_codes()
    if mesa_code not in mesa_access_codes:
        flash('Código de mesa inválido.', 'error')
        return redirect(url_for('admin.panel'))
    
    # URL del sitio
    site_url = request.url_root
    # URL completa para el código QR (eliminar la barra al final si existe)
    if site_url.endswith('/'):
        site_url = site_url[:-1]
    
    # Texto que se convertirá en código QR
    qr_data = f"{site_url}?code={mesa_code}"
    
    # Crear el objeto QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    # Agregar los datos al QR
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    # Crear la imagen QR y asegurarse de que esté en el formato correcto
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')  # Asegurarse de que esté en modo RGB
    
    # Obtener información de la mesa
    mesa_info = mesa_access_codes[mesa_code]
    group_id = mesa_info["group"]
    era = mesa_info["era"]
    
    # Crear una imagen más grande con espacio para texto
    img_width, img_height = qr_img.size
    new_img = Image.new('RGB', (img_width, img_height + 60), color='white')
    
    # Pegar el código QR en la nueva imagen
    new_img.paste(qr_img, (0, 0))
    
    # Agregar texto debajo del código QR
    draw = ImageDraw.Draw(new_img)
    
    # Intentar usar una fuente predeterminada, o usar el texto simple si no está disponible
    try:
        # En sistemas Linux
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except IOError:
        try:
            # En sistemas Windows
            font = ImageFont.truetype("arial.ttf", 18)
        except IOError:
            # Si no hay fuentes disponibles, usar fuente predeterminada
            font = ImageFont.load_default()
    
    # Texto para mostrar (código de mesa, grupo y era)
    mesa_name = "Mesa " + mesa_code[4:].zfill(2).upper()
    group_name = f"Grupo {group_id}"
    era_name = era.capitalize()
    
    # Dibujar el texto
    draw.text((10, img_height + 5), mesa_name, font=font, fill='black')
    draw.text((10, img_height + 25), f"{group_name} - {era_name}", font=font, fill='black')
    
    # Guardar la imagen en un buffer de bytes
    img_byte_array = io.BytesIO()
    new_img.save(img_byte_array, format='PNG')
    img_byte_array.seek(0)
    
    # Enviar la imagen como respuesta
    return send_file(
        img_byte_array,
        mimetype='image/png',
        as_attachment=True,
        download_name=f'qr_{mesa_code}.png'
    )

@admin_bp.route('/print_all_qr', methods=['GET'])
def print_all_qr():
    """Genera todos los códigos QR en una sola página para imprimir"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        flash('No tienes permiso para realizar esta acción.', 'error')
        return redirect(url_for('auth.index'))
    
    # URL del sitio
    site_url = request.url_root
    # URL completa para el código QR (eliminar la barra al final si existe)
    if site_url.endswith('/'):
        site_url = site_url[:-1]
    
    # Generar códigos QR para todas las mesas
    mesa_qr_data = {}
    mesa_access_codes = Auth.get_all_mesa_codes()
    
    for mesa_code in mesa_access_codes:
        # Texto que se convertirá en código QR
        qr_data = f"{site_url}?code={mesa_code}"
        
        # Crear el objeto QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # Agregar los datos al QR
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Crear la imagen QR y asegurarse de que esté en el formato correcto
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.convert('RGB')  # Asegurarse de que esté en modo RGB
        
        # Obtener información de la mesa
        mesa_info = mesa_access_codes[mesa_code]
        group_id = mesa_info["group"]
        era = mesa_info["era"]
        
        # Crear una imagen más grande con espacio para texto
        img_width, img_height = qr_img.size
        new_img = Image.new('RGB', (img_width, img_height + 60), color='white')
        
        # Pegar el código QR en la nueva imagen
        new_img.paste(qr_img, (0, 0))
        
        # Agregar texto debajo del código QR
        draw = ImageDraw.Draw(new_img)
        
        # Intentar usar una fuente predeterminada
        try:
            # En sistemas Linux
            font = ImageFont.truetype("DejaVuSans.ttf", 18)
        except IOError:
            try:
                # En sistemas Windows
                font = ImageFont.truetype("arial.ttf", 18)
            except IOError:
                # Si no hay fuentes disponibles, usar fuente predeterminada
                font = ImageFont.load_default()
        
        # Texto para mostrar (código de mesa, grupo y era)
        mesa_name = "Mesa " + mesa_code[4:].zfill(2).upper()
        group_name = f"Grupo {group_id}"
        era_name = era.capitalize()
        
        # Dibujar el texto
        draw.text((10, img_height + 5), mesa_name, font=font, fill='black')
        draw.text((10, img_height + 25), f"{group_name} - {era_name}", font=font, fill='black')
        
        # Convertir la imagen a base64 para mostrarla en HTML
        img_byte_array = io.BytesIO()
        new_img.save(img_byte_array, format='PNG')
        img_byte_array.seek(0)
        img_base64 = base64.b64encode(img_byte_array.getvalue()).decode('utf-8')
        
        # Guardar los datos del QR
        mesa_qr_data[mesa_code] = {
            'img_base64': img_base64,
            'mesa_name': mesa_name,
            'group_name': group_name,
            'era_name': era_name
        }
    
    # Renderizar la página con todos los códigos QR
    return render_template('print_qr.html', mesa_qr_data=mesa_qr_data)
