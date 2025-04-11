# app/models/game_data.py
import json
import random
from copy import deepcopy # Para crear copias de las estructuras por defecto

# Definir claves/prefijos de Redis
GLOBAL_COUNTERS_KEY = "global_counters"
ROOM_KEY_PREFIX = "room:"

class GameData:
    """Modelo para los datos del juego usando Redis"""

    # Mantenemos la informaciÃ³n estÃ¡tica de botones/dependencias aquÃ­
    button_info = {
        "pasado": [
            "Thomas y Mary se han conocido.", "Ha empezado la financiaciÃ³n de un observatorio.",
            "Thomas y Mary se han inspirado en Nikola Tesla.", "Thomas y Mary se han casado.",
            "Se ha plantado la semilla de un Ã¡rbol.", "Se ha aÃ±adido \"Un noble legado\" a la zona de victoria."
        ],
        "presente": [
            "Se han fundado Industrias Corrigan.", "Se ha construido el observatorio.",
            "Ha empezado la investigaciÃ³n sobre el teletransporte.", "Se ha pagado la deuda.",
            "Se ha aÃ±adido \"Un noble legado\" a la zona de victoria."
        ],
        "futuro": [
            "Thomas y Mary han realizado un descubrimiento histÃ³rico.", "Thomas y Mary han ganado un Premio Nobel.",
            "Coloca una semilla en la Universidad Miskatonic PASADO.", "Se ha aÃ±adido \"Un noble legado\" a la zona de victoria."
        ]
    }
    button_dependencies = {
         "pasado": { 0: [], 1: [], 2: [], 3: ["pasado-0"], 4: [], 5: [] },
         "presente": { 0: ["pasado-0"], 1: ["pasado-1"], 2: ["pasado-2", "presente-1"], 3: [], 4: [] },
         "futuro": { 0: ["presente-0", "presente-2"], 1: ["futuro-0"], 2: ["pasado-4"], 3: [] }
    }

    # Estructuras de datos por defecto
    _default_room_structure = None
    _default_global_counters = {
        "perdicion": 0, "reserva": 0, "perdicion_cycle": 1, "consecuencias_imprevistas": False,
    }

    @classmethod
    def _get_default_room_structure(cls):
        """Genera la estructura por defecto para una sala nueva."""
        if cls._default_room_structure is None:
            cls._default_room_structure = {
                "progress": {
                    "pasado": [False] * len(cls.button_info["pasado"]),
                    "presente": [False] * len(cls.button_info["presente"]),
                    "futuro": [False] * len(cls.button_info["futuro"])
                },
                "resources": {"pasado": 0, "presente": 0, "futuro": 0, "total": 0},
                "biff_defeats": {"pasado": 0, "presente": 0, "futuro": 0},
                "biff_disabled": {"pasado": False, "presente": False, "futuro": False},
                "column_totals": {
                    "pasado": {"perdicion": 0, "reserva": 0, "fluzo": 0}, # AÃ±adido fluzo por defecto
                    "presente": {"perdicion": 0, "reserva": 0, "fluzo": 0},
                    "futuro": {"perdicion": 0, "reserva": 0, "fluzo": 0}
                }
            }
        # Devolver una copia profunda para evitar modificaciones accidentales
        return deepcopy(cls._default_room_structure)

    @classmethod
    def initialize_defaults(cls, r):
        """Inicializa contadores globales por defecto si no existen."""
        if not r.exists(GLOBAL_COUNTERS_KEY):
            print(f"Inicializando {GLOBAL_COUNTERS_KEY} en Redis...")
            # Convertir valores a string para hmset si no son strings
            defaults_str = {k: str(v) for k, v in cls._default_global_counters.items()}
            r.hmset(GLOBAL_COUNTERS_KEY, defaults_str)

    @classmethod
    def _get_room_key(cls, room_id):
        """Genera la clave Redis para una sala."""
        return f"{ROOM_KEY_PREFIX}{room_id}"

    @classmethod
    def get_room_data(cls, room_id):
        """Obtiene los datos de una sala desde Redis."""
        from app import redis_client
        if not redis_client: return cls._get_default_room_structure() # Devuelve defecto si no hay conexiÃ³n

        room_key = cls._get_room_key(room_id)
        room_data_json = redis_client.get(room_key)

        if room_data_json:
            try:
                data = json.loads(room_data_json)
                # ValidaciÃ³n / MigraciÃ³n simple (asegurar campos existen)
                defaults = cls._get_default_room_structure()
                changed = False
                for k, v in defaults.items():
                    if k not in data:
                        data[k] = v
                        changed = True
                    # Asegurar sub-campos (ej: biff_disabled)
                    if isinstance(v, dict):
                         for sub_k, sub_v in v.items():
                              if k == "column_totals" and sub_k in data[k]: # para column_totals
                                   if "fluzo" not in data[k][sub_k]:
                                       data[k][sub_k]["fluzo"] = 0
                                       changed = True
                              elif sub_k not in data[k]:
                                   data[k][sub_k] = sub_v
                                   changed = True


                if changed: # Si aÃ±adimos campos faltantes, guardar de nuevo
                     cls.save_room_data(room_id, data)
                return data
            except json.JSONDecodeError:
                print(f"Error decodificando JSON para sala: {room_id}. Usando valores por defecto.")
                # Si hay error, podrÃ­amos borrar la clave corrupta y empezar de nuevo
                # redis_client.delete(room_key)
                return cls._get_default_room_structure()
        else:
            # La sala no existe en Redis, inicializarla
            print(f"Sala {room_id} no encontrada en Redis, inicializando...")
            default_data = cls._get_default_room_structure()
            cls.save_room_data(room_id, default_data)
            return default_data

    @classmethod
    def save_room_data(cls, room_id, data):
        """Guarda los datos de una sala en Redis."""
        from app import redis_client
        if not redis_client: return False

        room_key = cls._get_room_key(room_id)
        try:
            redis_client.set(room_key, json.dumps(data))
            return True
        except TypeError as e:
            print(f"Error serializando datos para sala {room_id}: {e}")
            return False
        except redis.exceptions.RedisError as e:
            print(f"Error de Redis guardando sala {room_id}: {e}")
            return False

    @classmethod
    def get_global_counters(cls):
        """Obtiene los contadores globales desde Redis."""
        from app import redis_client
        if not redis_client: return deepcopy(cls._default_global_counters) # Devuelve defecto si no hay conexiÃ³n

        counters = redis_client.hgetall(GLOBAL_COUNTERS_KEY)
        if not counters:
            # Si no existe, inicializar y devolver por defecto
            cls.initialize_defaults(redis_client)
            return deepcopy(cls._default_global_counters)

        # Convertir valores a tipos correctos
        result = {}
        defaults = cls._default_global_counters
        try:
            result["perdicion"] = int(counters.get("perdicion", defaults["perdicion"]))
            result["reserva"] = int(counters.get("reserva", defaults["reserva"]))
            result["perdicion_cycle"] = int(counters.get("perdicion_cycle", defaults["perdicion_cycle"]))
            # Convertir string 'True'/'False' a booleano
            consec_str = counters.get("consecuencias_imprevistas", str(defaults["consecuencias_imprevistas"]))
            result["consecuencias_imprevistas"] = consec_str.lower() == 'true'

             # AÃ±adir campos faltantes si es necesario
            updated = False
            for key, default_val in defaults.items():
                if key not in counters:
                    redis_client.hset(GLOBAL_COUNTERS_KEY, key, str(default_val))
                    result[key] = default_val # AÃ±adir al resultado devuelto
                    updated = True
            if updated:
                print(f"Actualizados campos faltantes en {GLOBAL_COUNTERS_KEY}")

        except (ValueError, TypeError) as e:
            print(f"Error convirtiendo tipos de contadores globales: {e}. Usando valores por defecto.")
            return deepcopy(cls._default_global_counters)

        return result

    @classmethod
    def increment_global_counter(cls, counter_name, amount):
        """Incrementa un contador global en Redis (atÃ³micamente)."""
        from app import redis_client
        if not redis_client: return None # O manejar el error de otra forma

        try:
            # HINCRBY es atÃ³mico
            return redis_client.hincrby(GLOBAL_COUNTERS_KEY, counter_name, amount)
        except redis.exceptions.RedisError as e:
            print(f"Error de Redis incrementando {counter_name}: {e}")
            return None

    @classmethod
    def set_global_counter(cls, counter_name, value):
        """Establece un valor especÃ­fico para un contador global."""
        from app import redis_client
        if not redis_client: return False
        try:
            # HSET para establecer valor
            redis_client.hset(GLOBAL_COUNTERS_KEY, counter_name, str(value))
            return True
        except redis.exceptions.RedisError as e:
            print(f"Error de Redis estableciendo {counter_name}: {e}")
            return False

    @classmethod
    def reset_perdicion_all_rooms(cls):
        """Reinicia el contador de perdiciÃ³n en todas las salas en Redis."""
        from app import redis_client
        if not redis_client: return False

        try:
            # Buscar todas las claves de sala
            room_keys = redis_client.keys(f"{ROOM_KEY_PREFIX}*")
            for room_key in room_keys:
                room_data_json = redis_client.get(room_key)
                if room_data_json:
                    try:
                        data = json.loads(room_data_json)
                        changed = False
                        # Asegurarse que column_totals existe
                        if "column_totals" not in data:
                             data["column_totals"] = deepcopy(cls._get_default_room_structure()["column_totals"])
                             changed = True

                        for era in ["pasado", "presente", "futuro"]:
                             # Asegurar que la era y perdicion existen
                             if era not in data["column_totals"]:
                                  data["column_totals"][era] = {"perdicion": 0, "reserva": 0, "fluzo": 0}
                                  changed = True
                             elif "perdicion" not in data["column_totals"][era]:
                                  data["column_totals"][era]["perdicion"] = 0
                                  changed = True

                             if data["column_totals"][era]["perdicion"] != 0:
                                data["column_totals"][era]["perdicion"] = 0
                                changed = True

                        if changed:
                            redis_client.set(room_key, json.dumps(data))
                    except json.JSONDecodeError:
                        print(f"Error decodificando JSON para sala {room_key} durante reset.")
                        continue
                    except TypeError as e:
                         print(f"Error serializando datos para sala {room_key} durante reset: {e}")
                         continue
            return True
        except redis.exceptions.RedisError as e:
            print(f"Error de Redis reseteando perdiciÃ³n en salas: {e}")
            return False

    @classmethod
    def reset_all_data(cls):
        """Resetea todos los datos del juego en Redis (salas y globales)."""
        from app import redis_client
        if not redis_client: return False
        try:
            # Borrar todas las claves de sala
            room_keys = redis_client.keys(f"{ROOM_KEY_PREFIX}*")
            if room_keys:
                redis_client.delete(*room_keys) # El * desempaqueta la lista
            # Borrar contadores globales
            redis_client.delete(GLOBAL_COUNTERS_KEY)
            # Re-inicializar globales por defecto para que existan
            cls.initialize_defaults(redis_client)
            print("Todos los datos de GameData reseteados en Redis.")
            return True
        except redis.exceptions.RedisError as e:
            print(f"Error de Redis reseteando todos los datos: {e}")
            return False

    # NO necesitamos save_column_totals o save_global_counters explÃ­citamente.
    # Los cambios se guardan en la estructura de datos de la sala y luego
    # se llama a save_room_data para guardar todo el objeto de sala.
    # Los contadores globales se actualizan directamente con HINCRBY/HSET.

    # Necesitamos REFACTORIZAR CÃ“MO SE ACTUALIZAN LOS DATOS en room_controller.py
    # Ya no modificaremos _game_data directamente.
    # El flujo serÃ¡:
    # 1. Obtener datos de sala: room_data = GameData.get_room_data(room_id)
    # 2. Modificar el diccionario room_data en Python.
    # 3. Guardar datos de sala: GameData.save_room_data(room_id, room_data)
    # 4. Para contadores globales: GameData.increment_global_counter(...) o GameData.set_global_counter(...)