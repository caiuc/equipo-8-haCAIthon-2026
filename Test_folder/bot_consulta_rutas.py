"""
Bot de Telegram - Flujo de consulta de rutas + registro en SQLite

Algoritmo:
1. El usuario escribe algo como "quiero ir a Mall Plaza Vespucio",
   "Plaza de Armas a Mall Plaza Vespucio", o simplemente comparte su
   ubicación GPS.
2. El bot intenta extraer (origen, destino) del texto:
     - Si detecta destino pero no origen, pide el origen y ofrece un
       botón para enviar la ubicación actual (o escribirlo a mano).
     - Si el mensaje NO calza con ningún patrón reconocible (ej. "hola",
       un saludo, texto suelto), el bot NO intenta adivinar: pregunta
       directamente por el destino.
3. Cada mensaje de texto o ubicación se guarda en `transporte.db`
   (tabla `reportes`), usando SQLite (viene incluido en Python).
4. El bot pregunta si quiere ordenar las sugerencias por TIEMPO o por COSTO.
5. Consulta la base de datos con esa preferencia y muestra las sugerencias.
6. Cada consulta de rutas también se registra (señal) para trazabilidad.

Requiere: pip install python-telegram-bot --upgrade
Ejecutar:
    export TELEGRAM_BOT_TOKEN="tu_token_de_botfather"
    python bot_consulta_rutas.py

Dependencias que TÚ debes conectar:
- `consultar_rutas_bd()`  -> reemplazar por tu query real (SQL, ORM, API interna, etc.)
- `registrar_senal_bd()`  -> reemplazar por tu logging/evento real hacia la BD

⚠️ SEGURIDAD: el token se lee SIEMPRE desde la variable de entorno
TELEGRAM_BOT_TOKEN, nunca lo escribas directamente en este archivo.
Si un token ya se compartió alguna vez en un chat/repo, revócalo en
BotFather (/revoke) y genera uno nuevo.
"""

import hashlib
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import datetime
import hashlib
import psycopg2

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

DATABASE_URL = "postgresql://neondb_owner:npg_yW7bu8JrnRho@ep-curly-pine-acbc6s87.sa-east-1.aws.neon.tech/neondb?sslmode=require"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = "8820144153:AAFErZf1H_Bpnqt3LJoIJ9Lj_eDfxHm0YkQ"
# Estados de la conversación
ESPERANDO_PREGUNTA, ESPERANDO_ORIGEN, ESPERANDO_ORDEN, ESPERANDO_REPORTE = range(4)


# ---------------------------------------------------------------------------
# Capa de base de datos (SQLite nativo de Python, no requiere instalar nada)
# ---------------------------------------------------------------------------


def guardar_dato(
    user_id: int,
    tipo: str,
    texto: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> None:
    """Guarda un registro directamente en la base de datos PostgreSQL en la nube (Neon).

    El user_id se guarda como hash (SHA-256) en vez de en texto plano,
    para no almacenar el ID real de Telegram directamente.
    """
    user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()
    fecha = datetime.now(timezone.utc).isoformat()

    try:
        # Usamos psycopg2 y DATABASE_URL en lugar de sqlite3
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # IMPORTANTE: PostgreSQL usa %s en lugar de ? para las variables
        cursor.execute(
            """
            INSERT INTO reportes (user_hash, tipo, texto, latitud, longitud, fecha_hora)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_hash, tipo, texto, lat, lon, fecha),
        )
        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ Reporte tipo '{tipo}' guardado en la nube con éxito.")
        
    except Exception as e:
        print(f"❌ Error guardando en la base de datos de Neon: {e}")
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
# Parseo de lenguaje libre
# ---------------------------------------------------------------------------

# Verbos/frases típicas para indicar SOLO destino ("quiero ir a X", "voy a X"...)
_PATRON_SOLO_DESTINO = re.compile(
    r"(?:quiero ir|necesito ir|tengo que ir|voy|ir|llegar)\s+a\s+(?P<destino>.+)$",
    re.IGNORECASE,
)
_PATRON_HASTA_PARA = re.compile(
    r"^(?:hasta|para)\s+(?P<destino>.+)$", re.IGNORECASE
)
_PATRON_DE_A = re.compile(
    r"^de\s+(?P<origen>.+?)\s+a\s+(?P<destino>.+)$", re.IGNORECASE
)
_PATRON_ORIGEN_A_DESTINO = re.compile(
    r"^(?P<origen>.+?)\s+a\s+(?P<destino>.+)$", re.IGNORECASE
)


def parsear_mensaje(texto: str) -> tuple[str | None, str | None]:
    """Intenta extraer (origen, destino) de un mensaje en texto libre.

    Devuelve (None, None) si el mensaje no parece una consulta de ruta
    (ej. un saludo como "hola"). Devuelve (None, destino) si solo se
    pudo identificar el destino.
    """
    t = texto.strip()
    if not t:
        return None, None

    m = _PATRON_DE_A.match(t)
    if m:
        return m.group("origen").strip(), m.group("destino").strip()

    m = _PATRON_SOLO_DESTINO.search(t)
    if m:
        return None, m.group("destino").strip()

    m = _PATRON_HASTA_PARA.match(t)
    if m:
        return None, m.group("destino").strip()

    m = _PATRON_ORIGEN_A_DESTINO.match(t)
    if m:
        return m.group("origen").strip(), m.group("destino").strip()

    return None, None


def _formatear_ubicacion(lat: float, lon: float) -> str:
    return f"Mi ubicación actual ({lat:.5f}, {lon:.5f})"


# ---------------------------------------------------------------------------
# Helpers de conversación reutilizados en varios puntos del flujo
# ---------------------------------------------------------------------------

async def pedir_origen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    teclado = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Enviar mi ubicación actual", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        "¿Desde dónde sales? Escríbelo, o toca el botón para enviarme tu "
        "ubicación actual.",
        reply_markup=teclado,
    )


async def preguntar_orden(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    destino = context.user_data.get("destino", "tu destino")
    teclado = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱️ Por tiempo", callback_data="tiempo"),
            InlineKeyboardButton("💰 Por costo", callback_data="costo"),
        ]
    ])
    await update.message.reply_text(
        f"Buscando rutas hacia «{destino}». ¿Cómo prefieres que ordene "
        "las sugerencias?",
        reply_markup=teclado,
    )
    return ESPERANDO_ORDEN


# ---------------------------------------------------------------------------
# Handlers de la conversación
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "¡Hola! Cuéntame tu recorrido, por ejemplo:\n"
        "«Quiero ir a Mall Plaza Vespucio»\n"
        "«Plaza de Armas a Mall Plaza Vespucio»\n"
        "También puedes compartir tu ubicación 📍 en cualquier momento.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ESPERANDO_PREGUNTA


async def recibir_pregunta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    texto_lower = texto.lower()

    # 1. DETECTAR INTENCIÓN DE REPORTE
    palabras_clave = ["reporte", "reportar", "problema", "incidente", "taco", "choque"]
    if any(palabra in texto_lower for palabra in palabras_clave):
        await update.message.reply_text(
            "🚨 *Modo Reporte Activado*\n"
            "Entendido. Cuéntame con detalle qué está pasando o envíame tu ubicación "
            "para registrar la incidencia en la base de datos comunitaria:",
            parse_mode="Markdown"
        )
        return ESPERANDO_REPORTE

    # 2. SI NO ES REPORTE, SIGUE EL FLUJO NORMAL DE RUTAS
    guardar_dato(user_id=update.effective_user.id, tipo="consulta_ruta", texto=texto)

    # Si ya teníamos un origen guardado (ej. vino de una ubicación GPS
    # enviada antes de decir el destino), este mensaje es directamente
    # el destino, sin necesidad de parsearlo con los patrones de ruta.
    if context.user_data.get("origen") and not context.user_data.get("destino"):
        context.user_data["destino"] = texto
        return await preguntar_orden(update, context)

    origen, destino = parsear_mensaje(texto)

    if not destino:
        # No calza con ningún formato reconocido (ej. "hola", texto suelto).
        # No adivinamos: preguntamos directo por destino y origen.
        await update.message.reply_text(
            "No logré entender tu recorrido 🙈. Cuéntame a dónde quieres ir, "
            "por ejemplo:\n«Quiero ir a Mall Plaza Vespucio» o "
            "«Plaza de Armas a Mall Plaza Vespucio»."
        )
        return ESPERANDO_PREGUNTA

    context.user_data["destino"] = destino

    if origen:
        context.user_data["origen"] = origen
        return await preguntar_orden(update, context)

    await pedir_origen(update, context)
    return ESPERANDO_ORIGEN

async def procesar_reporte_final(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda el detalle del reporte o la ubicación de la incidencia"""
    user_id = update.effective_user.id

    if update.message.location:
        loc = update.message.location
        guardar_dato(
            user_id=user_id, 
            tipo="reporte_gps",
            lat=loc.latitude, 
            lon=loc.longitude
        )
    else:
        texto = update.message.text.strip()
        guardar_dato(user_id=user_id, tipo="reporte_texto", texto=texto)

    await update.message.reply_text(
        "✅ ¡Incidencia registrada con éxito! La información ya está en la nube "
        "ayudando a la comunidad.\n\n"
        "Si necesitas buscar una ruta, vuelve a usar /start"
    )
    context.user_data.clear()
    return ConversationHandler.END

async def recibir_ubicacion_inicial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ubicación enviada ANTES de que el usuario haya dicho el destino."""
    loc = update.message.location
    guardar_dato(
        user_id=update.effective_user.id, tipo="gps",
        lat=loc.latitude, lon=loc.longitude,
    )
    context.user_data["origen"] = _formatear_ubicacion(loc.latitude, loc.longitude)

    if context.user_data.get("destino"):
        return await preguntar_orden(update, context)

    await update.message.reply_text(
        "📍 ¡Gracias! Guardé tu ubicación como punto de partida.\n"
        "¿A dónde quieres ir?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ESPERANDO_PREGUNTA


async def recibir_origen_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    guardar_dato(user_id=update.effective_user.id, tipo="texto", texto=texto)
    context.user_data["origen"] = texto
    return await preguntar_orden(update, context)


async def recibir_origen_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    loc = update.message.location
    guardar_dato(
        user_id=update.effective_user.id, tipo="gps",
        lat=loc.latitude, lon=loc.longitude,
    )
    context.user_data["origen"] = _formatear_ubicacion(loc.latitude, loc.longitude)
    return await preguntar_orden(update, context)


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
    else:
        criterio = "tiempo estimado" if orden == "tiempo" else "costo estimado"
        lineas = [f"Resultados ordenados por {criterio}:\n"]
        for i, s in enumerate(sugerencias, start=1):
            lineas.append(
                f"{i}. {s.nombre} ({s.tipo})\n"
                f"   ⏱️ {s.tiempo_min} min   💰 ${s.costo_clp} CLP"
            )
        lineas.append("\n¿Quieres hacer otra consulta? Usa /start")
        await query.edit_message_text("\n".join(lineas))

    context.user_data.clear()
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Consulta cancelada. Escribe /start cuando quieras.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Arranque del bot
# ---------------------------------------------------------------------------

def main() -> None:

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                ESPERANDO_PREGUNTA: [
                    MessageHandler(filters.LOCATION, recibir_ubicacion_inicial),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_pregunta),
                ],
                ESPERANDO_ORIGEN: [
                    MessageHandler(filters.LOCATION, recibir_origen_ubicacion),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_origen_texto),
                ],
                ESPERANDO_ORDEN: [
                    CallbackQueryHandler(recibir_orden, pattern="^(tiempo|costo)$")
                ],
                # NUEVO: Aquí el bot espera el detalle del reporte
                ESPERANDO_REPORTE: [
                    MessageHandler(filters.LOCATION, procesar_reporte_final),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_reporte_final),
                ]
            },
            fallbacks=[CommandHandler("cancelar", cancelar)],
        )

    app.add_handler(conv_handler)

    logger.info("Bot corriendo...")
    app.run_polling()


if __name__ == "__main__":
    main()
