# 🚗 Geo IA — SafeRoute & Rescue Urbano

Aplicación web inteligente de movilidad y asistencia vial. El usuario reporta un incidente con una
descripción, una fotografía y su ubicación. Un sistema de agentes de IA analiza el caso, consulta
herramientas (datos propios y geolocalización externa), genera una recomendación, registra el caso
y permite hacer preguntas posteriores en un chat contextual.

## Estructura del proyecto

```
Geo IA/
├── backend/            # API FastAPI, agentes, herramientas y base de datos
│   ├── main.py         # Endpoints y orquestador
│   ├── agents.py       # Agentes de IA (Gemini)
│   ├── tools.py        # Herramientas y acción del sistema
│   └── database.py     # Persistencia en SQLite
├── frontend/static/
│   └── index.html      # Interfaz web (HTML + CSS + JavaScript)
├── requirements.txt
├── .env.example
└── README.md
```

## Arquitectura

| Capa | Tecnología |
|------|------------|
| Interfaz web | HTML + CSS + JavaScript (servida por FastAPI desde `frontend/static/`) |
| Backend | Python + FastAPI (servidor uvicorn) |
| Modelo de IA | Google Gemini (multimodal, configurable con `GEMINI_MODEL`) |
| Datos propios | SQLite: tabla `servicios_propios` (talleres y grúas) y tabla `casos` |
| Servicio externo | Geoapify (geocodificación inversa y rutas), con respaldo en OpenStreetMap/Nominatim |

Flujo general:

```
Usuario → Interfaz web → FastAPI (orquestador)
   → Agente Analista Multimodal (texto + imagen → JSON)
   → [¿información suficiente?]
        sí → Agente de Logística y Rutas (herramientas: SQLite, Geoapify)
        no → se pide más información
   → Acción: registrar el caso en SQLite
   → Respuesta + Chat contextual
```

### Agentes y orquestación

El orquestador (`backend/main.py`, endpoint `/api/procesar-incidente`) decide el orden y las condiciones:

1. **Agente Analista Multimodal**: recibe texto + imagen y devuelve un JSON estructurado
   (tipo, gravedad, heridos visibles, servicio recomendado, coherencia, información suficiente).
2. **Condición**: si la información es suficiente, participa el **Agente de Logística y Rutas**.
   Si no lo es, se omite y se solicita más información al usuario.
   Si la imagen no coincide con la descripción, se muestra una advertencia.
3. **Agente de Logística y Rutas**: ejecuta las herramientas y redacta la recomendación
   usando solo los datos consultados.
4. **Acción del sistema**: el caso se registra en SQLite.
5. **Agente de Chat Contextual**: responde preguntas posteriores solo con la información guardada del caso.

### Herramientas (`backend/tools.py`)

- `consultar_datos_propios_servicios`: consulta SQLite y ordena los servicios por distancia.
- `consultar_geolocalizacion_externa`: geocodificación inversa (Geoapify / Nominatim).
- `calcular_ruta_externa`: distancia y tiempo hasta el servicio más cercano (Geoapify Routing).
- `registrar_caso_en_sistema`: **acción** que crea el registro del caso en la base de datos.

### Persistencia y trazabilidad

Cada caso guarda descripción, coordenadas, análisis estructurado, resultados de herramientas,
recomendación, agentes participantes, herramientas usadas y acción realizada.
Se pueden consultar en `GET /api/casos` y `GET /api/casos/{id}`.

## Tecnologías y servicios

- Python, FastAPI, Uvicorn, SQLite
- Google Gemini (SDK `google-genai`): modelo multimodal usado para analizar imágenes y generar texto
- Geoapify (geocodificación inversa y rutas) y OpenStreetMap/Nominatim como respaldo
- JavaScript, HTML, CSS y `marked.js` (para mostrar Markdown)

## Instalación y ejecución

Requisitos: Python 3.10 o superior.

```bash
# 1. Crear y activar entorno virtual (en la carpeta raíz del proyecto)
python -m venv .venv
# Windows: .venv\Scripts\activate    |   Linux/Mac: source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
# Windows: copy .env.example .env    |   Linux/Mac: cp .env.example .env
# Abre .env y escribe tus claves reales

# 4. Ejecutar el servidor desde la carpeta backend
cd backend
uvicorn main:app --reload
```

Abre http://127.0.0.1:8000 en el navegador. La documentación automática de la API está en
http://127.0.0.1:8000/docs.

## Variables de entorno

Ver `.env.example`:

| Variable | Descripción |
|----------|-------------|
| `GEMINI_API_KEY` | Clave de la API de Google Gemini |
| `GEMINI_MODEL` | Modelo de Gemini a usar |
| `GEOAPIFY_API_KEY` | Clave de la API de Geoapify |