import os
import json

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import (
    consultar_datos_propios_servicios,
    consultar_geolocalizacion_externa,
    calcular_ruta_externa,
)

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


def _limpiar_json(texto: str) -> dict:
    texto = (texto or "").replace("```json", "").replace("```", "").strip()
    return json.loads(texto)


# ---------------------------------------------------------------------------
# AGENTE 1: Analista Multimodal
#   Recibe: descripción del usuario + imagen
#   Herramientas: ninguna (solo el modelo multimodal)
#   Produce: JSON estructurado con clasificación y validación de coherencia
# ---------------------------------------------------------------------------
def agente_analista_multimodal(descripcion_usuario: str, imagen_bytes: bytes, mime_type: str) -> dict:
    prompt = f"""
Eres un Agente Analista Multimodal experto en incidentes viales y urbanos.
Analiza la imagen adjunta y la descripción del usuario: "{descripcion_usuario}".

Devuelve ÚNICAMENTE un objeto JSON plano con estas claves exactas:
- "tipo_incidente": string (ej: Choque, Vehículo volcado, Vehículo varado, Hueco en vía, Derrame de aceite, Otro)
- "gravedad": string, uno de: "Baja", "Media", "Alta", "Crítica"
- "heridos_visibles": boolean (true si la imagen sugiere personas heridas o atención médica)
- "servicio_recomendado": string, uno de: "Grúa", "Taller mecánico", "Ambulancia", "Policía de tránsito", "Ninguno"
- "observaciones_imagen": string (qué se ve realmente en la imagen, breve)
- "coherente_con_descripcion": boolean (true si la imagen coincide con la descripción)
- "evaluacion_coherencia": string (explica brevemente la coincidencia o contradicción)
- "informacion_suficiente": boolean (false si la imagen o el texto no permiten identificar el incidente)

No inventes datos que no se puedan ver en la imagen. Si algo es dudoso, dilo en los campos de texto.
"""
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            prompt,
            types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type),
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    try:
        data = _limpiar_json(response.text)
    except Exception:
        data = {
            "tipo_incidente": "No determinado",
            "gravedad": "Media",
            "heridos_visibles": False,
            "servicio_recomendado": "Ninguno",
            "observaciones_imagen": "",
            "coherente_con_descripcion": True,
            "evaluacion_coherencia": f"El modelo no devolvió JSON válido: {response.text}",
            "informacion_suficiente": False,
        }

    # Normalizar campos para que la app siempre pueda usarlos
    data.setdefault("tipo_incidente", "No determinado")
    data.setdefault("gravedad", "Media")
    data.setdefault("heridos_visibles", False)
    data.setdefault("servicio_recomendado", "Ninguno")
    data.setdefault("observaciones_imagen", "")
    data.setdefault("coherente_con_descripcion", True)
    data.setdefault("evaluacion_coherencia", "Sin evaluar")
    data.setdefault("informacion_suficiente", True)
    return data


# ---------------------------------------------------------------------------
# AGENTE 2: Logística y Rutas
#   Recibe: análisis estructurado del Agente 1 + coordenadas
#   Herramientas: datos propios (SQLite), geocodificación inversa externa,
#                 ruta externa (Geoapify)
#   Produce: recomendación en Markdown basada en datos reales consultados
# ---------------------------------------------------------------------------
_TIPO_SERVICIO = {
    "Grúa": "Servicio de Grúa",
    "Taller mecánico": "Taller Mecánico",
}


def agente_logistica_rutas(analisis: dict, latitud: float, longitud: float) -> dict:
    herramientas = []

    # Herramienta 1: geolocalización externa
    ubicacion = consultar_geolocalizacion_externa(latitud, longitud)
    herramientas.append("consultar_geolocalizacion_externa")

    # Herramienta 2: datos propios
    tipo = _TIPO_SERVICIO.get(analisis.get("servicio_recomendado"))
    servicios = consultar_datos_propios_servicios(latitud, longitud, tipo)
    herramientas.append("consultar_datos_propios_servicios")

    # Herramienta 3: ruta externa hasta el servicio más cercano
    ruta = None
    if servicios:
        s = servicios[0]
        ruta = calcular_ruta_externa(latitud, longitud, s["latitud"], s["longitud"])
        ruta["destino"] = s["nombre"]
        herramientas.append("calcular_ruta_externa")

    google_maps_url = f"https://www.google.com/maps/search/?api=1&query={latitud},{longitud}"
    waze_url = f"https://waze.com/ul?ll={latitud},{longitud}&navigate=yes"

    prompt = f"""
Eres un Agente de Logística y Rutas de Movilidad Urbana.
Genera una recomendación profesional y breve usando EXCLUSIVAMENTE los datos de abajo.
No inventes teléfonos, direcciones ni distancias que no aparezcan en los datos.

ANÁLISIS DEL INCIDENTE:
{json.dumps(analisis, ensure_ascii=False, indent=2)}

UBICACIÓN (geocodificación externa):
{json.dumps(ubicacion, ensure_ascii=False)}

SERVICIOS PROPIOS CERCANOS (ordenados por distancia, ya consultados en la base de datos):
{json.dumps(servicios, ensure_ascii=False, indent=2)}

RUTA AL SERVICIO MÁS CERCANO (servicio externo):
{json.dumps(ruta, ensure_ascii=False)}

FORMATO:
1. Usa encabezados Markdown (###), viñetas y negritas.
2. Incluye OBLIGATORIAMENTE estos enlaces:
   - 📍 [Ver ubicación en Google Maps]({google_maps_url})
   - 🚗 [Navegar hacia el punto en Waze]({waze_url})
3. Recomienda el servicio más cercano de la lista (nombre, teléfono, distancia).
   Si la lista está vacía, dilo claramente.
4. Si la gravedad es Alta o Crítica, o hay heridos visibles, indica primero llamar a la línea de emergencias 123.
5. Da instrucciones de seguridad vial claras y acordes al tipo de incidente.
"""
    response = client.models.generate_content(model=MODEL, contents=prompt)

    return {
        "recomendacion": response.text,
        "herramientas": herramientas,
        "contexto": {
            "ubicacion": ubicacion,
            "servicios_cercanos": servicios,
            "ruta": ruta,
        },
    }


# ---------------------------------------------------------------------------
# AGENTE 3: Chat contextual
#   Responde solo con la información guardada del caso (incluye resultados
#   de las herramientas).
# ---------------------------------------------------------------------------
def agente_chat_contextual(caso: dict, pregunta: str) -> str:
    prompt = f"""
Eres un asistente de soporte vial dentro de un chat contextual.
Responde ÚNICAMENTE con la información verificada del siguiente caso.

[DATOS DEL CASO]
- ID: {caso['id']}
- Fecha: {caso['fecha']}
- Descripción del usuario: {caso['descripcion']}
- Coordenadas: {caso['latitud']}, {caso['longitud']}
- Agentes que participaron: {', '.join(caso['agentes'])}
- Herramientas usadas: {', '.join(caso['herramientas'])}
- Acción ejecutada: {caso['accion']}
- Resultado completo (análisis, datos de herramientas y recomendación):
{json.dumps(caso['analisis'], ensure_ascii=False, indent=2)}

Pregunta del usuario: "{pregunta}"

Instrucción estricta: si la pregunta pide información que no está en los datos anteriores,
indica amablemente que no dispones de esa información. No inventes datos.
"""
    response = client.models.generate_content(model=MODEL, contents=prompt)
    return response.text