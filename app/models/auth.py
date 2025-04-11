# app/models/auth.py
import json # Necesario para codificar/decodificar datos de mesa

# Definir claves de Redis
ADMIN_USERS_KEY = "admin_users"
MESA_CODES_KEY = "mesa_codes"
# No almacenaremos _rooms directamente, se derivarÃ¡

class Auth:
    """Modelo para autenticaciÃ³n y control de acceso usando Redis"""

    @classmethod
    def initialize_defaults(cls, r):
        """Inicializa datos por defecto en Redis si no existen."""
        if not r.exists(ADMIN_USERS_KEY):
            print(f"Inicializando {ADMIN_USERS_KEY} en Redis...")
            initial_admins = {
                "admin1": "clave1", "admin2": "clave2", "admin3": "clave3",
                "admin4": "clave4", "admin5": "clave5",
            }
            r.hmset(ADMIN_USERS_KEY, initial_admins)

        if not r.exists(MESA_CODES_KEY):
            print(f"Inicializando {MESA_CODES_KEY} en Redis...")
            initial_mesas = {
                "mesa01": json.dumps({"group": 1, "era": "pasado"}),
                "mesa02": json.dumps({"group": 1, "era": "presente"}),
                "mesa03": json.dumps({"group": 1, "era": "futuro"}),
                # AÃ±ade mÃ¡s mesas iniciales si las tenÃ­as
                 "mesa04": json.dumps({"group": 2, "era": "pasado"}),
                 "mesa05": json.dumps({"group": 2, "era": "presente"}),
                 "mesa06": json.dumps({"group": 2, "era": "futuro"}),
            }
            r.hmset(MESA_CODES_KEY, initial_mesas)

    @classmethod
    def get_mesa_info(cls, access_code):
        """Obtiene la informaciÃ³n de una mesa desde Redis"""
        from app import redis_client # Importar cliente global
        if not redis_client: return None # Manejar fallo de conexiÃ³n

        access_code = access_code.strip().lower()
        mesa_data_json = redis_client.hget(MESA_CODES_KEY, access_code)
        if mesa_data_json:
            try:
                return json.loads(mesa_data_json)
            except json.JSONDecodeError:
                print(f"Error decodificando JSON para mesa: {access_code}")
                return None
        return None

    @classmethod
    def validate_admin(cls, username, password):
        """Valida las credenciales de un administrador desde Redis"""
        from app import redis_client
        if not redis_client: return False

        stored_password = redis_client.hget(ADMIN_USERS_KEY, username)
        return stored_password == password

    @classmethod
    def get_all_rooms(cls):
        """Retorna todas las salas/grupos disponibles derivÃ¡ndolos de Redis"""
        from app import redis_client
        if not redis_client: return []

        all_mesas = redis_client.hgetall(MESA_CODES_KEY)
        groups = set()
        for mesa_data_json in all_mesas.values():
            try:
                mesa_data = json.loads(mesa_data_json)
                groups.add(mesa_data["group"])
            except (json.JSONDecodeError, KeyError):
                continue # Ignorar datos malformados

        # Ordenar y crear la lista de diccionarios
        sorted_groups = sorted(list(groups))
        return [{"name": f"Grupo {group_id}", "id": group_id} for group_id in sorted_groups]

    @classmethod
    def get_room_by_id(cls, room_id):
        """Busca una sala por su ID (verifica si existe el grupo en Redis)"""
        from app import redis_client
        if not redis_client: return None

        all_mesas = redis_client.hgetall(MESA_CODES_KEY)
        for mesa_data_json in all_mesas.values():
            try:
                mesa_data = json.loads(mesa_data_json)
                if mesa_data.get("group") == room_id:
                    return {"name": f"Grupo {room_id}", "id": room_id} # Encontrado
            except (json.JSONDecodeError, KeyError):
                continue
        return None # No encontrado

    @classmethod
    def add_room(cls):
        """AÃ±ade una nueva sala/grupo y sus mesas a Redis"""
        from app import redis_client
        if not redis_client: return None

        all_mesas = redis_client.hgetall(MESA_CODES_KEY)
        last_mesa_num = 0
        existing_groups = set()

        for mesa_code, mesa_data_json in all_mesas.items():
            if mesa_code.startswith('mesa'):
                try:
                    num = int(mesa_code[4:])
                    if num > last_mesa_num:
                        last_mesa_num = num
                except ValueError:
                    pass # Ignorar formato invÃ¡lido
            try:
                mesa_data = json.loads(mesa_data_json)
                existing_groups.add(mesa_data["group"])
            except (json.JSONDecodeError, KeyError):
                pass

        next_group_id = max(existing_groups) + 1 if existing_groups else 1

        new_mesas = {}
        for i, era in enumerate(['pasado', 'presente', 'futuro']):
            new_mesa_num = last_mesa_num + 1 + i
            new_mesa_code = f"mesa{new_mesa_num:02d}"
            new_mesa_data = {"group": next_group_id, "era": era}
            new_mesas[new_mesa_code] = json.dumps(new_mesa_data)

        if new_mesas:
            redis_client.hmset(MESA_CODES_KEY, new_mesas)

        return {"name": f"Grupo {next_group_id}", "id": next_group_id}

    @classmethod
    def get_all_mesa_codes(cls):
        """Retorna todos los cÃ³digos de mesa disponibles desde Redis"""
        from app import redis_client
        if not redis_client: return {}

        all_mesas_json = redis_client.hgetall(MESA_CODES_KEY)
        result = {}
        for code, data_json in all_mesas_json.items():
            try:
                result[code] = json.loads(data_json)
            except json.JSONDecodeError:
                print(f"Error decodificando JSON para mesa: {code}")
                continue
        return result