from config import obtener_routers
import routeros_api

def probar_conexion(router):
    """Intenta conectar a un router y listar sus interfaces."""
    r_id = router["id"]
    host = router["host"]
    user = router["user"]
    port = router["port"]
    monitor_interfaces = router.get("monitor_interfaces", [])

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
        print(f"  Total de interfaces en el equipo: {len(interfaces)}")

        if monitor_interfaces:
            print(f"  Interfaces seleccionadas en lista blanca ({len(monitor_interfaces)}):")
            for iface in interfaces:
                nombre = iface.get('name')
                if nombre in monitor_interfaces:
                    tipo = iface.get('type')
                    running = iface.get('running') == 'true'
                    disabled = iface.get('disabled') == 'true'
                    estado = "DESHABILITADA" if disabled else ("UP (Running)" if running else "DOWN")
                    print(f"    - {nombre} ({tipo}): {estado}")
        else:
            print("  Resumen de interfaces (todas):")
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
    routers = obtener_routers()
    
    if not routers:
        print(" No se encontraron routers configurados en el archivo .env")
        print("Asegúrate de llenar las variables ROUTER_1_HOST, ROUTER_1_USER, etc.")
    else:
        print(f"Se encontraron {len(routers)} router(s) en .env.")
        for r in routers:
            probar_conexion(r)
