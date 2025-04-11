class Auth:
    """Modelo para autenticación y control de acceso"""
    
    # Códigos de acceso para cada mesa, con su respectivo grupo y era
    _mesa_access_codes = {
        "mesa01": {"group": 1, "era": "pasado"},   # Mesa 01 accede al Grupo 1, era Pasado
        "mesa02": {"group": 1, "era": "presente"}, # Mesa 02 accede al Grupo 1, era Presente
        "mesa03": {"group": 1, "era": "futuro"},   # Mesa 03 accede al Grupo 1, era Futuro
        
    }
    
    # Usuarios administradores (con acceso completo)
    _admin_users = {
        "admin1": "clave1",  # Usuario: admin1, Contraseña: clave1
        "admin2": "clave2",
        "admin3": "clave3",
        "admin4": "clave4",
        "admin5": "clave5",
    }
    
    # Lista de salas/grupos disponibles
    _rooms = [{"name": f"Grupo {i+1}", "id": i+1} for i in range(2)]
    
    @classmethod
    def get_mesa_info(cls, access_code):
        """Obtiene la información de una mesa a partir de su código de acceso"""
        access_code = access_code.strip().lower()
        return cls._mesa_access_codes.get(access_code)
    
    @classmethod
    def validate_admin(cls, username, password):
        """Valida las credenciales de un administrador"""
        return cls._admin_users.get(username) == password
    
    @classmethod
    def get_all_rooms(cls):
        """Retorna todas las salas/grupos disponibles"""
        return cls._rooms
    
    @classmethod
    def get_room_by_id(cls, room_id):
        """Busca una sala por su ID"""
        return next((r for r in cls._rooms if r["id"] == room_id), None)
    
    @classmethod
    def add_room(cls):
        """Añade una nueva sala/grupo"""
        next_id = max([r["id"] for r in cls._rooms]) + 1 if cls._rooms else 1
        new_room = {"name": f"Grupo {next_id}", "id": next_id}
        cls._rooms.append(new_room)
        
        # Crear códigos de mesa para el nuevo grupo (uno para cada era)
        last_mesa_num = 0
        for mesa_code in cls._mesa_access_codes.keys():
            if mesa_code.startswith('mesa'):
                try:
                    num = int(mesa_code[4:])
                    if num > last_mesa_num:
                        last_mesa_num = num
                except ValueError:
                    # Ignorar si el formato no es mesakk donde kk es un número
                    pass
        
        # Crear los nuevos códigos de mesa
        for i, era in enumerate(['pasado', 'presente', 'futuro']):
            new_mesa_num = last_mesa_num + 1 + i
            new_mesa_code = f"mesa{new_mesa_num:02d}"  # Formato: mesa10, mesa11, etc.
            
            # Añadir el nuevo código al diccionario
            cls._mesa_access_codes[new_mesa_code] = {
                "group": next_id,
                "era": era
            }
        
        return new_room
    
    @classmethod
    def get_all_mesa_codes(cls):
        """Retorna todos los códigos de mesa disponibles"""
        return cls._mesa_access_codes
