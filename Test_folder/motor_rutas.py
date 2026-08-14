import re
import requests
from dataclasses import dataclass
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

# Reutilizamos la misma estructura de tu bot original
@dataclass
class Sugerencia:
    nombre: str
    tipo: str
    tiempo_min: float
    costo_clp: int

# Inicializamos el geocodificador (OpenStreetMap)
# Se requiere un user_agent personalizado por políticas de OSM
geolocator = Nominatim(user_agent="mi_bot_transporte_santiago_v1")

# URL de tu servidor OpenTripPlanner corriendo localmente
OTP_API_URL = "http://localhost:8080/otp/routers/default/plan"

def extraer_coordenadas(texto: str) -> tuple[float, float] | None:
    """
    Si el texto viene del GPS del bot (ej: 'Mi ubicación actual (-33.45, -70.66)'),
    extrae las coordenadas. Si no, devuelve None.
    """
    match = re.search(r"Mi ubicación actual \(([-.\d]+),\s*([-.\d]+)\)", texto)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None

def geocodificar(lugar: str) -> tuple[float, float] | None:
    """Busca un texto en OpenStreetMap y devuelve (Lat, Lon)."""
    # Si ya son coordenadas enviadas por GPS
    coords_gps = extraer_coordenadas(lugar)
    if coords_gps:
        return coords_gps

    # Si es texto, buscamos en OSM (le agregamos 'Santiago, Chile' para dar contexto)
    query = f"{lugar}, Santiago, Chile"
    try:
        location = geolocator.geocode(query, timeout=5)
        if location:
            return (location.latitude, location.longitude)
    except GeocoderTimedOut:
        print(f"Error: Timeout al buscar {query}")
    
    return None

def consultar_rutas_bd_real(origen_texto: str, destino_texto: str, orden: str) -> list[Sugerencia]:
    """
    Esta es la función que REEMPLAZARÁ a consultar_rutas_bd en tu bot principal.
    """
    coords_origen = geocodificar(origen_texto)
    coords_destino = geocodificar(destino_texto)

    if not coords_origen or not coords_destino:
        print("No se pudieron geocodificar los puntos.")
        return []

    # Parámetros para OpenTripPlanner
    params = {
        "fromPlace": f"{coords_origen[0]},{coords_origen[1]}",
        "toPlace": f"{coords_destino[0]},{coords_destino[1]}",
        "time": "8:00am", # Puedes dinamizar esto con datetime.now()
        "date": "08-14-2026", 
        "mode": "TRANSIT,WALK", # Transporte público + caminar
        "maxWalkDistance": 1000, # Máximo a caminar en metros
        "arriveBy": "false"
    }

    try:
        response = requests.get(OTP_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error conectando con OpenTripPlanner: {e}")
        return []

    sugerencias = []
    
    # OTP devuelve 'itineraries' (rutas sugeridas)
    itinerarios = data.get("plan", {}).get("itineraries", [])
    
    for itinerario in itinerarios:
        # Calcular tiempo en minutos
        tiempo_min = round(itinerario["duration"] / 60)
        
        # Extraer los buses/metros de esta ruta
        tramos_transporte = [leg for leg in itinerario["legs"] if leg["mode"] in ["BUS", "SUBWAY", "TRAM"]]
        
        if not tramos_transporte:
            continue # Es una ruta solo caminando
            
        # Crear un nombre descriptivo (ej: "Micro 210 -> Metro L4")
        nombres_rutas = [leg.get("route", "") for leg in tramos_transporte]
        nombre_final = " -> ".join(filter(None, nombres_rutas))
        
        # Identificar el tipo principal
        tipo = "Mixto"
        if all(leg["mode"] == "BUS" for leg in tramos_transporte): tipo = "Micro"
        elif all(leg["mode"] == "SUBWAY" for leg in tramos_transporte): tipo = "Metro"

        # Costo aproximado (OTP puede calcular tarifas si se configura, pero aquí podemos poner un mock inteligente)
        # Tarifa integrada DTPM (Red) general:
        costo_clp = 730 if tipo == "Micro" else 830 

        sugerencias.append(Sugerencia(
            nombre=nombre_final,
            tipo=tipo,
            tiempo_min=tiempo_min,
            costo_clp=costo_clp
        ))

    # Ordenar según preferencia del usuario
    clave = (lambda s: s.tiempo_min) if orden == "tiempo" else (lambda s: s.costo_clp)
    return sorted(sugerencias, key=clave)