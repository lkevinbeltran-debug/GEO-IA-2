import os
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import init_db, obtener_caso_por_id, listar_casos
from agents import (
    agente_analista_multimodal,
    agente_logistica_rutas,
    agente_chat_contextual,
)
from tools import registrar_caso_en_sistema

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SafeRoute & Rescue Urbano API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# ORQUESTADOR: decide el orden y las condiciones en que participan agentes
# y herramientas.
#   1. Agente Analista Multimodal  -> análisis estructurado (texto + imagen)
#   2. Si la información es suficiente -> Agente de Logística y Rutas
#      (usa herramientas: datos propios, geolocalización y ruta externa)
#      Si NO es suficiente -> se omite el Agente 2 y se pide más información
#   3. Acción del sistema: registrar el caso en la base de datos
# ---------------------------------------------------------------------------
@app.post("/api/procesar-incidente")
async def procesar_incidente(
    descripcion: str = Form(...),
    latitud: float = Form(...),
    longitud: float = Form(...),
    imagen: UploadFile = File(...),
):
    if not (imagen.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen.")

    imagen_bytes = await imagen.read()

    pasos = []
    agentes = []
    herramientas = []
    advertencias = []

    # --- Paso 1: Agente Analista -------------------------------------------
    try:
        analisis = agente_analista_multimodal(descripcion, imagen_bytes, imagen.content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falla en el Agente Analista (Gemini): {e}")

    agentes.append("Agente Analista Multimodal")
    pasos.append("1. Agente Analista Multimodal analizó texto + imagen y devolvió JSON estructurado.")

    if not analisis.get("coherente_con_descripcion", True):
        advertencias.append(
            "La imagen no parece coincidir con la descripción del usuario. Verifica los datos del reporte."
        )

    # --- Paso 2: decisión condicional --------------------------------------
    contexto_herramientas = {}
    if analisis.get("informacion_suficiente", True):
        try:
            resultado = agente_logistica_rutas(analisis, latitud, longitud)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Falla en el Agente de Logística (Gemini): {e}")

        recomendacion = resultado["recomendacion"]
        contexto_herramientas = resultado["contexto"]
        herramientas.extend(resultado["herramientas"])
        agentes.append("Agente de Logística y Rutas")
        pasos.append(
            "2. Información suficiente: el Agente de Logística consultó herramientas y generó la recomendación."
        )
        estado = "PROCESADO"
    else:
        recomendacion = (
            "### ⚠️ Información insuficiente\n"
            "No fue posible clasificar el incidente con confianza.\n\n"
            "- Adjunta una fotografía más clara del lugar o del vehículo.\n"
            "- Describe con más detalle lo que ocurrió.\n\n"
            "**Si hay personas heridas o riesgo inmediato, llama a la línea de emergencias 123.**"
        )
        advertencias.append("Información insuficiente: se omitió el Agente de Logística.")
        pasos.append("2. Información insuficiente: se omitió el Agente de Logística y se pidió más información.")
        estado = "PENDIENTE_DE_ACLARACION"

    # --- Paso 3: acción dentro del sistema ---------------------------------
    contexto_caso = {
        "analisis": analisis,
        "recomendacion_logistica": recomendacion,
        "contexto_herramientas": contexto_herramientas,
        "advertencias": advertencias,
        "estado": estado,
    }
    accion_desc = (
        f"Caso registrado en la base de datos con estado {estado}. "
        f"Tipo: {analisis.get('tipo_incidente', 'N/D')}"
    )
    herramientas.append("registrar_caso_en_sistema (acción)")
    pasos.append("3. Acción ejecutada: el caso fue persistido en SQLite.")

    caso_id = registrar_caso_en_sistema(
        descripcion=descripcion,
        latitud=latitud,
        longitud=longitud,
        contexto=contexto_caso,
        agentes=agentes,
        herramientas=herramientas,
        accion=accion_desc,
    )

    ubic = contexto_herramientas.get("ubicacion") or {
        "direccion": f"Lat: {latitud}, Lon: {longitud}"
    }

    return {
        "caso_id": caso_id,
        "estado": estado,
        "analisis_estructurado": analisis,
        "ubicacion_detectada": ubic,
        "servicios_cercanos": contexto_herramientas.get("servicios_cercanos", []),
        "ruta": contexto_herramientas.get("ruta"),
        "recomendacion_logistica": recomendacion,
        "advertencias": advertencias,
        "trazabilidad": {
            "orquestacion": pasos,
            "agentes_participantes": agentes,
            "herramientas_ejecutadas": herramientas,
            "accion_realizada": accion_desc,
        },
    }


# ---------------------------------------------------------------------------
# Recuperación de casos (Fase 7: persistencia y trazabilidad)
# ---------------------------------------------------------------------------
@app.get("/api/casos")
def listar():
    return listar_casos()


@app.get("/api/casos/{caso_id}")
def obtener_caso(caso_id: int):
    caso = obtener_caso_por_id(caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="El caso no existe en el sistema")
    return caso


# ---------------------------------------------------------------------------
# Chat contextual (Fase 5)
# ---------------------------------------------------------------------------
class PreguntaChat(BaseModel):
    caso_id: int
    pregunta: str


@app.post("/api/chat-contextual")
def chat_contextual(payload: PreguntaChat):
    caso = obtener_caso_por_id(payload.caso_id)
    if not caso:
        raise HTTPException(status_code=404, detail="El caso no existe en el sistema")
    try:
        respuesta = agente_chat_contextual(caso, payload.pregunta)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falla en el chat contextual (Gemini): {e}")
    return {"respuesta": respuesta}


app.mount(
    "/",
    StaticFiles(directory=os.path.join(BASE_DIR, "..", "frontend", "static"), html=True),
    name="static",
)