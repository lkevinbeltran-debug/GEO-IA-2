import os
import math
import requests

from database import obtener_servicios_propios, guardar_caso


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# HERRAMIENTA 1: datos propios (SQLite)
# ---------------------------------------------------------------------------
def consultar_datos_propios_servicios(latitud: float, longitud: float, tipo: str | None = None):
    """Consulta talleres y grúas de la base de datos propia, ordenados por cercanía."""
    servicios = obtener_servicios_propios()
    if tipo:
        filtrados = [s for s in servicios if s["tipo"] == tipo]
        servicios = filtrados or servicios  # si no hay de ese tipo, devuelve todos

    for s in servicios:
        s["distancia_km"] = round(_haversine_km(latitud, longitud, s["latitud"], s["longitud"]), 2)
    return sorted(servicios, key=lambda s: s["distancia_km"])


# ---------------------------------------------------------------------------
# HERRAMIENTA 2: geolocalización externa (Geoapify, con respaldo en Nominatim)
# ---------------------------------------------------------------------------
def consultar_geolocalizacion_externa(latitud: float, longitud: float):
    """Geocodificación inversa: devuelve dirección, barrio y ciudad de unas coordenadas."""
    api_key = os.getenv("GEOAPIFY_API_KEY", "")
    if api_key:
        try:
            url = (
                "https://api.geoapify.com/v1/geocode/reverse"
                f"?lat={latitud}&lon={longitud}&apiKey={api_key}"
            )
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("features"):
                    props = data["features"][0]["properties"]
                    return {
                        "direccion": props.get("formatted", "Ubicación detectada"),
                        "barrio": props.get("suburb", "N/A"),
                        "ciudad": props.get("city", "N/A"),
                        "fuente": "Geoapify",
                    }
        except Exception:
            pass

    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitud}&lon={longitud}"
        resp = requests.get(url, headers={"User-Agent": "SafeRouteApp/1.0"}, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})
            return {
                "direccion": data.get("display_name", "Ubicación detectada"),
                "barrio": addr.get("suburb", "N/A"),
                "ciudad": addr.get("city", "N/A"),
                "fuente": "OpenStreetMap/Nominatim",
            }
    except Exception:
        pass

    return {
        "direccion": f"Coordenadas: {latitud}, {longitud}",
        "barrio": "Desconocido",
        "ciudad": "Desconocido",
        "fuente": "sin servicio externo disponible",
    }


# ---------------------------------------------------------------------------
# HERRAMIENTA 3: ruta externa (Geoapify Routing, con respaldo en línea recta)
# ---------------------------------------------------------------------------
def calcular_ruta_externa(lat_o: float, lon_o: float, lat_d: float, lon_d: float):
    """Calcula distancia y tiempo en carro entre dos puntos."""
    api_key = os.getenv("GEOAPIFY_API_KEY", "")
    if api_key:
        try:
            url = (
                "https://api.geoapify.com/v1/routing"
                f"?waypoints={lat_o},{lon_o}|{lat_d},{lon_d}&mode=drive&apiKey={api_key}"
            )
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                props = resp.json()["features"][0]["properties"]
                return {
                    "distancia_km": round(props["distance"] / 1000, 2),
                    "tiempo_min": round(props["time"] / 60, 1),
                    "fuente": "Geoapify Routing",
                }
        except Exception:
            pass

    km = round(_haversine_km(lat_o, lon_o, lat_d, lon_d), 2)
    return {"distancia_km": km, "tiempo_min": None, "fuente": "estimación en línea recta"}


# ---------------------------------------------------------------------------
# ACCIÓN: registrar el caso en el sistema (cambio real en la base de datos)
# ---------------------------------------------------------------------------
def registrar_caso_en_sistema(descripcion, latitud, longitud, contexto, agentes, herramientas, accion) -> int:
    return guardar_caso(
        descripcion=descripcion,
        lat=latitud,
        lon=longitud,
        analisis=contexto,
        agentes=agentes,
        herramientas=herramientas,
        accion=accion,
    )