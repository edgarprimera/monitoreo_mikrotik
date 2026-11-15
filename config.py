import os
import re
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", 9177))
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", 10))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def obtener_routers():
    """Lee dinámicamente cualquier ROUTER_<N>_* definido en el archivo .env."""
    routers = {}
    patron = re.compile(r"^ROUTER_(\d+)_(.+)$")

    for key, value in os.environ.items():
        coincidencia = patron.match(key)
        if coincidencia:
            idx, campo = coincidencia.groups()
            idx = int(idx)
            if idx not in routers:
                routers[idx] = {
                    "id": f"Router-{idx}",
                    "host": "",
                    "port": 8728,
                    "user": "admin",
                    "password": "",
                    "monitor_interfaces": [],
                    "critical_interfaces": []
                }
            
            campo = campo.lower()
            if campo == "id":
                routers[idx]["id"] = value
            elif campo == "host":
                routers[idx]["host"] = value
            elif campo == "port":
                routers[idx]["port"] = int(value) if value.isdigit() else 8728
            elif campo == "user":
                routers[idx]["user"] = value
            elif campo in ("pass", "password"):
                routers[idx]["password"] = value
            elif campo in ("monitor_ifaces", "monitor_interfaces", "ifaces"):
                routers[idx]["monitor_interfaces"] = [x.strip() for x in value.split(",") if x.strip()]
            elif campo in ("critical_ifaces", "critical_interfaces"):
                routers[idx]["critical_interfaces"] = [x.strip() for x in value.split(",") if x.strip()]

    # Procesar listas por defecto: si no se especificó monitor_interfaces, usar critical_interfaces si existe
    resultado = []
    for i in sorted(routers.keys()):
        r = routers[i]
        if r["host"]:
            if not r["monitor_interfaces"] and r["critical_interfaces"]:
                r["monitor_interfaces"] = list(r["critical_interfaces"])
            resultado.append(r)

    return resultado
