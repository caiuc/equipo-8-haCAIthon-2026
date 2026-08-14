"""Telegram bot API: 8820144153:AAFErZf1H_Bpnqt3LJoIJ9Lj_eDfxHm0YkQ"""
import sys
import os

# 1. Obtenemos la ruta exacta de la carpeta Libraries/Telegram
# Usamos rutas relativas para que no se rompa si mueven el proyecto a otro computador
ruta_libreria = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Libraries', 'Telegram')
print(ruta_libreria)
# 2. Añadimos esa ruta al principio de la lista de búsqueda de Python
sys.path.insert(0, ruta_libreria)

# 3. AHORA SÍ hacemos la importación normal de Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypesApplication