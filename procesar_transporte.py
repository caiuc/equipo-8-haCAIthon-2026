import math
import os
import folium
import networkx as nx
import pandas as pd

# 1. Carpeta con tus datos GTFS
GTFS_DIR = "datos_gtfs"

print("⏳ 1/4 - Cargando datos con Pandas...")
df_routes = pd.read_csv(os.path.join(GTFS_DIR, "routes.txt"))
df_trips = pd.read_csv(os.path.join(GTFS_DIR, "trips.txt"))
df_shapes = pd.read_csv(os.path.join(GTFS_DIR, "shapes.txt"))

# 2. Seleccionar la primera ruta y extraer sus puntos GPS
ruta_ejemplo = df_routes.iloc[0]["route_id"]
nombre_linea = df_routes.iloc[0].get("route_short_name", ruta_ejemplo)
print(f"🚌 2/4 - Procesando recorrido de la línea: {nombre_linea}")

trips = df_trips[df_trips["route_id"] == ruta_ejemplo]
id_forma = trips.iloc[0]["shape_id"]

# Puntos ordenados de la ruta
puntos = (
    df_shapes[df_shapes["shape_id"] == id_forma]
    .sort_values(by="shape_pt_sequence")
    .reset_index(drop=True)
)


# Función para calcular distancia física en metros entre 2 coordenadas (Haversine)
def calcular_distancia_metros(lat1, lon1, lat2, lon2):
  r = 6371000  # Radio de la Tierra en metros
  phi1, phi2 = math.radians(lat1), math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlambda = math.radians(lon2 - lon1)
  a = (
      math.sin(dphi / 2) ** 2
      + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
  )
  return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# 3. Construir el Grafo con NetworkX
print("🕸️ 3/4 - Creando grafo de transporte en NetworkX...")
G = nx.DiGraph()  # Grafo dirigido (las micros van en un sentido)

coords_para_mapa = []

for i in range(len(puntos) - 1):
  nodo_actual = i
  nodo_siguiente = i + 1

  lat_a, lon_a = puntos.iloc[i]["shape_pt_lat"], puntos.iloc[i]["shape_pt_lon"]
  lat_b, lon_b = (
      puntos.iloc[i + 1]["shape_pt_lat"],
      puntos.iloc[i + 1]["shape_pt_lon"],
  )

  coords_para_mapa.append((lat_a, lon_a))

  # Guardar los nodos con sus coordenadas
  G.add_node(nodo_actual, pos=(lat_a, lon_a))
  G.add_node(nodo_siguiente, pos=(lat_b, lon_b))

  # Calcular distancia y tiempo estimado (suponiendo 25 km/h = 6.94 m/s)
  distancia_m = calcular_distancia_metros(lat_a, lon_a, lat_b, lon_b)
  tiempo_segundos = distancia_m / 6.94

  # Unir los dos puntos con una arista ponderada por distancia y tiempo
  G.add_edge(
      nodo_actual,
      nodo_siguiente,
      distancia=distancia_m,
      tiempo=tiempo_segundos,
      linea=nombre_linea,
  )

coords_para_mapa.append((puntos.iloc[-1]["shape_pt_lat"], puntos.iloc[-1]["shape_pt_lon"]))

# 4. Calcular la ruta completa con NetworkX
nodo_inicio = 0
nodo_fin = len(puntos) - 1

camino_nodos = nx.shortest_path(
    G, source=nodo_inicio, target=nodo_fin, weight="distancia"
)
distancia_total = nx.path_weight(G, camino_nodos, weight="distancia")
tiempo_total_min = (
    nx.path_weight(G, camino_nodos, weight="tiempo") / 60
)

print("\n--- 🎯 RESULTADO DEL PROCESAMIENTO ---")
print(f"• Línea modelada: {nombre_linea}")
print(f"• Total de nodos en el grafo: {G.number_of_nodes()}")
print(f"• Distancia total del trayecto: {round(distancia_total / 1000, 2)} km")
print(f"• Tiempo estimado de viaje: {round(tiempo_total_min, 1)} minutos")

# 5. Generar archivo de mapa interactivo HTML para la demo
centro_lat, centro_lon = coords_para_mapa[0]
mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=13)
folium.PolyLine(
    coords_para_mapa,
    color="blue",
    weight=5,
    opacity=0.8,
    popup=f"Recorrido {nombre_linea}",
).add_to(mapa)
mapa.save("mapa_recorrido.html")
print("🗺️ Archivo visual 'mapa_recorrido.html' generado con éxito.")
