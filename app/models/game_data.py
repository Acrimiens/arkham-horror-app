import random

class GameData:
    """Modelo para los datos del juego"""
    
    # Información de botones para cada era
    button_info = {
        "pasado": [
            "Thomas y Mary se han conocido.",
            "Ha empezado la financiación de un observatorio.",
            "Thomas y Mary se han inspirado en Nikola Tesla.",
            "Thomas y Mary se han casado.",
            "Se ha plantado la semilla de un árbol.",
            "Se ha añadido \"Un noble legado\" a la zona de victoria."
        ],
        "presente": [
            "Se han fundado Industrias Corrigan.",
            "Se ha construido el observatorio.",
            "Ha empezado la investigación sobre el teletransporte.",
            "Se ha pagado la deuda.",
            "Se ha plantado la semilla de un árbol.",  # Nuevo botón añadido
            "Se ha añadido \"Un noble legado\" a la zona de victoria."
        ],
        "futuro": [
            "Thomas y Mary han realizado un descubrimiento histórico.",
            "Thomas y Mary han ganado un Premio Nobel.",
            "Coloca una semilla en la Universidad Miskatonic PASADO.",
            "Se ha plantado la semilla de un árbol.",  # Nuevo botón añadido
            "Se ha añadido \"Un noble legado\" a la zona de victoria."
        ]
    }
    
    # Dependencias de los botones
    button_dependencies = {
        "pasado": {
            0: [],  # Pasado 1: Se puede activar libremente
            1: [],  # Pasado 2: Se puede activar libremente
            2: [],  # Pasado 3: Se puede activar libremente
            3: ["pasado-0"],  # Pasado 4: Requiere Pasado 1
            4: ["futuro-2"],   # Pasado 5: Se puede activar libremente
            5: []   # Pasado 6 (Noble legado): Se puede activar libremente
        },
        "presente": {
            0: ["pasado-0"],  # Presente 1: Requiere Pasado 1
            1: ["pasado-1"],  # Presente 2: Requiere Pasado 2
            2: ["pasado-2", "presente-1"],  # Presente 3: Requiere Pasado 3 y Presente 2
            3: [],  # Presente 4: Se puede activar libremente
            4: ["pasado-4"],  # Presente 5 (Semilla árbol): Requiere Pasado 5 (semilla en pasado)
            5: []   # Presente 6 (Noble legado): Se puede activar libremente
        },
        "futuro": {
            0: ["presente-0", "presente-2"],  # Futuro 1: Requiere Presente 1 y Presente 3
            1: ["futuro-0"],  # Futuro 2: Requiere Futuro 1
            2: [],  # Futuro 3: Se puede activar libremente
            3: ["pasado-4"],  # Futuro 4 (Semilla árbol): Requiere Pasado 5 (semilla en pasado)
            4: []   # Futuro 5 (Noble legado): Se puede activar libremente
        }
    }
    
    # Almacenamiento del progreso y recursos
    _game_data = {}
    
    @classmethod
    def initialize_room_data(cls, room_id):
        """Inicializa o carga datos de una sala"""
        room_key = f"room_{room_id}"
        if room_key not in cls._game_data:
            cls._game_data[room_key] = {
                "progress": {
                    "pasado": [False] * len(cls.button_info["pasado"]),
                    "presente": [False] * len(cls.button_info["presente"]),
                    "futuro": [False] * len(cls.button_info["futuro"])
                },
                "resources": {
                    "pasado": 0,
                    "presente": 0,
                    "futuro": 0,
                    "total": 0
                },
                "biff_defeats": {
                    "pasado": 0,
                    "presente": 0,
                    "futuro": 0
                },
                "biff_disabled": {
                    "pasado": False,
                    "presente": False,
                    "futuro": False
                }
            }
        # Asegurar retrocompatibilidad: si el campo biff_disabled no existe, añadirlo
        elif "biff_disabled" not in cls._game_data[room_key]:
            cls._game_data[room_key]["biff_disabled"] = {
                "pasado": False,
                "presente": False,
                "futuro": False
            }
        return cls._game_data[room_key]
    
    @classmethod
    def initialize_global_counters(cls):
        """Inicializa los contadores globales"""
        if "global_counters" not in cls._game_data:
            cls._game_data["global_counters"] = {
                "perdicion": 0,
                "reserva": 0,
                "perdicion_cycle": 1,  # Ciclo 1, 2 o 3
                "consecuencias_imprevistas": False,  # Nuevo campo para Consecuencias Imprevistas
            }
        else:
            # Asegurar que los campos existan en datos existentes
            if "perdicion_cycle" not in cls._game_data["global_counters"]:
                cls._game_data["global_counters"]["perdicion_cycle"] = 1
            if "consecuencias_imprevistas" not in cls._game_data["global_counters"]:
                cls._game_data["global_counters"]["consecuencias_imprevistas"] = False
    
        return cls._game_data["global_counters"]
    
    @classmethod
    def initialize_room_column_totals(cls, room_id):
        """Inicializa los contadores por columna en una sala"""
        room_key = f"room_{room_id}"
        room_data = cls.initialize_room_data(room_id)
        
        if "column_totals" not in room_data:
            room_data["column_totals"] = {
                "pasado": {
                    "perdicion": 0,
                    "reserva": 0
                },
                "presente": {
                    "perdicion": 0,
                    "reserva": 0
                },
                "futuro": {
                    "perdicion": 0,
                    "reserva": 0
                }
            }
        # Asegurar compatibilidad con versiones anteriores
        elif not isinstance(room_data["column_totals"].get("perdicion", {}), dict):
            # Convertir formato antiguo a nuevo formato
            old_totals = room_data["column_totals"].copy()
            room_data["column_totals"] = {
                "pasado": {
                    "perdicion": 0,
                    "reserva": 0
                },
                "presente": {
                    "perdicion": 0,
                    "reserva": 0
                },
                "futuro": {
                    "perdicion": 0,
                    "reserva": 0
                }
            }
        
        return room_data["column_totals"]
    
    @classmethod
    def save_column_totals(cls, room_id, column_totals):
        """Guarda los totales de columna en la estructura de datos en memoria"""
        room_key = f"room_{room_id}"
        if room_key in cls._game_data:
            cls._game_data[room_key]["column_totals"] = column_totals
        return True
    
    @classmethod
    def save_global_counters(cls, global_counters):
        """Guarda los contadores globales en la estructura de datos en memoria"""
        cls._game_data["global_counters"] = global_counters
        return True
    
    @classmethod
    def reset_perdicion_all_rooms(cls):
        """Reinicia el contador de perdición en todas las salas"""
        # Iterar por todas las salas
        for key in list(cls._game_data.keys()):
            # Solo procesar las llaves que corresponden a salas
            if key.startswith("room_"):
                # Asegurarse de que existe la estructura de column_totals
                if "column_totals" in cls._game_data[key]:
                    # Reiniciar el contador de perdición para todas las eras en esta sala
                    for era in ["pasado", "presente", "futuro"]:
                        if era in cls._game_data[key]["column_totals"]:
                            cls._game_data[key]["column_totals"][era]["perdicion"] = 0
        
        return True
    
    @classmethod
    def reset_all_data(cls):
        """Resetea todos los datos del juego"""
        cls._game_data = {}
        # Inicializar contadores globales para evitar errores
        cls.initialize_global_counters()
        return True