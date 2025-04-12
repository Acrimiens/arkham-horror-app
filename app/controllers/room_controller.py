# -*- coding: utf-8 -*-
# app/controllers/room_controller.py

from flask import Blueprint, render_template, redirect, url_for, session, flash, request, jsonify
from app.models.auth import Auth  # Usa la versión Redis
from app.models.game_data import GameData # Usa la versión Redis
from app import socketio # Importar socketio global
from flask_socketio import emit, join_room, leave_room
import traceback
import json
from copy import deepcopy
import random # Necesario para biff_defeat

# --- DEFINE EL BLUEPRINT AQUÍ ---
room_bp = Blueprint('game', __name__)
# -----------------------------

# --- Rutas ---

@room_bp.route('/room/<int:room_id>')
def room(room_id):
    """Vista de selección de eras en una sala"""
    # [SIN CAMBIOS EN LÓGICA DE ACCESO]
    if not ('is_admin' in session and session['is_admin']):
        flash('No tienes permiso para acceder a esta página.', 'error')
        if 'assigned_group' in session and 'assigned_era' in session:
            return redirect(url_for('game.era', room_id=session['assigned_group'], era=session['assigned_era']))
        else:
            return redirect(url_for('auth.index'))

    # [REFACTORIZADO] Usa Auth refactorizado
    room_info = Auth.get_room_by_id(room_id)
    if not room_info:
        flash('Grupo no válido.', 'error')
        return redirect(url_for('auth.index'))

    return render_template('room.html', room=room_info, is_admin=True)

@room_bp.route('/era/<int:room_id>/<era>')
def era(room_id, era):
    """Vista de una era específica en una sala (adaptada para Redis)"""
    # [SIN CAMBIOS EN LÓGICA DE ACCESO]
    if 'is_admin' in session and session['is_admin']:
        pass # OK
    elif 'assigned_group' in session and 'assigned_era' in session:
        if session['assigned_group'] != room_id or session['assigned_era'] != era:
            flash('No tienes permiso para acceder a este grupo o era.', 'error')
            return redirect(url_for('game.era', room_id=session['assigned_group'], era=session['assigned_era']))
    else:
        flash('No tienes permiso para acceder a esta página.', 'error')
        return redirect(url_for('auth.index'))

    if era not in ["pasado", "presente", "futuro"]:
        # Redirigir a era asignada o a login si la era es inválida
        era_redir = session.get('assigned_era') if 'assigned_group' in session else None
        if era_redir and session['assigned_group'] == room_id:
             return redirect(url_for('game.era', room_id=room_id, era=era_redir))
        else:
             return redirect(url_for('auth.index')) # O al panel admin si es admin

    # [REFACTORIZADO] Usa Auth refactorizado
    room_info = Auth.get_room_by_id(room_id)
    if not room_info:
        flash('Grupo no válido.', 'error')
        return redirect(url_for('auth.index'))

    # --- OBTENER DATOS DESDE REDIS ---
    try:
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
    except Exception as e:
        print(f"Error obteniendo datos de Redis para sala {room_id}: {e}")
        flash('Error al cargar los datos del juego. Inténtalo de nuevo.', 'error')
        return redirect(url_for('auth.index'))
    # --- FIN OBTENER DATOS ---

    progress = room_data.get("progress", {}) # Usar .get con default por si acaso
    biff_defeats = room_data.get("biff_defeats", {})
    biff_disabled = room_data.get("biff_disabled", {})
    column_totals = room_data.get("column_totals", {})

    # Verificar botones disponibles usando la función auxiliar
    available_buttons = get_available_buttons(progress)

    # Obtener nombre de mesa
    mesa_name = ""
    if 'mesa_code' in session:
        # No es necesario volver a leer de Redis aquí, ya lo hizo auth_controller
        mesa_code = session['mesa_code']
        mesa_name = "Mesa " + mesa_code[4:].zfill(2).upper()

    perdicion_cycle = global_counters["perdicion_cycle"]

    # Verificar condiciones de victoria (usa la función refactorizada)
    victory_conditions_met = check_victory_conditions()

    return render_template('era.html',
                          room=room_info, # Pasar room_info obtenido de Auth
                          era=era,
                          progress=progress, # Pasar el diccionario de progreso
                          button_info=GameData.button_info.get(era, []), # Info estática
                          available_buttons=available_buttons.get(era, []), # Pasar lista para la era actual
                          # resources ya no existe, se maneja en column_totals
                          biff_defeats=biff_defeats.get(era, 0),
                          biff_disabled=biff_disabled.get(era, False),
                          mesa_name=mesa_name,
                          perdicion_cycle=perdicion_cycle,
                          column_totals=column_totals.get(era, {"perdicion": 0, "reserva": 0, "fluzo": 0}),
                          victory_conditions_met=victory_conditions_met,
                          is_admin='is_admin' in session and session['is_admin'])


@room_bp.route('/toggle_button/<int:room_id>/<era>/<int:button_idx>', methods=['POST'])
def toggle_button(room_id, era, button_idx):
    """Activa o desactiva un botón de anuncio (adaptado para Redis)"""
    # [SIN CAMBIOS EN LÓGICA DE ACCESO]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
         # Manejo de error AJAX
         if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'success': False, 'error': 'No tienes permiso'}), 403
         else:
             flash('No tienes permiso para realizar esta acción.', 'error')
             return redirect(url_for('auth.index'))

    if era not in GameData.button_info or button_idx >= len(GameData.button_info[era]):
        return jsonify({'success': False, 'error': 'Botón o era inválida'}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        progress = room_data["progress"]
        # --- FIN OBTENER DATOS ---

        is_activating = not progress[era][button_idx]
        can_change = False # Flag para saber si se realiza el cambio

        if 'is_admin' in session and session['is_admin']:
            can_change = True
        elif is_activating:
            # Verificar dependencias para activar
            can_toggle = True
            # Usar GameData.button_dependencies directamente
            dependencies = GameData.button_dependencies.get(era, {}).get(button_idx, [])
            for dep in dependencies:
                try:
                    dep_era, dep_idx_str = dep.split('-')
                    dep_idx = int(dep_idx_str)
                    if not (dep_era in progress and dep_idx < len(progress[dep_era]) and progress[dep_era][dep_idx]):
                        can_toggle = False
                        break
                except (ValueError, KeyError, IndexError):
                    can_toggle = False
                    break
            if can_toggle:
                can_change = True
        else: # Desactivando (no admin) - Siempre permitido si ya está activo
            can_change = True

        if can_change:
             if is_activating:
                 progress[era][button_idx] = True
             else:
                 progress[era][button_idx] = False
                 # Desactivar dependientes (usa la función auxiliar)
                 deactivate_dependent_buttons(progress, f"{era}-{button_idx}")

             # --- GUARDAR DATOS ---
             # Guardamos todo el room_data actualizado
             if not GameData.save_room_data(room_id, room_data):
                  raise Exception("Error al guardar datos de la sala en Redis")
             # --- FIN GUARDAR DATOS ---

             # Calcular estado actualizado de botones y victoria
             all_available_buttons = get_available_buttons(progress)
             victory_conditions_met = check_victory_conditions()

             # Emitir evento (enviar solo datos necesarios)
             socketio.emit('button_update', {
                 'room_id': room_id,
                 'progress': progress, # Enviar todo el progreso para recalcular dependencias en cliente
                 # 'available_buttons': all_available_buttons, # Cliente puede calcular esto a partir de progress
                 # 'era': era, # El cliente ya sabe su era
                 # 'button_idx': button_idx, # Cliente puede determinarlo
                 # 'is_activating': is_activating # Cliente puede determinarlo
             }, room=f"room_{room_id}")

             if victory_conditions_met:
                 socketio.emit('victory_conditions_met', {'message': "->R1"})

             # Respuesta AJAX
             return jsonify({
                 'success': True,
                 'progress': progress, # Devuelve el estado actualizado
                 # 'available_buttons': all_available_buttons # Opcional devolver esto
                 'victory_conditions_met': victory_conditions_met
             })
        else:
             # No se puede activar (dependencias no cumplidas)
             return jsonify({'success': False, 'error': 'Dependencias no cumplidas'}), 400

    except Exception as e:
        error_msg = f"Error al actualizar botÃ³n: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg}), 500

# [ELIMINADO] Ruta /update_resources - Funcionalidad cubierta por /update_reserva
# @room_bp.route('/update_resources/<int:room_id>/<era>', methods=['POST'])
# def update_resources(room_id, era):
#    ...

# [REFACTORIZADO] adjust_all_fluzo_values_internal - Ahora usa Redis
def adjust_all_fluzo_values_internal():
    """Ajusta los valores de fluzo en todas las salas según las reglas especificadas (adaptada para Redis)"""
    try:
        all_rooms_info = Auth.get_all_rooms()
        if not all_rooms_info:
            print("No hay salas para ajustar fluzo.")
            return True # No es un error si no hay salas

        room_ids = [room['id'] for room in all_rooms_info]
        any_change = False

        for room_id in room_ids:
            try:
                room_data = GameData.get_room_data(room_id)
                column_totals = room_data.get("column_totals", {})
                room_changed = False

                for era in ["pasado", "presente", "futuro"]:
                    era_totals = column_totals.get(era, {})
                    current_fluzo = era_totals.get("fluzo", 0)
                    new_fluzo = current_fluzo

                    # Aplicar las reglas de ajuste:
                    if current_fluzo > 86:      new_fluzo = current_fluzo - 10
                    elif current_fluzo < 76:    new_fluzo = current_fluzo + 10
                    elif 80 <= current_fluzo <= 82: new_fluzo = current_fluzo - 5

                    new_fluzo = max(0, new_fluzo) # Asegurar no negativo

                    if new_fluzo != current_fluzo:
                        # Actualizar localmente
                        if era not in room_data["column_totals"]: room_data["column_totals"][era] = {}
                        room_data["column_totals"][era]["fluzo"] = new_fluzo
                        room_changed = True
                        any_change = True

                        # Emitir evento (SOLO si cambiÃ³)
                        socketio.emit('fluzo_update', {
                            'room_id': room_id, 'era': era,
                            'fluzoTotal': new_fluzo, 'fluzoValue': 0,
                            'message': "El nivel de Fluzo condensado ha sido alterado",
                            'consecuenciasCompleted': room_data.get("consecuencias_imprevistas", False) # Pasar estado actual
                        }, room=f"room_{room_id}")

                # Guardar datos de la sala SOLO si cambiÃ³ algo en ella
                if room_changed:
                    if not GameData.save_room_data(room_id, room_data):
                        print(f"Error guardando sala {room_id} despuÃ©s de ajustar fluzo.")
                        # Continuar con otras salas? O devolver False? Por ahora continuamos.

            except Exception as e_inner:
                 print(f"Error procesando sala {room_id} en adjust_all_fluzo_values_internal: {e_inner}")
                 continue # Saltar a la siguiente sala

        # Verificar victoria global despuÃ©s de todos los ajustes
        if any_change:
             victory_conditions_met = check_victory_conditions()
             if victory_conditions_met:
                 socketio.emit('victory_conditions_met', {'message': "->R1"})

        return True # Indicar Ã©xito general (errores individuales se loggean)

    except Exception as e:
        print(f"Error general en adjust_all_fluzo_values_internal: {str(e)}")
        traceback.print_exc()
        return False

@room_bp.route('/adjust_all_fluzo_values', methods=['POST'])
def adjust_all_fluzo_values():
    """Ajusta los valores de fluzo en todas las salas (adaptado para Redis)"""
    # [SIN CAMBIOS EN LÓGICA DE ACCESO]
    if not ('is_admin' in session and session['is_admin']):
        return jsonify({"success": False, "error": "No tienes permiso"}), 403

    try:
        success = adjust_all_fluzo_values_internal() # Llama a la versión refactorizada

        if success:
            # La verificación de victoria ya se hace dentro de internal si hubo cambios
            return jsonify({"success": True, "message": "Valores de fluzo procesados."})
        else:
            return jsonify({"success": False, "error": "Error al procesar ajuste de fluzo"}), 500
    except Exception as e:
        error_msg = f"Error al ajustar valores de fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@room_bp.route('/biff_defeat/<int:room_id>/<era>', methods=['POST'])
def biff_defeat(room_id, era):
    """Incrementa el contador de derrotas de Biff (adaptado para Redis)"""
    # [SIN CAMBIOS EN LÓGICA DE ACCESO]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
        # --- FIN OBTENER DATOS ---

        biff_defeats = room_data.get("biff_defeats", {})
        biff_disabled = room_data.get("biff_disabled", {})
        current_cycle = global_counters["perdicion_cycle"]
        is_plan_1a = (current_cycle == 1)

        # Verificar si ya estÃ¡ deshabilitado
        if biff_disabled.get(era, False):
             return jsonify({ "success": True, "defeats": biff_defeats.get(era, 0), "disable_button": True, "message": "Biff ya estÃ¡ en la zona de victoria." })

        # Incrementar contador localmente
        current_era_defeats = biff_defeats.get(era, 0)
        new_defeats = current_era_defeats + 1
        room_data["biff_defeats"][era] = new_defeats # Actualizar en la copia local

        # Determinar mensaje y si se deshabilita
        biff_message = ""
        disable_button = False
        # [LÓGICA DE MENSAJES SIN CAMBIOS - Usa new_defeats y is_plan_1a]
        if new_defeats == 1: biff_message = "\"¡Hey, McFly!...\"" # Mensaje completo omitido por brevedad
        elif new_defeats == 2: biff_message = "\"¿Te estoy haciendo perder el tiempo?...\""
        elif new_defeats == 3: biff_message = "\"¿Te estoy despistando?...\""
        elif new_defeats == 4: biff_message = "\"¡Llevo mucho tiempo preparando esto!...\""
        elif new_defeats >= 5:
            if not is_plan_1a:
                biff_message = "Dale la vuelta a Biff Tannen y añadelo a la zona de victoria."
                disable_button = True
                room_data["biff_disabled"][era] = True # Marcar deshabilitado localmente
            else:
                if new_defeats == 5: biff_message = "\"Deja de golpearte...\""
                elif new_defeats == 6: biff_message = "\"¡Tenemos tiempo de sobra!...\""
                elif new_defeats == 7: biff_message = "\"¡Ya no vas a necesitar esto!...\""
                else:
                    random_messages = ["\"Deja de golpearte...\"", "\"¡Tenemos tiempo de sobra!...\"", "\"¡Ya no vas a necesitar esto!...\""]
                    biff_message = random.choice(random_messages)

        # --- GUARDAR DATOS ---
        if not GameData.save_room_data(room_id, room_data):
             raise Exception("Error al guardar datos de la sala en Redis")
        # --- FIN GUARDAR DATOS ---

        # Verificar victoria si se deshabilitÃ³ el botÃ³n
        victory_conditions_met = check_victory_conditions() if disable_button else False

        # Emitir evento
        socketio.emit('biff_update', {
            'room_id': room_id, 'era': era, 'defeats': new_defeats,
            'message': biff_message, 'disable_button': disable_button
        }, room=f"room_{room_id}")

        if victory_conditions_met:
             socketio.emit('victory_conditions_met', {'message': "->R1"})

        return jsonify({
            "success": True, "defeats": new_defeats, "message": biff_message,
            "disable_button": disable_button, "victory_conditions_met": victory_conditions_met
        })

    except Exception as e:
        error_msg = f"Error al actualizar derrotas de Biff: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500


# [ELIMINADO] Ruta genérica /update_column_resource - Usar rutas específicas
# @room_bp.route('/update_column_resource/<int:room_id>/<era>/<column>', methods=['POST'])
# def update_column_resource(room_id, era, column):
#    ...

# --- Rutas Específicas para Contadores ---

@room_bp.route('/update_perdicion/<int:room_id>/<era>', methods=['POST'])
def update_perdicion(room_id, era):
    """Actualiza específicamente el contador de perdición (adaptado para Redis)"""
    # [SIN CAMBIOS EN LÓGICA DE ACCESO]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id):
        return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]:
        return jsonify({"success": False, "error": "Era inválida"}), 400

    data = request.get_json()
    if data is None or 'amount' not in data:
        return jsonify({"success": False, "error": "Datos inválidos"}), 400
    try:
        amount = int(data.get('amount', 0))
    except ValueError:
         return jsonify({"success": False, "error": "Cantidad inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
        # --- FIN OBTENER DATOS ---

        column_totals = room_data.get("column_totals", {})
        current_cycle = global_counters["perdicion_cycle"]
        current_global_perdicion = global_counters["perdicion"]

        if current_cycle > 3:
            return jsonify({"success": False,"error": "Contador completado."})

        # Validar amount negativo
        if amount < 0 and abs(amount) > current_global_perdicion:
            amount = -current_global_perdicion # Limitar reducción

        new_global_perdicion = current_global_perdicion + amount
        cycle_completed = False
        notification = None
        cycle_limits = {1: 5, 2: 4, 3: 5} # Límites correctos

        if current_cycle in cycle_limits and new_global_perdicion >= cycle_limits[current_cycle]:
            # --- COMPLETAR CICLO ---
            cycle_completed = True
            notifications = {1: "Haz avanzar al Plan 1b",
                           2: "Haz avanzar al Plan 1b. El valor de Fluzo ha sido alterado",
                           3: "(->R4)"} # Mantenido de tu código original
            notification = notifications[current_cycle]
            new_cycle = current_cycle + 1

            # Actualizar globales (separado para claridad)
            GameData.set_global_counter("perdicion_cycle", new_cycle)
            GameData.set_global_counter("perdicion", 0)
            # Actualizar copia local para emitir
            global_counters["perdicion_cycle"] = new_cycle
            global_counters["perdicion"] = 0

            # Resetear perdición en TODAS las salas
            GameData.reset_perdicion_all_rooms() # Usa la función refactorizada
            # Asegurar que la copia local de ESTA sala también se resetea
            for reset_era in ["pasado", "presente", "futuro"]:
                 if reset_era in column_totals:
                      column_totals[reset_era]["perdicion"] = 0

            # Ajustar fluzo si pasamos de ciclo 2 a 3
            if current_cycle == 2:
                adjust_all_fluzo_values_internal() # Llama a la versión refactorizada

        else:
            # --- ACTUALIZAR NORMALMENTE ---
            updated_global = GameData.increment_global_counter("perdicion", amount)
            if updated_global is None: raise Exception("Error Redis global perdicion")
            global_counters["perdicion"] = updated_global # Actualizar copia local

            # Actualizar localmente en la sala (asegurando estructura)
            if era not in column_totals: column_totals[era] = {}
            column_totals[era]["perdicion"] = column_totals[era].get("perdicion", 0) + amount
            # --- GUARDAR DATOS DE SALA ---
            if not GameData.save_room_data(room_id, room_data):
                 raise Exception("Error al guardar sala en Redis")
            # --- FIN GUARDAR DATOS ---

        # --- EMITIR EVENTOS ---
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
        error_msg = f"Error al actualizar perdición: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@room_bp.route('/update_reserva/<int:room_id>/<era>', methods=['POST'])
def update_reserva(room_id, era):
    """Actualiza específicamente el contador de reserva (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que update_perdicion]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]: return jsonify({"success": False, "error": "Era inválida"}), 400
    data = request.get_json(); amount = data.get('amount', 0) if data else 0
    if not isinstance(amount, int): return jsonify({"success": False, "error": "Cantidad inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
        # --- FIN OBTENER DATOS ---

        column_totals = room_data.get("column_totals", {})
        current_global_reserva = global_counters["reserva"]

        # Validar amount negativo
        if amount < 0 and abs(amount) > current_global_reserva:
            amount = -current_global_reserva

        # Actualizar global
        updated_global = GameData.increment_global_counter("reserva", amount)
        if updated_global is None: raise Exception("Error Redis global reserva")
        global_counters["reserva"] = updated_global # Actualizar copia local

        # Actualizar localmente en la sala (permite negativos)
        if era not in column_totals: column_totals[era] = {}
        column_totals[era]["reserva"] = column_totals[era].get("reserva", 0) + amount

        # --- GUARDAR DATOS DE SALA ---
        if not GameData.save_room_data(room_id, room_data):
             raise Exception("Error al guardar sala en Redis")
        # --- FIN GUARDAR DATOS ---

        # --- EMITIR EVENTOS ---
        socketio.emit('reserva_update', {
            'room_id': room_id, 'era': era,
            'columnTotal': column_totals[era]["reserva"]
        }, room=f"room_{room_id}")
        socketio.emit('global_reserva_update', {
            'globalTotal': global_counters["reserva"]
        })
        # --- FIN EMITIR EVENTOS ---

        return jsonify({
            "success": True,
            "columnTotal": column_totals[era]["reserva"],
            "globalTotal": global_counters["reserva"]
        })

    except Exception as e:
        error_msg = f"Error al actualizar reserva: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@room_bp.route('/update_fluzo/<int:room_id>/<era>', methods=['POST'])
def update_fluzo(room_id, era):
    """Actualiza específicamente el contador de fluzo (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que update_perdicion]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]: return jsonify({"success": False, "error": "Era inválida"}), 400
    data = request.get_json(); amount = data.get('amount', 0) if data else 0
    if not isinstance(amount, int): return jsonify({"success": False, "error": "Cantidad inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters() # Para check_fluzo_value
        # --- FIN OBTENER DATOS ---

        column_totals = room_data.get("column_totals", {})
        consecuencias_completado = global_counters.get("consecuencias_imprevistas", False)

        # No permitir cambios si consecuencias está completado
        if consecuencias_completado:
             return jsonify({"success": False, "error": "Consecuencias Imprevistas completado."})

        # Actualizar localmente en la sala
        if era not in column_totals: column_totals[era] = {}
        new_fluzo = max(0, column_totals[era].get("fluzo", 0) + amount) # No negativo
        column_totals[era]["fluzo"] = new_fluzo

        # --- GUARDAR DATOS DE SALA ---
        if not GameData.save_room_data(room_id, room_data):
             raise Exception("Error al guardar sala en Redis")
        # --- FIN GUARDAR DATOS ---

        # Verificar victoria
        victory_conditions_met = check_victory_conditions()

        # --- EMITIR EVENTOS ---
        socketio.emit('fluzo_update', {
            'room_id': room_id, 'era': era,
            'fluzoTotal': new_fluzo, 'fluzoValue': 0, # Caja siempre 0
            'isRandomValue': False, # No es valor aleatorio
            'consecuenciasCompleted': consecuencias_completado
        }, room=f"room_{room_id}")
        if victory_conditions_met:
             socketio.emit('victory_conditions_met', {'message': "->R1"})
        # --- FIN EMITIR EVENTOS ---

        return jsonify({
            "success": True,
            "fluzoTotal": new_fluzo,
            "fluzoValue": 0,
            "victory_conditions_met": victory_conditions_met
        })

    except Exception as e:
        error_msg = f"Error al actualizar fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500


@room_bp.route('/get_column_totals/<int:room_id>/<era>', methods=['GET'])
def get_column_totals(room_id, era):
    """Obtiene los totales de columna para una era específica (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que antes]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]: return jsonify({"success": False, "error": "Era inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
        # --- FIN OBTENER DATOS ---

        column_totals_era = room_data.get("column_totals", {}).get(era, {"perdicion": 0, "reserva": 0, "fluzo": 0})
        victory_conditions_met = check_victory_conditions()

        return jsonify({
            "success": True,
            "columnTotals": column_totals_era,
            "globalTotals": global_counters,
            "victory_conditions_met": victory_conditions_met
        })
    except Exception as e:
        error_msg = f"Error al obtener totales de columna: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@room_bp.route('/get_global_counters', methods=['GET'])
def get_global_counters():
    """Obtiene los contadores globales (adaptado para Redis)"""
    # [Lógica de acceso igual que antes]
    if not ('is_admin' in session and session['is_admin']) and 'assigned_group' not in session:
        return jsonify({"success": False, "error": "No tienes permiso"}), 403

    try:
        # --- OBTENER DATOS ---
        global_counters = GameData.get_global_counters()
        # --- FIN OBTENER DATOS ---

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
        return jsonify({"success": False, "error": error_msg}), 500

# --- Rutas de Reseteo ---

@room_bp.route('/reset_announcements/<int:room_id>/<era>', methods=['POST'])
def reset_announcements(room_id, era):
    """Resetea todos los anuncios de una era específica (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que antes]
    if not ('is_admin' in session and session['is_admin']): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in GameData.button_info: return jsonify({"success": False, "error": "Era inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        # --- FIN OBTENER DATOS ---

        if era in room_data.get("progress", {}):
            num_buttons = len(GameData.button_info[era])
            room_data["progress"][era] = [False] * num_buttons

            # --- GUARDAR DATOS ---
            if not GameData.save_room_data(room_id, room_data):
                 raise Exception("Error al guardar sala en Redis")
            # --- FIN GUARDAR DATOS ---

            # Calcular botones disponibles
            all_available_buttons = get_available_buttons(room_data["progress"])

            # Emitir evento
            socketio.emit('button_update', {
                'room_id': room_id,
                'progress': room_data["progress"],
                # 'available_buttons': all_available_buttons, # Cliente puede calcular
            }, room=f"room_{room_id}")

            return jsonify({"success": True, "message": "Anuncios reseteados"})
        else:
            return jsonify({"success": False, "error": "Datos de progreso no encontrados para la era"})


    except Exception as e:
        error_msg = f"Error al resetear anuncios: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@room_bp.route('/reset_biff/<int:room_id>/<era>', methods=['POST'])
def reset_biff(room_id, era):
    """Resetea el contador de derrotas de Biff para una era específica (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que antes]
    if not ('is_admin' in session and session['is_admin']): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]: return jsonify({"success": False, "error": "Era inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        # --- FIN OBTENER DATOS ---

        room_data.setdefault("biff_defeats", {})[era] = 0
        room_data.setdefault("biff_disabled", {})[era] = False

        # --- GUARDAR DATOS ---
        if not GameData.save_room_data(room_id, room_data):
             raise Exception("Error al guardar sala en Redis")
        # --- FIN GUARDAR DATOS ---

        # Emitir evento
        socketio.emit('biff_update', {
            'room_id': room_id, 'era': era, 'defeats': 0, 'disable_button': False
        }, room=f"room_{room_id}")

        return jsonify({"success": True, "message": "Contador de Biff reseteado"})

    except Exception as e:
        error_msg = f"Error al resetear contador de Biff: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@room_bp.route('/reset_column/<int:room_id>/<column>', methods=['POST'])
def reset_column(room_id, column):
    """Resetea un contador de columna específico en todas las eras (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que antes]
    if not ('is_admin' in session and session['is_admin']): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    # Permitimos resetear fluzo también si es necesario
    if column not in ["perdicion", "reserva", "fluzo"]: return jsonify({"success": False, "error": "Columna inválida"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        # --- FIN OBTENER DATOS ---

        column_totals = room_data.setdefault("column_totals", {})
        changed = False
        for era in ["pasado", "presente", "futuro"]:
            if era not in column_totals: column_totals[era] = {}
            if column_totals[era].get(column, 0) != 0:
                column_totals[era][column] = 0
                changed = True

        # Resetear global si aplica (perdicion o reserva)
        global_reset_needed = column in ["perdicion", "reserva"]
        global_counters = None
        if global_reset_needed:
            global_counters = GameData.get_global_counters()
            if global_counters.get(column, 0) != 0:
                GameData.set_global_counter(column, 0)
                global_counters[column] = 0 # Actualizar copia local para emitir
            else:
                 global_reset_needed = False # No era necesario resetear global

        # --- GUARDAR DATOS DE SALA (SOLO SI CAMBIARON) ---
        if changed:
            if not GameData.save_room_data(room_id, room_data):
                 raise Exception("Error al guardar sala en Redis")
        # --- FIN GUARDAR DATOS ---

        # --- EMITIR EVENTOS ---
        if changed: # Emitir solo si la sala cambiÃ³
            for era in ["pasado", "presente", "futuro"]:
                # Enviar el estado completo de column_totals para la era
                socketio.emit('column_resource_update', {
                    'room_id': room_id, 'era': era,
                    'columnTotals': column_totals.get(era, {}),
                     # Incluir ciclo actual de perdiciÃ³n si reseteamos perdiciÃ³n
                    'perdicionCycle': global_counters["perdicion_cycle"] if global_counters and column == "perdicion" else GameData.get_global_counters()["perdicion_cycle"]
                }, room=f"room_{room_id}")

        if global_reset_needed:
            socketio.emit('global_counter_update', {
                'globalTotals': global_counters
                # No incluir 'notification' o 'cycleCompleted' aquí
            })
        # --- FIN EMITIR EVENTOS ---

        return jsonify({"success": True, "message": f"Contador de {column} reseteado"})

    except Exception as e:
        error_msg = f"Error al resetear columna: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

# --- Rutas de Fluzo Específicas ---

@room_bp.route('/set_fluzo_value/<int:room_id>/<era>', methods=['POST'])
def set_fluzo_value(room_id, era):
    """Establece un valor específico para el contador de fluzo (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que antes]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]: return jsonify({"success": False, "error": "Era inválida"}), 400
    data = request.get_json();
    if data is None: return jsonify({"success": False, "error": "Datos inválidos"}), 400
    value = data.get('value', 0); silent = data.get('silent', False)
    if not isinstance(value, int): return jsonify({"success": False, "error": "Valor inválido"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters() # Para estado consecuencias
        # --- FIN OBTENER DATOS ---

        column_totals = room_data.setdefault("column_totals", {})
        if era not in column_totals: column_totals[era] = {}

        new_fluzo = max(0, value) # Asegurar no negativo
        column_totals[era]["fluzo"] = new_fluzo

        # --- GUARDAR DATOS DE SALA ---
        if not GameData.save_room_data(room_id, room_data):
             raise Exception("Error al guardar sala en Redis")
        # --- FIN GUARDAR DATOS ---

        victory_conditions_met = check_victory_conditions()
        consecuencias_completado = global_counters.get("consecuencias_imprevistas", False)

        # --- EMITIR EVENTOS ---
        socketio.emit('fluzo_update', {
            'room_id': room_id, 'era': era, 'fluzoTotal': new_fluzo,
            'fluzoValue': 0, 'isRandomValue': True, # Mantener flag como en original?
            'silent': silent, 'consecuenciasCompleted': consecuencias_completado
        }, room=f"room_{room_id}")
        if victory_conditions_met:
             socketio.emit('victory_conditions_met', {'message': "->R1"})
        # --- FIN EMITIR EVENTOS ---

        return jsonify({
            "success": True, "fluzoTotal": new_fluzo, "fluzoValue": 0,
            "victory_conditions_met": victory_conditions_met
        })

    except Exception as e:
        error_msg = f"Error al establecer valor de fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500

@room_bp.route('/check_fluzo_value/<int:room_id>/<era>', methods=['POST'])
def check_fluzo_value(room_id, era):
    """Comprueba y actualiza fluzo, muestra mensajes, verifica consecuencias (adaptado para Redis)"""
    # [Lógica de acceso y validación igual que antes]
    if not ('is_admin' in session and session['is_admin']) and ('assigned_group' not in session or session['assigned_group'] != room_id): return jsonify({"success": False, "error": "No tienes permiso"}), 403
    if era not in ["pasado", "presente", "futuro"]: return jsonify({"success": False, "error": "Era inválida"}), 400
    data = request.get_json();
    if data is None: return jsonify({"success": False, "error": "Datos inválidos"}), 400
    total_value = data.get('total_value', 0) # Este es el *nuevo* total calculado en cliente
    checked_value = data.get('checked_value', 0) # El valor +/- que se introdujo
    custom_message = data.get('custom_message') # Mensaje opcional del cliente
    if not isinstance(total_value, int) or not isinstance(checked_value, int):
        return jsonify({"success": False, "error": "Valores inválidos"}), 400

    try:
        # --- OBTENER DATOS ---
        room_data = GameData.get_room_data(room_id)
        global_counters = GameData.get_global_counters()
        # --- FIN OBTENER DATOS ---

        column_totals = room_data.setdefault("column_totals", {})
        if era not in column_totals: column_totals[era] = {}

        consecuencias_completado = global_counters.get("consecuencias_imprevistas", False)

        # No permitir cambios si ya está completado
        if consecuencias_completado:
            # Aún así, emitir estado actual para que el cliente se actualice si estaba desincronizado
             socketio.emit('fluzo_update', {
                'room_id': room_id, 'era': era,
                'fluzoTotal': column_totals[era].get("fluzo", 0),
                'fluzoValue': 0, 'checkedValue': checked_value,
                'message': "Se ha completado Consecuencias Imprevistas",
                'consecuenciasCompleted': True
             }, room=f"room_{room_id}")
             return jsonify({"success": True, "fluzoTotal": column_totals[era].get("fluzo", 0), "message": "Consecuencias ya completado", "consecuenciasCompleted": True})

        # Establecer el nuevo valor total (ya validado no negativo en JS, pero por si acaso)
        new_total = max(0, total_value)
        column_totals[era]["fluzo"] = new_total
        room_data_changed = True # Asumimos que cambió para guardar

        # Verificar si AHORA se completa "Consecuencias Imprevistas"
        # [REFACTORIZADO] Esta verificación ahora necesita leer datos de Redis para OTRAS salas
        all_have_81 = True
        all_rooms_info = Auth.get_all_rooms()
        room_ids_to_check = [r['id'] for r in all_rooms_info]

        for check_room_id in room_ids_to_check:
            check_room_data = GameData.get_room_data(check_room_id) # Leer de Redis
            check_column_totals = check_room_data.get("column_totals", {})
            for check_era in ["pasado", "presente", "futuro"]:
                if check_column_totals.get(check_era, {}).get("fluzo", 0) != 81:
                    all_have_81 = False
                    break
            if not all_have_81: break

        message = ""
        if all_have_81:
            # ¡Se completó ahora!
            consecuencias_completado = True
            message = "Se ha completado Consecuencias Imprevistas"
            # Actualizar estado global en Redis
            GameData.set_global_counter("consecuencias_imprevistas", True)
            global_counters["consecuencias_imprevistas"] = True # Actualizar copia local

            # Emitir evento global de completado
            socketio.emit('consecuencias_imprevistas_completed', {'message': message})

        else:
            # No completado aún, determinar mensaje normal
            message = custom_message # Usar el del cliente si existe
            current_cycle = global_counters["perdicion_cycle"]
            if message is None: # Generar si no hay custom
                if current_cycle == 2: # Plan 1a, avance 1
                    if new_total < 78: message = "El valor de fluzo condensado es inferior a la media"
                    elif new_total > 78: message = "El valor de fluzo condensado es superior a la media"
                    elif new_total == 78: message = "¡Estas en la media! No alteres más..."
                elif current_cycle == 3: # Plan 1a, avance 2
                    if new_total < 81: message = "El valor de fluzo condensado es inferior a la media"
                    elif new_total > 81: message = "El valor de fluzo condensado es superior a la media"
                    elif new_total == 81: message = "¡Estas en la media! No alteres más..."

        # --- GUARDAR DATOS DE SALA ---
        if room_data_changed:
            if not GameData.save_room_data(room_id, room_data):
                 raise Exception("Error al guardar sala en Redis")
        # --- FIN GUARDAR DATOS ---

        # Verificar victoria general
        victory_conditions_met = check_victory_conditions()

        # --- EMITIR EVENTOS ---
        socketio.emit('fluzo_update', {
            'room_id': room_id, 'era': era, 'fluzoTotal': new_total,
            'fluzoValue': 0, 'checkedValue': checked_value,
            'message': message, 'consecuenciasCompleted': consecuencias_completado
        }, room=f"room_{room_id}")
        if victory_conditions_met:
             socketio.emit('victory_conditions_met', {'message': "->R1"})
        # --- FIN EMITIR EVENTOS ---

        return jsonify({
            "success": True, "fluzoTotal": new_total, "message": message,
            "consecuenciasCompleted": consecuencias_completado,
            "victory_conditions_met": victory_conditions_met
        })

    except Exception as e:
        error_msg = f"Error al comprobar fluzo: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({"success": False, "error": error_msg}), 500


# --- Funciones Auxiliares (Restauradas y adaptadas) ---

def deactivate_dependent_buttons(progress, dependency_key):
    """Desactiva recursivamente todos los botones que dependen de uno específico.
       Opera sobre el diccionario 'progress' local."""
    for era_loop in ["pasado", "presente", "futuro"]:
        if era_loop in progress and era_loop in GameData.button_dependencies:
            # Iterar sobre índices válidos para la era actual
            num_buttons = len(progress[era_loop])
            for idx in range(num_buttons):
                 dependencies = GameData.button_dependencies[era_loop].get(idx, [])
                 if dependency_key in dependencies:
                     if progress[era_loop][idx]: # Si está activo
                         progress[era_loop][idx] = False # Desactivar localmente
                         # Propagar recursivamente
                         deactivate_dependent_buttons(progress, f"{era_loop}-{idx}")

def get_available_buttons(progress):
    """Verifica qué botones están disponibles según dependencias actuales.
       Opera sobre el diccionario 'progress' local."""
    available_buttons = {}
    for era_loop in ["pasado", "presente", "futuro"]:
        available_buttons[era_loop] = []
        if era_loop in progress and era_loop in GameData.button_info:
             num_buttons = len(GameData.button_info[era_loop])
             # Asegurarse que progress[era_loop] tenga la longitud correcta
             if len(progress[era_loop]) < num_buttons:
                  # Podría pasar si se añaden botones y los datos de Redis son viejos
                  progress[era_loop].extend([False] * (num_buttons - len(progress[era_loop])))

             for i in range(num_buttons):
                 is_available = True
                 dependencies = GameData.button_dependencies.get(era_loop, {}).get(i, [])
                 for dep in dependencies:
                     try:
                         dep_era, dep_idx_str = dep.split('-')
                         dep_idx = int(dep_idx_str)
                         if not (dep_era in progress and dep_idx < len(progress[dep_era]) and progress[dep_era][dep_idx]):
                             is_available = False
                             break
                     except (ValueError, KeyError, IndexError):
                         is_available = False
                         print(f"Advertencia: Dependencia invÃ¡lida '{dep}' para botÃ³n {era_loop}-{i}")
                         break
                 available_buttons[era_loop].append(is_available)
        else:
              # Si no hay datos de progreso o info de botones, marcar como no disponibles
              if era_loop in GameData.button_info:
                   available_buttons[era_loop] = [False] * len(GameData.button_info[era_loop])
    return available_buttons

def check_victory_conditions():
    """Verifica condiciones de victoria leyendo datos de TODAS las salas desde Redis."""
    try:
        all_rooms_info = Auth.get_all_rooms()
        if not all_rooms_info: return False
        room_ids = [room['id'] for room in all_rooms_info]

        for room_id in room_ids:
            try:
                room_data = GameData.get_room_data(room_id) # Leer de Redis
                column_totals = room_data.get("column_totals", {})
                biff_disabled = room_data.get("biff_disabled", {})
                progress = room_data.get("progress", {})

                # 1. Biff
                for era in ["pasado", "presente", "futuro"]:
                    if not biff_disabled.get(era, False): return False
                # 2. Fluzo
                for era in ["pasado", "presente", "futuro"]:
                    if column_totals.get(era, {}).get("fluzo", 0) != 81: return False
                # 3. Noble Legado
                noble_legado_indices = {"pasado": 5, "presente": 4, "futuro": 3}
                for era, idx in noble_legado_indices.items():
                     era_progress = progress.get(era, [])
                     if not (len(era_progress) > idx and era_progress[idx]): return False
            except Exception as e_inner:
                 print(f"Error leyendo/verificando datos de sala {room_id} para victoria: {e_inner}")
                 return False # Error al leer datos de una sala implica no victoria

        return True # Si pasa todas las salas y condiciones

    except Exception as e:
        print(f"Error general en check_victory_conditions: {str(e)}")
        traceback.print_exc()
        return False


# --- Manejadores de Eventos Socket.IO (Sin Cambios) ---
@socketio.on('join')
def on_join(data):
    """Maneja cuando un cliente se une a una sala específica"""
    room = data.get('room')
    user_sid = request.sid # Obtener SID del cliente actual
    if room:
        join_room(room, sid=user_sid)
        print(f"Cliente {user_sid} unido a sala: {room}")
        if 'is_admin' in session and session['is_admin']:
            join_room('admin_room', sid=user_sid)
            print(f"Administrador {user_sid} unido a sala admin_room")

@socketio.on('leave')
def on_leave(data):
    """Maneja cuando un cliente abandona una sala específica"""
    room = data.get('room')
    user_sid = request.sid
    if room:
        leave_room(room, sid=user_sid)
        print(f"Cliente {user_sid} abandonó la sala: {room}")
        if 'is_admin' in session and session['is_admin']:
            leave_room('admin_room', sid=user_sid)
            print(f"Administrador {user_sid} abandonó la sala admin_room")

@socketio.on('disconnect')
def handle_disconnect():
    """Maneja la desconexión de un cliente"""
    user_sid = request.sid
    print(f"Cliente desconectado: {user_sid}")
    # Flask-SocketIO maneja leave_room automáticamente al desconectar