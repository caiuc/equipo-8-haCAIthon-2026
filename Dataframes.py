import pandas as pd

archivos = [
    "calendar.txt",
    "calendar_dates.txt"
]

dataframes = {}

for archivo in archivos:
    nombre = archivo.replace(".txt", "")
    dataframes[nombre] = pd.read_csv(archivo)

print(dataframes["calendar"])