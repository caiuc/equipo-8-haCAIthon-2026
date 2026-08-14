import folium
import osmnx as ox
import networkx as nx
import os

# 1. Definir origen y destino
lat_origen, lon_origen = -33.6064, -70.5826
lat_destino, lon_destino = -33.6423, -70.3524

archivo_mapa = "mapa_cajon_maipo.graphml"

# 2. Lógica de carga
if os.path.exists(archivo_mapa):
    print("⚡ Cargando el mapa de calles desde tu disco duro...")
    G = ox.load_graphml(archivo_mapa)
else:
    print("⏳ Descargando un mapa MÁS GRANDE de internet (Ten paciencia nuevamente)...")
    # Agrandamos el margen (bbox) para que la ruta G-25 no se ampute en las curvas
    G = ox.graph_from_bbox(
        bbox=(-70.65, -33.75, -70.20, -33.50),
        network_type='drive'
    )
    print("💾 Guardando el nuevo mapa completo en tu computador...")
    ox.save_graphml(G, archivo_mapa)

print("✅ Mapa listo. Calculando la ruta real con NetworkX...")

# 3. Encontrar los Nodos
nodo_origen = ox.distance.nearest_nodes(G, X=lon_origen, Y=lat_origen)
nodo_destino = ox.distance.nearest_nodes(G, X=lon_destino, Y=lat_destino)

# 4. Calcular el camino más corto
ruta_nodos = nx.shortest_path(G, source=nodo_origen, target=nodo_destino, weight="length")

# 5. Extraer las coordenadas
ruta_coordenadas = [(G.nodes[nodo]['y'], G.nodes[nodo]['x']) for nodo in ruta_nodos]

# 6. Dibujar en Folium
mapa = folium.Map(location=[-33.6200, -70.4700], zoom_start=12)

folium.Marker([lat_origen, lon_origen], popup="📍 Metro Las Mercedes", icon=folium.Icon(color="green")).add_to(mapa)
folium.Marker([lat_destino, lon_destino], popup="📍 San José de Maipo", icon=folium.Icon(color="red")).add_to(mapa)

folium.PolyLine(
    locations=ruta_coordenadas,
    color="blue",
    weight=5,
    opacity=0.8,
    tooltip="Ruta real MB-72"
).add_to(mapa)

mapa.save("ruta_real_mb72.html")
print("✅ ¡Listo! Abre 'ruta_real_mb72.html' para ver la ruta completa.")
