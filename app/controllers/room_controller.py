from flask import Blueprint, render_template, redirect, url_for, session, flash, request, jsonify
from app.models.auth import Auth
from app.models.game_data import GameData
from app import socketio
from flask_socketio import emit, join_room, leave_room
import traceback

# Crear blueprint para rutas de sala y eras
room_bp = Blueprint('game', __name__)

# Nueva función para verificar si se cumplen las tres condiciones en todas las mesas
def check_victory_conditions():
    """Verifica si todas las mesas cumplen las tres condiciones de victoria"""
    try:
        # Obtener todas las salas con datos
        room_ids = []
        for key in GameData._game_data.keys():
            if key.startswith("room_"):
                room_id = int(key.split("_")[1])
                room_ids.append(room_id)
        
        if not room_ids:
            return False  # No hay salas para verificar
        
        # Verificar condiciones para cada sala
        for room_id in room_ids:
            room_data = GameData.initialize_room_data(room_id)
            column_totals = GameData.initialize_room_column_totals(room_id)
            
            # 1. Verificar si Biff ha sido derrotado en todas las eras
            for era in ["pasado", "presente", "futuro"]:
                if not room_data["biff_disabled"].get(era, False):
                    return False  # Biff no ha sido derrotado en todas las eras
            
            # 2. Verificar si todas las eras tienen fluzo = 81
            for era in ["pasado", "presente", "futuro"]:
                if "fluzo" not in column_totals[era] or column_totals[era]["fluzo"] != 81:
                    return False  # No todas las eras tienen fluzo = 81
            
            # 3. Verificar si "Un noble legado" está marcado en todas las eras
            # Identificar qué índice corresponde al anuncio de "Un noble legado" en cada era
            noble_legado_indices = {
                "pasado": 5,  # índice 5 en la era pasado
                "presente": 4,  # índice 4 en la era presente
                "futuro": 3    # índice 3 en la era futuro
            }
            
            for era, idx in noble_legado_indices.items():
                if not room_data["progress"][era][idx]:
                    return False  # "Un noble legado" no está marcado en todas las eras
        
        # Si llegamos aquí, todas las condiciones se cumplen en todas las salas
        return True
    
    except Exception as e:
        print(f"Error al verificar condiciones de victoria: {str(e)}")
        traceback.print_exc()
        return False

@room_bp.route('/room/<int:room_id>')
def room(room_id):
    """Vista de selección de eras en una sala"""
    # Solo los administradores pueden acceder a la vista de selección de eras
    if not ('is_admin' in session and session['is_admin']):
        flash('No tienes permiso para acceder a esta página.', 'error')
        
        # Si el usuario tiene una era asignada, redirigirlo allí
        if 'assigned_group' in session and 'assigned_era' in session:
            return redirect(url_for('game.era', room_id=session['assigned_group'], era=session['assigned_era']))
        else:
            return redirect(url_for('auth.index'))
    
    room = Auth.get_room_by_id(room_id)
    if not room:
        return redirect(url_for('auth.index'))
    
    return render_template('room.html', room=room, is_admin='is_admin' in session and session['is_admin'])
@room_bp.route('/era/<int:room_id>/<era>')
def era(room_id, era):
    """Vista de una era específica en una sala"""
    # Verificar acceso
    if 'is_admin' in session and session['is_admin']:
        # Los admins pueden acceder a cualquier era de cualquier grupo
        pass
    elif 'assigned_group' in session and 'assigned_era' in session:
        # Verificar que el usuario solo pueda acceder a su grupo y era asignada
        if session['assigned_group'] != room_id or session['assigned_era'] != era:
            flash('No tienes permiso para acceder a este grupo o era.', 'error')
            return redirect(url_for('game.era', room_id=session['assigned_group'], era=session['assigned_era']))
    else:
        flash('No tienes permiso para acceder a esta página.', 'error')
        return redirect(url_for('auth.index'))
    
    if era not in ["pasado", "presente", "futuro"]:
        if 'assigned_era' in session:
            return redirect(url_for('game.era', room_id=room_id, era=session['assigned_era']))
        else:
            return redirect(url_for('auth.index'))
    
    room = Auth.get_room_by_id(room_id)
    if not room:
        return redirect(url_for('auth.index'))
    
    # Inicializar o cargar datos de la sala
    room_data = GameData.initialize_room_data(room_id)
    progress = room_data["progress"]
    resources = room_data["resources"]
    biff_defeats = room_data["biff_defeats"]
    biff_disabled = room_data["biff_disabled"]  # Añadir campo de desactivación de Biff
    
    # Verificar cuáles botones están disponibles según las dependencias
    available_buttons = []
    for i in range(len(GameData.button_info[era])):
        is_available = True
        for dep in GameData.button_dependencies[era][i]:
            dep_era, dep_idx = dep.split('-')
            dep_idx = int(dep_idx)
            if not progress[dep_era][dep_idx]:
                is_available = False
                break
        available_buttons.append(is_available)
    
    # Obtener el nombre de la mesa si aplica
    mesa_name = ""
    if 'mesa_code' in session:
        mesa_code = session['mesa_code']
        # Convertir mesa01 a Mesa 01
        mesa_name = "Mesa " + mesa_code[4:].zfill(2).upper()
    
    # Obtener el ciclo actual de perdición
    global_counters = GameData.initialize_global_counters()
    perdicion_cycle = global_counters["perdicion_cycle"]
    
    # Inicializar columnas de la sala
    column_totals = GameData.initialize_room_column_totals(room_id)
    
    # Verificar condiciones de victoria para R1
    victory_conditions_met = check_victory_conditions()
    
    # Añadir al contexto de la plantilla
    return render_template('era.html', 
                          room=room, 
                          era=era, 
                          progress=progress,
                          button_info=GameData.button_info[era],
                          available_buttons=available_buttons,
                          resources=resources,
                          biff_defeats=biff_defeats[era],
                          biff_disabled=biff_disabled[era],
                          mesa_name=mesa_name,
                          perdicion_cycle=perdicion_cycle,
                          column_totals=column_totals[era],
                          victory_conditions_met=victory_conditions_met,
                          is_admin='is_admin' in session and session['is_admin'])
@room_bp.route('/toggle_button/<int:room_id>/<era>/<int:button_idx>', methods=['POST'])
def toggle_button(room_id, era, button_idx):
    """Activa o desactiva un botón de anuncio"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        flash('No tienes permiso para realizar esta acción.', 'error')
        return redirect(url_for('auth.index'))
    
    if era not in ["pasado", "presente", "futuro"]:
        if 'assigned_era' in session:
            return redirect(url_for('game.era', room_id=room_id, era=session['assigned_era']))
        else:
            return redirect(url_for('auth.index'))
    
    try:
        # Inicializar o cargar datos de la sala
        room_data = GameData.initialize_room_data(room_id)
        
        # Determinar si estamos activando o desactivando el botón
        is_activating = not room_data["progress"][era][button_idx]
        
        # Si es admin, permitir activar cualquier botón sin restricciones
        if 'is_admin' in session and session['is_admin']:
            # Si estamos desactivando, desactivar también los dependientes
            if not is_activating:
                # Primero, cambiamos el estado del botón principal
                room_data["progress"][era][button_idx] = False
                
                # Luego desactivamos todos los que dependen de este
                deactivate_dependent_buttons(room_data["progress"], f"{era}-{button_idx}")
            else:
                # Si estamos activando, simplemente activamos este botón
                room_data["progress"][era][button_idx] = True
        else:
            # Verificar si se cumplen las dependencias para activar
            if is_activating:
                can_toggle = True
                for dep in GameData.button_dependencies[era][button_idx]:
                    dep_era, dep_idx = dep.split('-')
                    dep_idx = int(dep_idx)
                    if not room_data["progress"][dep_era][dep_idx]:
                        can_toggle = False
                        break
                
                if can_toggle:
                    # Cambiar el estado del botón (activar)
                    room_data["progress"][era][button_idx] = True
            else:
                # Si está desactivando, verificar y desactivar dependientes
                room_data["progress"][era][button_idx] = False
                deactivate_dependent_buttons(room_data["progress"], f"{era}-{button_idx}")
        
        # Verificar todos los botones en todas las eras para determinar las dependencias correctamente
        all_available_buttons = get_available_buttons(room_data["progress"])
        
        # Verificar si se han cumplido las condiciones de victoria después del cambio
        victory_conditions_met = check_victory_conditions()
        
        # Emitir evento de actualización a todos los clientes en la sala
        socketio.emit('button_update', {
            'room_id': room_id,
            'era': era,
            'progress': room_data["progress"],
            'available_buttons': all_available_buttons,
            'button_idx': button_idx,  # Enviar qué botón específico se ha cambiado
            'is_activating': is_activating  # Indicar si se está activando o desactivando
        }, room=f"room_{room_id}")
        
        # Si se cumplen las condiciones de victoria, emitir evento especial
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })
        
        # Determinar si la solicitud fue AJAX o normal
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Botón actualizado correctamente',
                'progress': room_data["progress"],
                'available_buttons': all_available_buttons,
                'victory_conditions_met': victory_conditions_met
            })
        else:
            return redirect(url_for('game.era', room_id=room_id, era=era))
    except Exception as e:
        error_msg = f"Error al actualizar botón: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': error_msg
            })
        else:
            flash(error_msg, 'error')
            return redirect(url_for('game.era', room_id=room_id, era=era))
@room_bp.route('/update_resources/<int:room_id>/<era>', methods=['POST'])
def update_resources(room_id, era):
    """Actualiza los recursos de una era"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Obtener datos de recursos del POST
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Datos no proporcionados o formato incorrecto"})
            
        resource_amount = data.get('amount', 0)
        
        # Inicializar o cargar datos de la sala
        room_data = GameData.initialize_room_data(room_id)
        
        # Actualizar los recursos
        room_data["resources"][era] += resource_amount
        room_data["resources"]["total"] += resource_amount
        
        # Emitir evento de actualización de recursos a todos los clientes en la sala
        socketio.emit('resource_update', {
            'room_id': room_id,
            'resources': room_data["resources"]
        }, room=f"room_{room_id}")
        
        return jsonify({
            "success": True,
            "resources": room_data["resources"]
        })
    except Exception as e:
        error_msg = f"Error al actualizar recursos: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

# Función interna para ajustar todos los valores de fluzo
def adjust_all_fluzo_values_internal():
    """Ajusta los valores de fluzo en todas las salas según las reglas especificadas (función interna)"""
    try:
        # Obtener todas las salas con datos
        room_ids = []
        for key in GameData._game_data.keys():
            if key.startswith("room_"):
                room_id = int(key.split("_")[1])
                room_ids.append(room_id)
        
        # Para cada sala, ajustar los valores de fluzo en todas las eras
        for room_id in room_ids:
            for era in ["pasado", "presente", "futuro"]:
                # Obtener los datos de la sala
                column_totals = GameData.initialize_room_column_totals(room_id)
                
                # Asegurarse de que fluzo existe en los datos
                if "fluzo" not in column_totals[era]:
                    column_totals[era]["fluzo"] = 0
                
                # Obtener el valor actual
                current_fluzo = column_totals[era]["fluzo"]
                new_fluzo = current_fluzo
                
                # Aplicar las reglas de ajuste:
                if current_fluzo > 86:
                    new_fluzo = current_fluzo - 10
                elif current_fluzo < 76:
                    new_fluzo = current_fluzo + 10
                elif current_fluzo >= 80 and current_fluzo <= 82:
                    new_fluzo = current_fluzo - 5
                
                # Solo actualizar si el valor ha cambiado
                if new_fluzo != current_fluzo:
                    # Actualizar el valor en la sala
                    column_totals[era]["fluzo"] = new_fluzo
                    
                    # Guardar los cambios
                    GameData.save_column_totals(room_id, column_totals)
                    
                    # Emitir evento de actualización
                    socketio.emit('fluzo_update', {
                        'room_id': room_id,
                        'era': era,
                        'fluzoTotal': new_fluzo,
                        'fluzoValue': 0,  # La caja siempre muestra 0
                    }, room=f"room_{room_id}")
        
        # Verificar si se cumplen las condiciones de victoria después de ajustar
        victory_conditions_met = check_victory_conditions()
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })
            
        return True
    except Exception as e:
        print(f"Error al ajustar valores de fluzo internamente: {str(e)}")
        traceback.print_exc()
        return False
@room_bp.route('/adjust_all_fluzo_values', methods=['POST'])
def adjust_all_fluzo_values():
    """Ajusta los valores de fluzo en todas las salas según las reglas especificadas"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    try:
        success = adjust_all_fluzo_values_internal()
        
        if success:
            # Verificar si se cumplen las condiciones de victoria después del ajuste
            victory_conditions_met = check_victory_conditions()
            
            return jsonify({
                "success": True,
                "message": "Valores de fluzo ajustados en todas las salas",
                "victory_conditions_met": victory_conditions_met
            })
        else:
            return jsonify({
                "success": False,
                "error": "Error al ajustar los valores de fluzo"
            })
    except Exception as e:
        error_msg = f"Error al ajustar valores de fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

@room_bp.route('/biff_defeat/<int:room_id>/<era>', methods=['POST'])
def biff_defeat(room_id, era):
    """Incrementa el contador de derrotas de Biff"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Inicializar o cargar datos de la sala
        room_data = GameData.initialize_room_data(room_id)
        
        # Obtener el ciclo actual de perdición
        global_counters = GameData.initialize_global_counters()
        current_cycle = global_counters["perdicion_cycle"]
        is_plan_1a = (current_cycle == 1)
        
        # Si el botón ya está desactivado, no hacer nada
        if room_data["biff_disabled"][era]:
            return jsonify({
                "success": True,
                "defeats": room_data["biff_defeats"][era],
                "disable_button": True,
                "message": "Biff Tannen ya ha sido añadido a la zona de victoria."
            })
        
        # Obtener el número actual de derrotas y sumamos 1 para obtener la nueva cantidad
        current_defeats = room_data["biff_defeats"][era]
        new_defeats = current_defeats + 1
        
        # Determinar el mensaje según el número de derrotas
        biff_message = ""
        # Variable para indicar si se debe desactivar el botón
        disable_button = False
        
        if new_defeats == 1:
            biff_message = "\"¡Hey, McFly!\" Biff Tannen aparece agotado. Si en la partida esta Marty McFly, aparece en el Lugar de Marty, ignorando sus instrucciones de Aparición"
        elif new_defeats == 2:
            biff_message = "\"¿Te estoy haciendo perder el tiempo?\": en lugar de derrotar a Biff Tannen, agótalo. No se considera que haya sido derrotado."
        elif new_defeats == 3:
            biff_message = "\"¿Te estoy despistando?\": cada investigador debe colocar una de sus pistas sobre su Lugar, o bien recibir 1 punto de horror."
        elif new_defeats == 4:
            biff_message = "\"¡Llevo mucho tiempo preparando esto!\": Decides seguir el rastro que ha dejado Biff durante sus viajes en el tiempo. Coloca 1 pista (de la reserva de fichas) sobre cada Lugar en juego."
        elif new_defeats >= 5:
            # A partir de la quinta derrota (incluida)
            if not is_plan_1a:
                # Si NO estamos en Plan 1a, siempre mostrar este mensaje
                biff_message = "Dale la vuelta a Biff Tannen y añadelo a la zona de victoria."
                # Indicar que se debe desactivar el botón
                disable_button = True
                # Guardar el estado de desactivación
                room_data["biff_disabled"][era] = True
            else:
                # Si estamos en Plan 1a, depende del número exacto de derrotas
                if new_defeats == 5:
                    biff_message = "\"Deja de golpearte, deja de golpearte, deja de golpearte\": Realiza una prueba de <span style=\"font-family: 'AHLCG';\">S</span>(2). Por cada punto que falte para tener éxito, recibe 1 punto de daño."
                elif new_defeats == 6:
                    biff_message = "\"¡Tenemos tiempo de sobra!\": añade 1 ficha de Perdición al Plan en curso."
                elif new_defeats == 7:
                    biff_message = "\"¡Ya no vas a necesitar esto!\": El investigador que ha derrotado a Biff descarta 1 Apoyo que controle, a ser posible un Apoyo usado para derrotar a Biff Tannen."
                else:  # 8 o más derrotas
                    # Seleccionar mensaje aleatorio entre los 3 disponibles
                    import random
                    random_messages = [
                        "\"Deja de golpearte, deja de golpearte, deja de golpearte\": Realiza una prueba de <span style=\"font-family: 'AHLCG';\">S</span>(2). Por cada punto que falte para tener éxito, recibe 1 punto de daño.",
                        "\"¡Tenemos tiempo de sobra!\": añade 1 ficha de Perdición al Plan en curso.",
                        "\"¡Ya no vas a necesitar esto!\": El investigador que ha derrotado a Biff descarta 1 Apoyo que controle, a ser posible un Apoyo usado para derrotar a Biff Tannen."
                    ]
                    biff_message = random.choice(random_messages)
        
        # Incrementar el contador de derrotas de Biff (sin límite)
        room_data["biff_defeats"][era] += 1
        
        # Verificar si se cumplen las condiciones de victoria después del cambio
        victory_conditions_met = check_victory_conditions() if disable_button else False
        
        # Emitir evento de actualización a todos los clientes en la sala
        socketio.emit('biff_update', {
            'room_id': room_id,
            'era': era,
            'defeats': room_data["biff_defeats"][era],
            'message': biff_message,  # Añadir el mensaje a la respuesta
            'disable_button': disable_button  # Indicar si se debe desactivar el botón
        }, room=f"room_{room_id}")
        
        # Si se cumplen las condiciones de victoria, emitir evento especial
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })
        
        return jsonify({
            "success": True,
            "defeats": room_data["biff_defeats"][era],
            "message": biff_message,  # Añadir el mensaje a la respuesta
            "disable_button": disable_button,  # Indicar si se debe desactivar el botón
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al actualizar derrotas de Biff: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})
@room_bp.route('/update_column_resource/<int:room_id>/<era>/<column>', methods=['POST'])
def update_column_resource(room_id, era, column):
    """Actualiza un contador de columna específico"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    if column not in ["perdicion", "reserva", "fluzo"]:  # Añadido fluzo a las columnas permitidas
        return jsonify({"success": False, "error": "Columna inválida"})
    
    try:
        # Obtener datos del POST
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Datos no proporcionados o formato incorrecto"})
            
        amount = data.get('amount', 0)
        
        # Inicializar datos de la sala y contadores
        room_data = GameData.initialize_room_data(room_id)
        column_totals = GameData.initialize_room_column_totals(room_id)
        global_counters = GameData.initialize_global_counters()
        
        # MODIFICACIÓN: Lógica para valores negativos en Perdición
        if column == "perdicion" and amount < 0:
            # Verificar que el valor global no se vuelva negativo
            new_global_value = global_counters["perdicion"] + amount
            
            if new_global_value < 0:
                # Limitar la reducción para que el total sea 0
                amount = -global_counters["perdicion"]
                new_global_value = 0
        
        # Variable para controlar si estamos completando un ciclo
        cycle_completed = False
        notification = None
        
        # Lógica especial para perdición
        if column == "perdicion":
            # Si estamos en el ciclo 3 y ya ha terminado, no permitimos más cambios
            if global_counters["perdicion_cycle"] > 3:
                return jsonify({
                    "success": False,
                    "error": "El contador de perdición ha completado todos sus ciclos."
                })
            
            # Calculamos el nuevo valor después del cambio
            new_perdicion_value = global_counters["perdicion"] + amount
            
            # Verificar que el nuevo valor no sea negativo
            if new_perdicion_value < 0:
                new_perdicion_value = 0
                # Ajustar la cantidad para que el contador de la sala también se actualice correctamente
                amount = -global_counters["perdicion"]
                
            # Verificar límites según el ciclo actual
            cycle_limits = {1: 5, 2: 4, 3: 5}
            current_cycle = global_counters["perdicion_cycle"]
            
            # Si alcanzamos o superamos el límite del ciclo actual
            if current_cycle in cycle_limits and new_perdicion_value >= cycle_limits[current_cycle]:
                # Enviamos una notificación según el ciclo
                notifications = {
                    1: "Haz avanzar al Plan 1b",
                    2: "Haz avanzar al Plan 1b. El valor de Fluzo ha sido alterado",
                    3: "(->R2)"
                }
                notification = notifications[current_cycle]
                
                # Actualizamos el ciclo y reseteamos el contador global
                global_counters["perdicion_cycle"] += 1
                global_counters["perdicion"] = 0
                
                # Marcamos que se completó un ciclo
                cycle_completed = True
                
                # Reiniciamos los contadores de perdición para todas las salas
                # 1. Reiniciamos los contadores de la sala actual
                for reset_era in ["pasado", "presente", "futuro"]:
                    column_totals[reset_era]["perdicion"] = 0
                
                # 2. Guardar en la sala actual
                GameData.save_column_totals(room_id, column_totals)
                
                # 3. Reiniciar contadores de perdición en TODAS las salas
                GameData.reset_perdicion_all_rooms()
                
                # 4. Si estamos pasando del ciclo 2 al ciclo 3, ajustar valores de fluzo
                if current_cycle == 2:
                    # Llamar a la función para ajustar todos los valores de fluzo
                    adjust_all_fluzo_values_internal()
            else:
                # Si no alcanzamos el límite, actualizamos normalmente
                global_counters["perdicion"] = new_perdicion_value
                column_totals[era][column] += amount
        elif column == "fluzo":
            # Para fluzo, simplemente actualizamos el valor en la sala
            column_totals[era][column] += amount
            
            # Verificar si se cumplen las condiciones de victoria después del cambio
            victory_conditions_met = check_victory_conditions()
            
            # Si se cumplen las condiciones de victoria, emitir evento especial
            if victory_conditions_met:
                socketio.emit('victory_conditions_met', {
                    'message': "->R1"
                })
        else:
            # Para otros contadores (reserva) actualizamos normalmente
            # También evitamos valores negativos para la reserva global
            new_value = global_counters[column] + amount
            if new_value < 0:
                new_value = 0
                # Ajustar la cantidad para que el contador de la sala también se actualice correctamente
                amount = -global_counters[column]
            
            global_counters[column] = new_value
            
            # También evitamos valores negativos para el contador de la sala
            new_room_value = column_totals[era][column] + amount
            if new_room_value < 0:
                new_room_value = 0
                amount = -column_totals[era][column]
            
            column_totals[era][column] = new_room_value
        
        # Guardar los cambios
        GameData.save_column_totals(room_id, column_totals)
        GameData.save_global_counters(global_counters)
        
        # Emitir eventos según corresponda
        if cycle_completed:
            # Si se completó un ciclo, enviar un evento a TODAS las mesas en TODAS las salas
            # Este evento forzará la actualización de todos los contadores de perdición
            socketio.emit('perdicion_cycle_completed', {
                'perdicionCycle': global_counters["perdicion_cycle"],
                'notification': notification,
                'originRoom': room_id,
                'originEra': era
            })
        else:
            # Comportamiento normal - enviar solo para la era actual
            socketio.emit('column_resource_update', {
                'room_id': room_id,
                'era': era,
                'columnTotals': column_totals[era],
                'notification': notification,
                'perdicionCycle': global_counters["perdicion_cycle"]
            }, room=f"room_{room_id}")
        
        # Emitir evento global a todos los clientes conectados
        socketio.emit('global_counter_update', {
            'globalTotals': global_counters,
            'notification': notification,
            'cycleCompleted': cycle_completed
        })
        
        # Verificar si se cumplen las condiciones de victoria
        victory_conditions_met = check_victory_conditions()
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })
        
        return jsonify({
            "success": True,
            "columnTotals": column_totals[era],
            "globalTotals": global_counters,
            "notification": notification,
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al actualizar columna: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})
# Controlador para Perdición
@room_bp.route('/update_perdicion/<int:room_id>/<era>', methods=['POST'])
def update_perdicion(room_id, era):
    """Actualiza específicamente el contador de perdición"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Obtener datos del POST
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Datos no proporcionados o formato incorrecto"})
            
        amount = data.get('amount', 0)
        
        # Inicializar datos de la sala y contadores
        room_data = GameData.initialize_room_data(room_id)
        column_totals = GameData.initialize_room_column_totals(room_id)
        global_counters = GameData.initialize_global_counters()
        
        # Lógica para valores negativos en Perdición
        if amount < 0:
            # Verificar que el valor global no se vuelva negativo
            new_global_value = global_counters["perdicion"] + amount
            
            if new_global_value < 0:
                # Limitar la reducción para que el total sea 0
                amount = -global_counters["perdicion"]
                new_global_value = 0
        
        # Variable para controlar si estamos completando un ciclo
        cycle_completed = False
        notification = None
        
        # Si estamos en el ciclo 3 y ya ha terminado, no permitimos más cambios
        if global_counters["perdicion_cycle"] > 3:
            return jsonify({
                "success": False,
                "error": "El contador de perdición ha completado todos sus ciclos."
            })
        
        # Calculamos el nuevo valor después del cambio
        new_perdicion_value = global_counters["perdicion"] + amount
        
        # Verificar que el nuevo valor no sea negativo
        if new_perdicion_value < 0:
            new_perdicion_value = 0
            # Ajustar la cantidad para que el contador de la sala también se actualice correctamente
            amount = -global_counters["perdicion"]
            
        # Verificar límites según el ciclo actual
        cycle_limits = {1: 5, 2: 4, 3: 5}
        current_cycle = global_counters["perdicion_cycle"]
        
        # Si alcanzamos o superamos el límite del ciclo actual
        if current_cycle in cycle_limits and new_perdicion_value >= cycle_limits[current_cycle]:
            # Enviamos una notificación según el ciclo
            notifications = {
                1: "Haz avanzar al Plan 1b",
                2: "Haz avanzar al Plan 1b. El valor de Fluzo ha sido alterado",
                3: "(->R4)"
            }
            notification = notifications[current_cycle]
            
            # Actualizamos el ciclo y reseteamos el contador global
            global_counters["perdicion_cycle"] += 1
            global_counters["perdicion"] = 0
            
            # Marcamos que se completó un ciclo
            cycle_completed = True
            
            # Reiniciamos los contadores de perdición para todas las salas
            # 1. Reiniciamos los contadores de la sala actual
            for reset_era in ["pasado", "presente", "futuro"]:
                column_totals[reset_era]["perdicion"] = 0
            
            # 2. Guardar en la sala actual
            GameData.save_column_totals(room_id, column_totals)
            
            # 3. Reiniciar contadores de perdición en TODAS las salas
            GameData.reset_perdicion_all_rooms()
            
            # 4. Si estamos pasando del ciclo 2 al ciclo 3, ajustar valores de fluzo
            if current_cycle == 2:
                # Llamar a la función para ajustar todos los valores de fluzo
                adjust_all_fluzo_values_internal()
        else:
            # Si no alcanzamos el límite, actualizamos normalmente
            global_counters["perdicion"] = new_perdicion_value
            column_totals[era]["perdicion"] += amount
        
        # Guardar los cambios
        GameData.save_column_totals(room_id, column_totals)
        GameData.save_global_counters(global_counters)
        
        # Emitir eventos según corresponda
        if cycle_completed:
            # Si se completó un ciclo, enviar un evento a TODAS las mesas en TODAS las salas
            socketio.emit('perdicion_cycle_completed', {
                'perdicionCycle': global_counters["perdicion_cycle"],
                'notification': notification,
                'originRoom': room_id,
                'originEra': era
            })
        else:
            # Comportamiento normal - enviar solo para la era actual
            socketio.emit('perdicion_update', {
                'room_id': room_id,
                'era': era,
                'columnTotal': column_totals[era]["perdicion"],
                'notification': notification,
                'perdicionCycle': global_counters["perdicion_cycle"]
            }, room=f"room_{room_id}")
        
        # Emitir evento global a todos los clientes conectados
        socketio.emit('global_perdicion_update', {
            'globalTotal': global_counters["perdicion"],
            'perdicionCycle': global_counters["perdicion_cycle"],
            'notification': notification,
            'cycleCompleted': cycle_completed
        })
        
        # Verificar si se cumplen las condiciones de victoria
        victory_conditions_met = check_victory_conditions()
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })
        
        return jsonify({
            "success": True,
            "columnTotal": column_totals[era]["perdicion"],
            "globalTotal": global_counters["perdicion"],
            "perdicionCycle": global_counters["perdicion_cycle"],
            "notification": notification,
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al actualizar perdición: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})
# Controlador para Reserva
@room_bp.route('/update_reserva/<int:room_id>/<era>', methods=['POST'])
def update_reserva(room_id, era):
    """Actualiza específicamente el contador de reserva"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Obtener datos del POST
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Datos no proporcionados o formato incorrecto"})
            
        amount = data.get('amount', 0)
        
        # Inicializar datos de la sala y contadores
        room_data = GameData.initialize_room_data(room_id)
        column_totals = GameData.initialize_room_column_totals(room_id)
        global_counters = GameData.initialize_global_counters()
        
        # MODIFICACIÓN: Lógica para valores negativos en Reserva
        if amount < 0:
            # Verificar que el valor global no se vuelva negativo
            new_global_value = global_counters["reserva"] + amount
            
            if new_global_value < 0:
                # Limitar la reducción para que el total sea 0
                amount = -global_counters["reserva"]
                new_global_value = 0
            
            global_counters["reserva"] = new_global_value
        else:
            # Si es un valor positivo, simplemente sumarlo
            global_counters["reserva"] += amount
        
        # IMPORTANTE: Permitir valores negativos en el contador de la sala
        # Actualizar el valor de la sala directamente sin forzar que sea positivo
        column_totals[era]["reserva"] += amount
        
        # Guardar los cambios
        GameData.save_column_totals(room_id, column_totals)
        GameData.save_global_counters(global_counters)
        
        # Emitir evento de actualización a la sala actual
        socketio.emit('reserva_update', {
            'room_id': room_id,
            'era': era,
            'columnTotal': column_totals[era]["reserva"]
        }, room=f"room_{room_id}")
        
        # Emitir evento global a todos los clientes conectados
        socketio.emit('global_reserva_update', {
            'globalTotal': global_counters["reserva"]
        })
        
        return jsonify({
            "success": True,
            "columnTotal": column_totals[era]["reserva"],
            "globalTotal": global_counters["reserva"]
        })
    except Exception as e:
        error_msg = f"Error al actualizar reserva: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

# Controlador para Fluzo
@room_bp.route('/update_fluzo/<int:room_id>/<era>', methods=['POST'])
def update_fluzo(room_id, era):
    """Actualiza específicamente el contador de fluzo"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Obtener datos del POST
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Datos no proporcionados o formato incorrecto"})
            
        amount = data.get('amount', 0)
        
        # Inicializar datos de la sala
        column_totals = GameData.initialize_room_column_totals(room_id)
        
        # Asegurarse de que fluzo existe en los datos de la columna
        if "fluzo" not in column_totals[era]:
            column_totals[era]["fluzo"] = 0
        
        # Actualizar valor de fluzo en la sala
        column_totals[era]["fluzo"] += amount
        
        # Si el valor se vuelve negativo, establecerlo a 0
        if column_totals[era]["fluzo"] < 0:
            column_totals[era]["fluzo"] = 0
        
        # Guardar los cambios
        GameData.save_column_totals(room_id, column_totals)
        
        # Verificar si se cumplen las condiciones de victoria
        victory_conditions_met = check_victory_conditions()
        
        # Emitir evento de actualización a la sala actual
        socketio.emit('fluzo_update', {
            'room_id': room_id,
            'era': era,
            'fluzoTotal': column_totals[era]["fluzo"],
            'fluzoValue': 0,  # La caja siempre muestra 0
            'isRandomValue': True  # Indicar que este es un valor aleatorio
        }, room=f"room_{room_id}")
        
        # Si se cumplen las condiciones de victoria, emitir evento especial
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })

        return jsonify({
            "success": True,
            "fluzoTotal": column_totals[era]["fluzo"],
            "fluzoValue": 0,  # Siempre devolver 0 para la caja
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al actualizar fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})
@room_bp.route('/get_column_totals/<int:room_id>/<era>', methods=['GET'])
def get_column_totals(room_id, era):
    """Obtiene los totales de columna para una era específica"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Inicializar datos de la sala y contadores
        column_totals = GameData.initialize_room_column_totals(room_id)
        global_counters = GameData.initialize_global_counters()
        
        # Verificar condiciones de victoria
        victory_conditions_met = check_victory_conditions()
        
        return jsonify({
            "success": True,
            "columnTotals": column_totals[era],
            "globalTotals": global_counters,
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al obtener totales de columna: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

@room_bp.route('/get_global_counters', methods=['GET'])
def get_global_counters():
    """Obtiene los contadores globales"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and 'assigned_group' not in session:
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    try:
        # Inicializar contadores globales
        global_counters = GameData.initialize_global_counters()
        
        # Asegurar que consecuencias_imprevistas existe en los contadores
        if "consecuencias_imprevistas" not in global_counters:
            global_counters["consecuencias_imprevistas"] = False
            GameData.save_global_counters(global_counters)
        
        # Verificar condiciones de victoria
        victory_conditions_met = check_victory_conditions()
        
        return jsonify({
            "success": True,
            "globalTotals": global_counters,
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al obtener contadores globales: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

@room_bp.route('/reset_announcements/<int:room_id>/<era>', methods=['POST'])
def reset_announcements(room_id, era):
    """Resetea todos los anuncios de una era específica"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Inicializar o cargar datos de la sala
        room_data = GameData.initialize_room_data(room_id)
        
        # Resetear todos los anuncios de esta era
        for i in range(len(room_data["progress"][era])):
            room_data["progress"][era][i] = False
        
        # Verificar todos los botones para actualizar las dependencias
        all_available_buttons = get_available_buttons(room_data["progress"])
        
        # Emitir evento de actualización a todos los clientes en la sala
        socketio.emit('button_update', {
            'room_id': room_id,
            'era': era,
            'progress': room_data["progress"],
            'available_buttons': all_available_buttons
        }, room=f"room_{room_id}")
        
        return jsonify({
            "success": True,
            "message": "Anuncios reseteados correctamente"
        })
    except Exception as e:
        error_msg = f"Error al resetear anuncios: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})
@room_bp.route('/reset_biff/<int:room_id>/<era>', methods=['POST'])
def reset_biff(room_id, era):
    """Resetea el contador de derrotas de Biff para una era específica"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Inicializar o cargar datos de la sala
        room_data = GameData.initialize_room_data(room_id)
        
        # Resetear el contador de Biff
        room_data["biff_defeats"][era] = 0
        
        # Resetear también el estado de desactivación
        room_data["biff_disabled"][era] = False
        
        # Emitir evento de actualización a todos los clientes en la sala
        socketio.emit('biff_update', {
            'room_id': room_id,
            'era': era,
            'defeats': 0,
            'disable_button': False
        }, room=f"room_{room_id}")
        
        return jsonify({
            "success": True,
            "message": "Contador de Biff reseteado correctamente"
        })
    except Exception as e:
        error_msg = f"Error al resetear contador de Biff: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

@room_bp.route('/reset_column/<int:room_id>/<column>', methods=['POST'])
def reset_column(room_id, column):
    """Resetea un contador de columna específico en todas las eras"""
    # Verificar que sea un admin
    if not ('is_admin' in session and session['is_admin']):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if column not in ["perdicion", "reserva"]:
        return jsonify({"success": False, "error": "Columna inválida"})
    
    try:
        # Inicializar datos de la sala
        column_totals = GameData.initialize_room_column_totals(room_id)
        global_counters = GameData.initialize_global_counters()
        
        # Resetear la columna en todas las eras
        for era in ["pasado", "presente", "futuro"]:
            column_totals[era][column] = 0
        
        # Guardar los cambios
        GameData.save_column_totals(room_id, column_totals)
        
        # Resetear también el contador global si corresponde
        if column in global_counters:
            global_counters[column] = 0
            GameData.save_global_counters(global_counters)
        
        # Emitir eventos de actualización a todos los clientes en la sala
        for era in ["pasado", "presente", "futuro"]:
            socketio.emit('column_resource_update', {
                'room_id': room_id,
                'era': era,
                'columnTotals': column_totals[era]
            }, room=f"room_{room_id}")
        
        # Emitir evento global si corresponde
        if column in global_counters:
            socketio.emit('global_counter_update', {
                'globalTotals': global_counters
            })
        
        return jsonify({
            "success": True,
            "message": f"Contador de {column} reseteado correctamente"
        })
    except Exception as e:
        error_msg = f"Error al resetear columna: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})
@room_bp.route('/set_fluzo_value/<int:room_id>/<era>', methods=['POST'])
def set_fluzo_value(room_id, era):
    """Establece un valor específico para el contador de fluzo"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Obtener datos del POST
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Datos no proporcionados o formato incorrecto"})
            
        value = data.get('value', 0)
        silent = data.get('silent', False)  # Indicador para no mostrar notificación
        
        # Inicializar datos de la sala
        column_totals = GameData.initialize_room_column_totals(room_id)
        
        # Asegurarse de que fluzo existe en los datos de la columna
        if "fluzo" not in column_totals[era]:
            column_totals[era]["fluzo"] = 0
        
        # Establecer el valor directamente en lugar de incrementarlo
        column_totals[era]["fluzo"] = value
        
        # Guardar los cambios
        GameData.save_column_totals(room_id, column_totals)
        
        # Verificar si se cumplen las condiciones de victoria
        victory_conditions_met = check_victory_conditions()
        
        # Emitir evento de actualización a la sala actual - no incluimos mensaje si es silencioso
        socketio.emit('fluzo_update', {
            'room_id': room_id,
            'era': era,
            'fluzoTotal': column_totals[era]["fluzo"],
            'fluzoValue': 0,  # La caja siempre muestra 0
            'isRandomValue': True,  # Indicar que este es un valor aleatorio
            'silent': silent  # Indicador para no mostrar notificación
        }, room=f"room_{room_id}")
        
        # Si se cumplen las condiciones de victoria, emitir evento especial
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })
        
        return jsonify({
            "success": True,
            "fluzoTotal": column_totals[era]["fluzo"],
            "fluzoValue": 0,  # Siempre devolver 0 para la caja
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al establecer valor de fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})

@room_bp.route('/check_fluzo_value/<int:room_id>/<era>', methods=['POST'])
def check_fluzo_value(room_id, era):
    """Comprueba y actualiza el contador de fluzo, mostrando mensajes personalizados basados en el valor"""
    # Verificar acceso
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso para realizar esta acción."})
    
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"})
    
    try:
        # Obtener datos del POST
        data = request.get_json()
        if data is None:
            return jsonify({"success": False, "error": "Datos no proporcionados o formato incorrecto"})
            
        total_value = data.get('total_value', 0)
        checked_value = data.get('checked_value', 0)
        custom_message = data.get('custom_message')  # Mensaje personalizado desde el cliente
        
        # Inicializar datos de la sala
        column_totals = GameData.initialize_room_column_totals(room_id)
        global_counters = GameData.initialize_global_counters()
        
        # Asegurarse de que fluzo existe en los datos de la columna
        if "fluzo" not in column_totals[era]:
            column_totals[era]["fluzo"] = 0
        
        # Establecer el nuevo valor total (puede ser un valor reducido)
        column_totals[era]["fluzo"] = max(0, total_value)  # Evitar valores negativos en el total
        
        # Guardar los cambios
        GameData.save_column_totals(room_id, column_totals)
        
        # Verificar si se ha completado "Consecuencias Imprevistas"
        all_have_81 = True
        consecuencias_completado = False
        
        # Inicializar la variable para "consecuencias_imprevistas" si no existe
        if "consecuencias_imprevistas" not in global_counters:
            global_counters["consecuencias_imprevistas"] = False
        
        # Recuperar el estado actual
        consecuencias_completado = global_counters["consecuencias_imprevistas"]
        
        # Si ya está completado, no necesitamos verificar de nuevo
        if not consecuencias_completado:
            # Verificar todas las salas
            for key in GameData._game_data.keys():
                if key.startswith("room_"):
                    room_id_check = int(key.split("_")[1])
                    room_data = GameData.initialize_room_column_totals(room_id_check)
                    
                    # Verificar cada era en esta sala
                    for check_era in ["pasado", "presente", "futuro"]:
                        if "fluzo" not in room_data[check_era] or room_data[check_era]["fluzo"] != 81:
                            all_have_81 = False
                            break
                    
                    if not all_have_81:
                        break
                            
            # Si todos tienen 81, marcar como completado y usar un mensaje especial
            if all_have_81:
                consecuencias_completado = True
                global_counters["consecuencias_imprevistas"] = True
                GameData.save_global_counters(global_counters)
                
                # Emitir evento especial para notificar a todos los clientes
                socketio.emit('consecuencias_imprevistas_completed', {
                    'message': "Se ha completado Consecuencias Imprevistas"
                })
                
                message = "Se ha completado Consecuencias Imprevistas"
            else:
                # Usar el mensaje personalizado del cliente si está disponible
                message = custom_message
                
                # Si no hay mensaje personalizado y estamos en Plan 1a. Primer avance (ciclo 2), generarlo basado en el valor
                if message is None and global_counters["perdicion_cycle"] == 2:
                    if column_totals[era]["fluzo"] < 78:
                        message = "El valor de fluzo condensado es inferior a la media"
                    elif column_totals[era]["fluzo"] > 78:
                        message = "El valor de fluzo condensado es superior a la media"
                    elif column_totals[era]["fluzo"] == 78:
                        message = "¡Estas en la media! No alteres más tu valor de fluzo condensado, trata de ayudar a otros grupos colocando pistas en la Reserva temporal"
                
                # Si no hay mensaje personalizado y estamos en Plan 1a. Segundo avance (ciclo 3), generarlo basado en el valor
                elif message is None and global_counters["perdicion_cycle"] == 3:
                    if column_totals[era]["fluzo"] < 81:
                        message = "El valor de fluzo condensado es inferior a la media"
                    elif column_totals[era]["fluzo"] > 81:
                        message = "El valor de fluzo condensado es superior a la media"
                    elif column_totals[era]["fluzo"] == 81:
                        message = "¡Estas en la media! No alteres más tu valor de fluzo condensado, trata de ayudar a otros grupos colocando pistas en la Reserva temporal"
        else:
            # Si ya está completado, mantener el mensaje especial
            message = "Se ha completado Consecuencias Imprevistas"
        
        # Verificar si se cumplen las condiciones de victoria
        victory_conditions_met = check_victory_conditions()
        
        # Emitir evento de actualización a la sala actual
        socketio.emit('fluzo_update', {
            'room_id': room_id,
            'era': era,
            'fluzoTotal': column_totals[era]["fluzo"],
            'fluzoValue': 0,  # Resetear la caja a 0
            'checkedValue': checked_value,
            'message': message,
            'consecuenciasCompleted': consecuencias_completado
        }, room=f"room_{room_id}")
        
        # Si se cumplen las condiciones de victoria, emitir evento especial
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {
                'message': "->R1"
            })
        
        return jsonify({
            "success": True,
            "fluzoTotal": column_totals[era]["fluzo"],
            "message": message,
            "consecuenciasCompleted": consecuencias_completado,
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al comprobar fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})
# Función auxiliar para desactivar botones dependientes
def deactivate_dependent_buttons(progress, dependency_key):
    """Desactiva recursivamente todos los botones que dependen de uno específico"""
    for era in ["pasado", "presente", "futuro"]:
        for idx, deps in GameData.button_dependencies[era].items():
            if dependency_key in deps:
                # Este botón depende del que estamos desactivando, lo desactivamos también
                if progress[era][idx]:
                    progress[era][idx] = False
                    # Y propagamos la desactivación recursivamente
                    deactivate_dependent_buttons(progress, f"{era}-{idx}")

# Función auxiliar para verificar qué botones están disponibles
def get_available_buttons(progress):
    """Verifica qué botones están disponibles según las dependencias actuales"""
    available_buttons = {
        "pasado": [],
        "presente": [],
        "futuro": []
    }
    
    for era in ["pasado", "presente", "futuro"]:
        for i in range(len(GameData.button_info[era])):
            is_available = True
            for dep in GameData.button_dependencies[era][i]:
                dep_era, dep_idx = dep.split('-')
                dep_idx = int(dep_idx)
                if not progress[dep_era][dep_idx]:
                    is_available = False
                    break
            available_buttons[era].append(is_available)
    
    return available_buttons

# Manejador para unirse a una sala (Socket.IO)
@socketio.on('join')
def on_join(data):
    """Maneja cuando un cliente se une a una sala específica"""
    try:
        room = data.get('room')
        if room:
            join_room(room)
            print(f"Cliente unido a sala: {room}")
            
            # Si es un administrador, unirlo a la sala admin_room
            if 'is_admin' in session and session['is_admin']:
                join_room('admin_room')
                print(f"Administrador unido a sala admin_room")
    except Exception as e:
        print(f"Error al unir a sala: {str(e)}")
        traceback.print_exc()

# Manejador para abandonar una sala (Socket.IO)
@socketio.on('leave')
def on_leave(data):
    """Maneja cuando un cliente abandona una sala específica"""
    try:
        room = data.get('room')
        if room:
            leave_room(room)
            print(f"Cliente abandonó la sala: {room}")
            
            # Si es un administrador, hacer que abandone la sala admin_room
            if 'is_admin' in session and session['is_admin']:
                leave_room('admin_room')
                print(f"Administrador abandonó la sala admin_room")
    except Exception as e:
        print(f"Error al abandonar sala: {str(e)}")
        traceback.print_exc()

# Manejador para la desconexión de un cliente (Socket.IO)
@socketio.on('disconnect')
def handle_disconnect():
    """Maneja la desconexión de un cliente"""
    try:
        print(f"Cliente desconectado")
        # No es necesario hacer nada aquí, Flask-SocketIO maneja automáticamente
        # el abandono de las salas cuando un cliente se desconecta
    except Exception as e:
        print(f"Error en desconexión: {str(e)}")
        traceback.print_exc()