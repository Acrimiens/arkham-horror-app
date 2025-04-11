from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.models.auth import Auth

# Crear blueprint para rutas de autenticación
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/', methods=['GET', 'POST'])
def index():
    """Gestiona la pantalla de login principal"""
    # Verificar si hay un código en la URL (para escaneo de QR)
    if request.method == 'GET' and 'code' in request.args:
        access_code = request.args.get('code', '').strip().lower()
        
        mesa_data = Auth.get_mesa_info(access_code)
        if mesa_data:
            # Código válido, asignar al grupo y era correspondiente
            group_id = mesa_data["group"]
            era = mesa_data["era"]
            session['assigned_group'] = group_id
            session['assigned_era'] = era
            session['is_admin'] = False
            session['mesa_code'] = access_code
            return redirect(url_for('game.era', room_id=group_id, era=era))
        else:
            # Código inválido
            flash('Código de acceso inválido. Por favor, intenta nuevamente.', 'error')
    
    if request.method == 'POST':
        # Si se envió un código de mesa
        if 'access_code' in request.form:
            access_code = request.form.get('access_code', '').strip().lower()
            
            mesa_data = Auth.get_mesa_info(access_code)
            if mesa_data:
                # Código válido, asignar al grupo y era correspondiente
                group_id = mesa_data["group"]
                era = mesa_data["era"]
                session['assigned_group'] = group_id
                session['assigned_era'] = era
                session['is_admin'] = False
                session['mesa_code'] = access_code
                return redirect(url_for('game.era', room_id=group_id, era=era))
            else:
                # Código inválido
                flash('Código de acceso inválido. Por favor, intenta nuevamente.', 'error')
        
        # Si se enviaron credenciales de administrador
        elif 'admin_username' in request.form and 'admin_password' in request.form:
            username = request.form.get('admin_username', '').strip()
            password = request.form.get('admin_password', '').strip()
            
            if Auth.validate_admin(username, password):
                # Admin válido
                session['is_admin'] = True
                session.pop('assigned_group', None)  # Eliminar grupo específico ya que es admin
                session.pop('assigned_era', None)    # Eliminar era específica ya que es admin
                session.pop('mesa_code', None)       # Eliminar código de mesa ya que es admin
                return redirect(url_for('admin.panel'))
            else:
                # Credenciales inválidas
                flash('Credenciales de administrador inválidas.', 'error')
    
    # Si el usuario ya tiene una sesión
    if 'is_admin' in session and session['is_admin']:
        return redirect(url_for('admin.panel'))
    elif 'assigned_group' in session and 'assigned_era' in session:
        return redirect(url_for('game.era', room_id=session['assigned_group'], era=session['assigned_era']))
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """Gestiona el cierre de sesión"""
    # Simplemente limpiar todas las variables de sesión
    # No intentamos usar leave_room aquí ya que puede causar errores
    # La desconexión de Socket.IO se maneja automáticamente cuando el cliente se desconecta
    session.clear()
    
    # Redireccionar a la página de inicio
    return redirect(url_for('auth.index'))
