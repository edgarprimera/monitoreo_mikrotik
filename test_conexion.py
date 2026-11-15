import os
import re
from dotenv import load_dotenv
import routeros_api

# Cargar variables de entorno desde .env
load_dotenv()

def obtener_routers_desde_env():
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
            elif campo == "pass" or campo == "password":
                routers[idx]["password"] = value
            elif campo == "critical_ifaces":
                routers[idx]["critical_interfaces"] = [x.strip() for x in value.split(",") if x.strip()]

    # Retornar lista ordenada por índice
    return [routers[i] for i in sorted(routers.keys()) if routers[i]["host"]]


def probar_conexion(router):
    """Intenta conectar a un router y listar sus interfaces."""
    r_id = router["id"]
    host = router["host"]
    user = router["user"]
    port = router["port"]

    print(f"\nProbando conexión con: [{r_id}] en {host}:{port}...", flush=True)

    try:
        pool = routeros_api.RouterOsApiPool(
            host,
            username=user,
            password=router["password"],
            port=port,
            use_ssl=False,
            plaintext_login=True
        )
        api = pool.get_api()
        
        # Leer interfaces
        recurso_interfaces = api.get_resource('/interface')
        interfaces = recurso_interfaces.get()
        
        print(f" Conexión exitosa con [{r_id}]")
        print(f"  Total de interfaces detectadas: {len(interfaces)}")
        print("  Resumen de interfaces:")
        for iface in interfaces:
            nombre = iface.get('name')
            tipo = iface.get('type')
            running = iface.get('running') == 'true'
            disabled = iface.get('disabled') == 'true'
            estado = "DESHABILITADA" if disabled else ("UP (Running)" if running else "DOWN")
            print(f"    - {nombre} ({tipo}): {estado}")
            
        pool.disconnect()
        return True

    except Exception as e:
        print(f" Falló la conexión con [{r_id}]: {e}")
        return False


if __name__ == "__main__":
    print("=== TEST DE CONEXIÓN CON MIKROTIK DESDE .ENV ===")
    routers = obtener_routers_desde_env()
    
    if not routers:
        print(" No se encontraron routers configurados en el archivo .env")
        print("Asegúrate de llenar las variables ROUTER_1_HOST, ROUTER_1_USER, etc.")
    else:
        print(f"Se encontraron {len(routers)} router(s) en .env.")
        for r in routers:
            probar_conexion(r)
