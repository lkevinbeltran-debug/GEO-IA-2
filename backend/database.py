import os
import sqlite3
import json
from datetime import datetime

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saferoute.db")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servicios_propios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            tipo TEXT,
            latitud REAL,
            longitud REAL,
            telefono TEXT,
            direccion TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS casos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_registro TEXT,
            descripcion_usuario TEXT,
            latitud REAL,
            longitud REAL,
            analisis_estructurado TEXT,
            agentes_participantes TEXT,
            herramientas_usadas TEXT,
            accion_realizada TEXT
        )
    ''')

    cursor.execute("SELECT COUNT(*) FROM servicios_propios")
    if cursor.fetchone()[0] == 0:
        servicios_iniciales = [
            ("Taller Express Central", "Taller Mecánico", 4.6097, -74.0817, "+573001234567", "Calle 13 # 20-10"),
            ("Asistencia Grúas & Moto 24/7", "Servicio de Grúa", 4.6200, -74.0700, "+573109876543", "Av. Caracas # 45-12"),
            ("Punto Auxilio Mecánico Norte", "Taller Mecánico", 4.6500, -74.0500, "+573204567890", "Carrera 15 # 85-30"),
        ]
        cursor.executemany(
            "INSERT INTO servicios_propios (nombre, tipo, latitud, longitud, telefono, direccion) VALUES (?, ?, ?, ?, ?, ?)",
            servicios_iniciales,
        )

    conn.commit()
    conn.close()


def guardar_caso(descripcion, lat, lon, analisis, agentes, herramientas, accion):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    fecha = datetime.now().isoformat()

    cursor.execute('''
        INSERT INTO casos (fecha_registro, descripcion_usuario, latitud, longitud,
                           analisis_estructurado, agentes_participantes, herramientas_usadas, accion_realizada)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        fecha, descripcion, lat, lon,
        json.dumps(analisis, ensure_ascii=False),
        json.dumps(agentes, ensure_ascii=False),
        json.dumps(herramientas, ensure_ascii=False),
        accion,
    ))

    caso_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return caso_id


def obtener_servicios_propios():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, tipo, latitud, longitud, telefono, direccion FROM servicios_propios")
    rows = cursor.fetchall()
    conn.close()
    return [
        {"nombre": r[0], "tipo": r[1], "latitud": r[2], "longitud": r[3], "telefono": r[4], "direccion": r[5]}
        for r in rows
    ]


def obtener_caso_por_id(caso_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM casos WHERE id = ?", (caso_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "fecha": row[1],
            "descripcion": row[2],
            "latitud": row[3],
            "longitud": row[4],
            "analisis": json.loads(row[5]),
            "agentes": json.loads(row[6]),
            "herramientas": json.loads(row[7]),
            "accion": row[8],
        }
    return None


def listar_casos():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha_registro, descripcion_usuario, accion_realizada FROM casos ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "fecha": r[1], "descripcion": r[2], "accion": r[3]} for r in rows]