"""
Bot de Telegram - Flujo de consulta de rutas + registro en SQLite

Algoritmo:
1. El usuario envía su pregunta (origen y destino, o texto libre) o comparte
   su ubicación GPS.
2. Cada mensaje de texto o ubicación se guarda en la base de datos local
   `transporte.db` (tabla `reportes`), usando SQLite (viene incluido en Python,
   no requiere instalar nada externo).
3. El bot pregunta si quiere ordenar las sugerencias por TIEMPO o por COSTO.
4. El bot consulta la base de datos con esa preferencia y muestra todas
   las sugerencias encontradas.
5. Cada consulta de rutas también se registra (señal) para trazabilidad.

Requiere: pip install python-telegram-bot --upgrade
Ejecutar: python bot_consulta_rutas.py

Dependencias que TÚ debes conectar:
- `consultar_rutas_bd()`  -> reemplazar por tu query real (SQL, ORM, API interna, etc.)
- `registrar_senal_bd()`  -> reemplazar por tu logging/evento real hacia la BD
- TOKEN                   -> tu token de BotFather

⚠️ SEGURIDAD: no dejes el TOKEN escrito directamente en el código si vas a subirlo
a un repositorio o compartirlo. Si este token ya se compartió en algún chat/repo,
revócalo en BotFather (/revoke) y genera uno nuevo. Idealmente cárgalo así:
    import os
    TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
"""

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = "8820144153:AAFErZf1H_Bpnqt3LJoIJ9Lj_eDfxHm0YkQ"  # ⚠️ reemplaza/rota este token, ver nota de seguridad arriba

# Estados de la conversación
ESPERANDO_PREGUNTA, ESPERANDO_ORDEN = range(2)

DB_PATH = "transporte.db"


# ---------------------------------------------------------------------------
# Capa de base de datos (SQLite nativo de Python, no requiere instalar nada)
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Crea el archivo de base de datos transporte.db y la tabla 'reportes' si no existen."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_hash TEXT,
            tipo TEXT,
            texto TEXT,
            latitud REAL,
            longitud REAL,
            fecha_hora TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def guardar_dato(
    user_id: int,
    tipo: str,
    texto: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    """Guarda un registro en la base de datos.

    El user_id se guarda como hash (SHA-256) en vez de en texto plano,
    para no almacenar el ID real de Telegram directamente.
    """
    user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()
    fecha = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO reportes (user_hash, tipo, texto, latitud, longitud, fecha_hora)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_hash, tipo, texto, lat, lon, fecha),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Capa de datos de rutas (STUBS a reemplazar por la conexión real a tu BD)
# ---------------------------------------------------------------------------

@dataclass
class Sugerencia:
    nombre: str          # ej. "Colectivo 12 - Av. Grecia"
    tipo: str            # "colectivo" | "liebre" | "micro" | etc.
    tiempo_min: float    # minutos estimados
    costo_clp: int       # costo estimado en pesos


def consultar_rutas_bd(origen: str, destino: str, orden: str) -> list[Sugerencia]:
    """
    Reemplaza esto por tu consulta real a la base de datos
    (SQL, ORM tipo SQLAlchemy/Prisma, o llamada a tu API interna).

    `orden` es "tiempo" o "costo".
    """
    # --- MOCK de ejemplo, borrar cuando conectes la BD real ---
    resultados = [
        Sugerencia("Colectivo 12", "colectivo", tiempo_min=18, costo_clp=1200),
        Sugerencia("Liebre Puente Alto", "liebre", tiempo_min=25, costo_clp=900),
        Sugerencia("Micro 210", "micro", tiempo_min=22, costo_clp=800),
    ]
    clave = (lambda s: s.tiempo_min) if orden == "tiempo" else (lambda s: s.costo_clp)
    return sorted(resultados, key=clave)


def registrar_senal_bd(user_id: int, origen: str, destino: str, orden: str) -> None:
    """
    Reemplaza esto por el insert/evento real hacia tu base de datos
    (ej. tabla `consultas`, o publicar en una cola/pub-sub).
    """
    logger.info(
        "SEÑAL BD -> user_id=%s origen=%r destino=%r orden=%s",
        user_id, origen, destino, orden,
    )


# ---------------------------------------------------------------------------
# Handlers de la conversación
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "¡Hola! Cuéntame tu recorrido (o comparte tu ubicación 📍).\n"
        "Escribe origen y destino, por ejemplo:\n"
        "«Plaza de Armas a Mall Plaza Vespucio»"
    )
    return ESPERANDO_PREGUNTA


async def recibir_pregunta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()

    # Guardamos el mensaje de texto crudo en la base de datos (tabla 'reportes')
    guardar_dato(user_id=update.effective_user.id, tipo="texto", texto=texto)

    # Parseo simple "origen a destino" — ajusta a tu formato real
    # (podrías usar NLP, regex más robusto, o dos mensajes separados)
    if " a " in texto.lower():
        origen, destino = texto.lower().split(" a ", 1)
    else:
        origen, destino = texto, ""

    # Guardamos en el estado de la conversación para usarlo más adelante
    context.user_data["origen"] = origen.strip()
    context.user_data["destino"] = destino.strip()

    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱️ Por tiempo", callback_data="tiempo"),
            InlineKeyboardButton("💰 Por costo", callback_data="costo"),
        ]
    ])
    await update.message.reply_text(
        "¿Cómo prefieres que ordene las sugerencias?",
        reply_markup=teclado,
    )
    return ESPERANDO_ORDEN


async def recibir_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler nuevo: guarda la ubicación GPS que el usuario comparte."""
    loc = update.message.location
    guardar_dato(
        user_id=update.effective_user.id,
        tipo="gps",
        lat=loc.latitude,
        lon=loc.longitude,
    )
    await update.message.reply_text(
        "📍 ¡Gracias! Guardé tu ubicación. Si quieres consultar una ruta, "
        "escribe origen y destino (ej. «Plaza de Armas a Mall Plaza Vespucio»)."
    )
    # Nos quedamos en el mismo estado por si el usuario ahora escribe origen/destino
    return ESPERANDO_PREGUNTA


async def recibir_orden(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()  # ack del botón

    orden = query.data  # "tiempo" o "costo"
    origen = context.user_data.get("origen", "")
    destino = context.user_data.get("destino", "")
    user_id = update.effective_user.id

    # 1) Enviar la señal a la base de datos (trazabilidad de la consulta)
    registrar_senal_bd(user_id, origen, destino, orden)

    # 2) Hacer la consulta real y traer las sugerencias
    sugerencias = consultar_rutas_bd(origen, destino, orden)

    # 3) Mostrar todas las sugerencias
    if not sugerencias:
        await query.edit_message_text(
            "No encontré sugerencias para ese recorrido todavía. "
            "¿Quieres proponer una ruta? Usa /proponer"
        )
        return ConversationHandler.END

    criterio = "tiempo estimado" if orden == "tiempo" else "costo estimado"
    lineas = [f"Resultados ordenados por {criterio}:\n"]
    for i, s in enumerate(sugerencias, start=1):
        lineas.append(
            f"{i}. {s.nombre} ({s.tipo})\n"
            f"   ⏱️ {s.tiempo_min} min   💰 ${s.costo_clp} CLP"
        )
    lineas.append("\n¿Quieres hacer otra consulta? Usa /start")

    await query.edit_message_text("\n".join(lineas))
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Consulta cancelada. Escribe /start cuando quieras.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Arranque del bot
# ---------------------------------------------------------------------------

def main() -> None:
    # Crea transporte.db y la tabla 'reportes' si aún no existen
    init_db()

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ESPERANDO_PREGUNTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_pregunta),
                MessageHandler(filters.LOCATION, recibir_ubicacion),
            ],
            ESPERANDO_ORDEN: [
                CallbackQueryHandler(recibir_orden, pattern="^(tiempo|costo)$")
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(conv_handler)

    logger.info("Bot corriendo...")
    app.run_polling()


if __name__ == "__main__":
    main()
