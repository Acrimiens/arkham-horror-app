# app/controllers/room_controller.py
from flask import Blueprint, render_template, redirect, url_for, session, flash, request, jsonify
from app.models.auth import Auth
from app.models.game_data import GameData # Importar la clase refactorizada
from app import socketio # Importar socketio global
from flask_socketio import emit, join_room, leave_room
import traceback
import json # Para posibles errores de JSON

# ... (Blueprint y otras importaciones) ...

# --- EJEMPLO DE RUTA 'era' REFACORIZADA ---
@room_bp.route('/era/<int:room_id>/<era>')
def era(room_id, era):
    """Vista de una era especÃ­fica en una sala (adaptada para Redis)"""
    # ... (VerificaciÃ³n de acceso igual que antes) ...

    room = Auth.get_room_by_id(room_id) # Sigue usando Auth (que ahora usa Redis)
    if not room:
        flash('Grupo no vÃ¡lido.', 'error')
        return redirect(url_for('auth.index'))

    # --- OBTENER DATOS DESDE REDIS ---
    try:
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
    except Exception as e:
        print(f"Error obteniendo datos de Redis para sala {room_id}: {e}")
        flash('Error al cargar los datos del juego. IntÃ©ntalo de nuevo.', 'error')
        # Decide a dÃ³nde redirigir en caso de error grave
        return redirect(url_for('auth.index'))
    # --- FIN OBTENER DATOS ---

    progress = room_data["progress"]
    # resources = room_data["resources"] # Ya no usamos esto directamente
    biff_defeats = room_data["biff_defeats"]
    biff_disabled = room_data["biff_disabled"]
    column_totals = room_data["column_totals"] # Ahora parte de room_data

    # Verificar botones disponibles (esta lÃ³gica puede permanecer)
    available_buttons = get_available_buttons(progress) # Usa la funciÃ³n auxiliar

    # Obtener nombre de mesa (igual que antes)
    mesa_name = ""
    if 'mesa_code' in session:
        mesa_info = Auth.get_mesa_info(session['mesa_code'])
        if mesa_info:
             mesa_name = "Mesa " + session['mesa_code'][4:].zfill(2).upper()

    perdicion_cycle = global_counters["perdicion_cycle"]

    # Verificar condiciones de victoria (igual que antes)
    victory_conditions_met = check_victory_conditions() # ¡ASEGÚRATE QUE ESTA FUNCIÓN TAMBIÉN USE REDIS!

    return render_template('era.html',
                          room=room,
                          era=era,
                          progress=progress,
                          button_info=GameData.button_info[era],
                          available_buttons=available_buttons,
                          # resources=resources, # Ya no se pasa asÃ­
                          biff_defeats=biff_defeats[era],
                          biff_disabled=biff_disabled.get(era, False), # Usar get con default
                          mesa_name=mesa_name,
                          perdicion_cycle=perdicion_cycle,
                          # Acceder a los totales de columna para la era especÃ­fica
                          column_totals=column_totals.get(era, {"perdicion": 0, "reserva": 0, "fluzo": 0}),
                          victory_conditions_met=victory_conditions_met,
                          is_admin='is_admin' in session and session['is_admin'])

# --- EJEMPLO DE RUTA 'toggle_button' REFACORIZADA ---
@room_bp.route('/toggle_button/<int:room_id>/<era>/<int:button_idx>', methods=['POST'])
def toggle_button(room_id, era, button_idx):
    # ... (VerificaciÃ³n de acceso igual que antes) ...

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        # --- FIN OBTENER DATOS ---

        is_activating = not room_data["progress"][era][button_idx]

        can_change = False
        if 'is_admin' in session and session['is_admin']:
            can_change = True
        elif is_activating:
            # Verificar dependencias para activar (lÃ³gica sin cambios)
            can_toggle = True
            for dep in GameData.button_dependencies[era][button_idx]:
                dep_era, dep_idx = dep.split('-')
                dep_idx = int(dep_idx)
                if not room_data["progress"][dep_era][dep_idx]:
                    can_toggle = False
                    break
            if can_toggle:
                can_change = True
        else: # Desactivando (no admin)
             can_change = True

        if can_change:
             if is_activating:
                 room_data["progress"][era][button_idx] = True
             else:
                 room_data["progress"][era][button_idx] = False
                 # Desactivar dependientes (lÃ³gica sin cambios)
                 deactivate_dependent_buttons(room_data["progress"], f"{era}-{button_idx}")

             # --- GUARDAR DATOS ---
             if not GameData.save_room_data(room_id, room_data):
                  raise Exception("Error al guardar datos de la sala en Redis")
             # --- FIN GUARDAR DATOS ---

             # Verificar botones disponibles despuÃ©s del cambio
             all_available_buttons = get_available_buttons(room_data["progress"])
             # Verificar condiciones de victoria (¡ASEGÚRATE QUE USE REDIS!)
             victory_conditions_met = check_victory_conditions()

             # Emitir evento (igual que antes)
             socketio.emit('button_update', {
                 'room_id': room_id, 'era': era, 'progress': room_data["progress"],
                 'available_buttons': all_available_buttons, 'button_idx': button_idx,
                 'is_activating': is_activating
             }, room=f"room_{room_id}")

             if victory_conditions_met:
                 socketio.emit('victory_conditions_met', {'message': "->R1"})

             # Respuesta (igual que antes)
             if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                 return jsonify({
                     'success': True, 'progress': room_data["progress"],
                     'available_buttons': all_available_buttons,
                     'victory_conditions_met': victory_conditions_met
                 })
             else:
                 return redirect(url_for('game.era', room_id=room_id, era=era))
        else:
             # No se puede activar (dependencias no cumplidas)
             flash('No se cumplen las dependencias para activar este anuncio.', 'warning')
             # ... (cÃ³digo de respuesta de error) ...

    except Exception as e:
        # ... (manejo de errores igual que antes) ...
        error_msg = f"Error al actualizar botÃ³n: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        flash(error_msg, 'error')
        # ... (cÃ³digo de respuesta de error) ...
        return jsonify({'success': False, 'error': error_msg})


# --- EJEMPLO DE RUTA 'update_perdicion' REFACORIZADA ---
@room_bp.route('/update_perdicion/<int:room_id>/<era>', methods=['POST'])
def update_perdicion(room_id, era):
    # ... (VerificaciÃ³n de acceso y datos POST igual que antes) ...
    amount = data.get('amount', 0)

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
        # --- FIN OBTENER DATOS ---

        column_totals = room_data["column_totals"]
        current_cycle = global_counters["perdicion_cycle"]
        current_global_perdicion = global_counters["perdicion"]

        if current_cycle > 3:
            return jsonify({"success": False,"error": "Contador completado."})

        # Validar amount negativo
        if amount < 0 and abs(amount) > current_global_perdicion:
            amount = -current_global_perdicion # Limitar reducciÃ³n

        new_global_perdicion = current_global_perdicion + amount
        cycle_completed = False
        notification = None
        cycle_limits = {1: 5, 2: 4, 3: 5}

        if current_cycle in cycle_limits and new_global_perdicion >= cycle_limits[current_cycle]:
            # --- COMPLETAR CICLO ---
            cycle_completed = True
            notifications = {1: "Haz avanzar al Plan 1b",
                           2: "Haz avanzar al Plan 1b. El valor de Fluzo ha sido alterado",
                           3: "(->R4)"} # Cambiado R2 por R4 segÃºn cÃ³digo original
            notification = notifications[current_cycle]

            new_cycle = current_cycle + 1
            # Actualizar ciclo y resetear perdiciÃ³n global ATÃ“MICAMENTE si es posible
            # (No hay transacciÃ³n simple aquÃ­, hacemos sets separados)
            GameData.set_global_counter("perdicion_cycle", new_cycle)
            GameData.set_global_counter("perdicion", 0)
            global_counters["perdicion_cycle"] = new_cycle # Actualizar copia local
            global_counters["perdicion"] = 0

            # Resetear perdiciÃ³n en TODAS las salas (usa la funciÃ³n refactorizada)
            GameData.reset_perdicion_all_rooms()
            # La sala actual ya se reseteÃ³ con la funciÃ³n anterior
            # Asegurar que la copia local tambiÃ©n se resetea
            for reset_era in ["pasado", "presente", "futuro"]:
                 if reset_era in column_totals:
                      column_totals[reset_era]["perdicion"] = 0

            # Ajustar fluzo si pasamos de ciclo 2 a 3 (¡Refactorizar esta funciÃ³n tambiÃ©n!)
            if current_cycle == 2:
                adjust_all_fluzo_values_internal() # ¡NECESITA REFACTORIZARSE!

        else:
            # --- ACTUALIZAR NORMALMENTE ---
            # Incrementar global atÃ³micamente
            updated_global_perdicion = GameData.increment_global_counter("perdicion", amount)
            if updated_global_perdicion is None: # Error de Redis
                 raise Exception("Error al incrementar perdiciÃ³n global en Redis")
            global_counters["perdicion"] = updated_global_perdicion # Actualizar copia local

            # Actualizar localmente en la sala
            if era in column_totals and "perdicion" in column_totals[era]:
                 column_totals[era]["perdicion"] += amount
            else: # Inicializar si no existe
                 if era not in column_totals: column_totals[era] = {}
                 column_totals[era]["perdicion"] = amount


            # --- GUARDAR DATOS DE SALA ---
            if not GameData.save_room_data(room_id, room_data):
                 raise Exception("Error al guardar datos de la sala en Redis")
            # --- FIN GUARDAR DATOS ---

        # --- EMITIR EVENTOS ---
        # ... (lÃ³gica de emisiÃ³n igual que antes, usando los datos actualizados de global_counters y column_totals[era]) ...
         # Emitir eventos segÃºn corresponda
        if cycle_completed:
            socketio.emit('perdicion_cycle_completed', {
                'perdicionCycle': global_counters["perdicion_cycle"],
                'notification': notification,
                'originRoom': room_id, 'originEra': era
            })
        else:
            socketio.emit('perdicion_update', {
                'room_id': room_id, 'era': era,
                'columnTotal': column_totals[era]["perdicion"],
                'notification': notification,
                'perdicionCycle': global_counters["perdicion_cycle"]
            }, room=f"room_{room_id}")

        socketio.emit('global_perdicion_update', {
            'globalTotal': global_counters["perdicion"],
            'perdicionCycle': global_counters["perdicion_cycle"],
            'notification': notification,
            'cycleCompleted': cycle_completed
        })
        # --- FIN EMITIR EVENTOS ---

        # Verificar victoria (¡ASEGÚRATE QUE USE REDIS!)
        victory_conditions_met = check_victory_conditions()
        if victory_conditions_met:
            socketio.emit('victory_conditions_met', {'message': "->R1"})

        return jsonify({
            "success": True,
            "columnTotal": column_totals[era]["perdicion"],
            "globalTotal": global_counters["perdicion"],
            "perdicionCycle": global_counters["perdicion_cycle"],
            "notification": notification,
            "victory_conditions_met": victory_conditions_met
        })

    except Exception as e:
        # ... (manejo de errores igual que antes) ...
        error_msg = f"Error al actualizar perdiciÃ³n: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg})


# --- ¡IMPORTANTE! ---
# Debes refactorizar TODAS las funciones en room_controller.py que lean o escriban
# datos de GameData para seguir el patrÃ³n:
# 1. LEER datos de Redis (GameData.get_room_data, GameData.get_global_counters)
# 2. MODIFICAR los datos en las variables Python locales.
# 3. ESCRIBIR los datos modificados de vuelta a Redis (GameData.save_room_data, GameData.increment/set_global_counter).
# 4. AsegÃºrate que funciones como check_victory_conditions y adjust_all_fluzo_values_internal tambiÃ©n usen Redis.
#---------------------

# Funciones auxiliares como get_available_buttons y deactivate_dependent_buttons
# pueden permanecer igual ya que operan sobre la estructura de datos leÃ­da.

# FunciÃ³n auxiliar (MODIFICADA para usar Redis indirectamente via GameData)
def check_victory_conditions():
    """Verifica si todas las mesas cumplen las tres condiciones de victoria (adaptada para Redis)"""
    try:
        # Obtener todas las salas (grupos) desde Auth (que usa Redis)
        all_rooms_info = Auth.get_all_rooms()
        if not all_rooms_info:
            return False # No hay salas

        room_ids = [room['id'] for room in all_rooms_info]

        for room_id in room_ids:
            # Obtener datos actualizados de la sala desde Redis
            room_data = GameData.get_room_data(room_id)
            if not room_data: # Error al leer de Redis?
                print(f"Advertencia: No se pudieron obtener datos para la sala {room_id} al verificar victoria.")
                return False

            column_totals = room_data.get("column_totals", {})
            biff_disabled = room_data.get("biff_disabled", {})
            progress = room_data.get("progress", {})

            # 1. Biff derrotado en todas las eras
            for era in ["pasado", "presente", "futuro"]:
                if not biff_disabled.get(era, False):
                    return False

            # 2. Fluzo = 81 en todas las eras
            for era in ["pasado", "presente", "futuro"]:
                era_totals = column_totals.get(era, {})
                if era_totals.get("fluzo", 0) != 81:
                    return False

            # 3. "Un noble legado" marcado en todas las eras
            noble_legado_indices = {"pasado": 5, "presente": 4, "futuro": 3}
            for era, idx in noble_legado_indices.items():
                 era_progress = progress.get(era, [])
                 if not (len(era_progress) > idx and era_progress[idx]):
                     return False

        return True # Todas las condiciones cumplidas en todas las salas

    except Exception as e:
        print(f"Error al verificar condiciones de victoria con Redis: {str(e)}")
        traceback.print_exc()
        return False

# --- (Resto de room_controller.py: AsegÃºrate de refactorizar TODO lo que use GameData) ---
# Por ejemplo, adjust_all_fluzo_values_internal necesita iterar sobre las salas,
# obtener sus datos de Redis, modificar el fluzo, y guardar de vuelta.