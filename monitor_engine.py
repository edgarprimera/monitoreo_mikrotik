import time
import json
import logging
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

import routeros_api
from config import (
    EXPORTER_PORT,
    CHECK_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_REPORT_INTERVAL_MINUTES,
    TELEGRAM_DAILY_REPORT_TIME,
    obtener_routers,
    get_current_time_str,
)

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MikroTikMonitor")

# ===================================================
# ALMACENAMIENTO DE MÉTRICAS Y ESTADO (Thread-Safe)
# ===================================================
data_lock = threading.Lock()
metrics_store = {
    "routers": {},          # {r_id: {"up": 1/0, "host": "...", "last_check": "...", "cpu_load": int, "mem_percent": float}}
    "health": {},           # {(r_id, sensor_name): value}
    "interfaces": {},       # {(r_id, iface_name): {...}}
}
state_tracker = {
    "routers": {},          # {r_id: {"up": bool, "last_alert": timestamp, "last_cpu_alert": ts, "last_temp_alert": ts}}
    "interfaces": {},       # {(r_id, iface_name): {"running": bool, "last_alert": timestamp}}
}

# ===================================================
# MÓDULO DE ALERTAS TELEGRAM
# ===================================================
def send_telegram_alert(message: str):
    """Envía un mensaje formateado a Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"[TELEGRAM SIMULADO]: {message.replace('*', '')}")
        return

    def _send():
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = json.dumps({
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(req, timeout=8):
                pass
        except Exception as err:
            logger.error(f"Error enviando alerta por Telegram: {err}")

    # Ejecutar en hilo separado para no retrasar el ciclo de monitoreo
    threading.Thread(target=_send, daemon=True).start()


# ===================================================
# MÓDULO DE AUTOMATIZACIÓN (HOOKS)
# ===================================================
def on_critical_interface_down(router: dict, iface_name: str):
    """
    Se ejecuta automáticamente cuando una interfaz crítica pasa a estado DOWN.
    1. Registra un log de advertencia en RouterOS.
    2. Envía automáticamente una gráfica de diagnóstico del router a Telegram.
    """
    r_id = router["id"]
    logger.warning(f"⚠️ [AUTOMATIZACIÓN] Ejecutando acción por caída de interfaz crítica {iface_name} en {r_id}")
    
    # 1. Registrar un log de advertencia directamente en el router MikroTik
    def _remediate():
        try:
            pool = routeros_api.RouterOsApiPool(
                router["host"],
                username=router["user"],
                password=router["password"],
                port=router["port"],
                use_ssl=False,
                plaintext_login=True,
            )
            api = pool.get_api()
            # Inyectar log en RouterOS
            log_res = api.get_resource("/log")
            log_res.call("print", {"message": f"ALERTA MONITOR: Interfaz {iface_name} en estado DOWN"})
            pool.disconnect()
            logger.info(f" Log de evento registrado exitosamente en {r_id}")
        except Exception as e:
            logger.error(f"No se pudo ejecutar remediación en {r_id}: {e}")

    # 2. Generar y enviar gráfica de diagnóstico por Telegram
    def _send_chart():
        try:
            import telegram_reporter
            image_path = telegram_reporter.generate_router_chart(router, window_minutes=30)
            stats = telegram_reporter.get_current_router_stats(r_id)
            caption = (
                f"🚨 *DIAGNÓSTICO DE CAÍDA CRÍTICA*\n"
                f"*Router:* `{r_id}` ({router['host']})\n"
                f"*Interfaz Afectada:* `{iface_name}` (DOWN)\n"
                f"⚡ *CPU:* `{stats['cpu_load']}%` | 🌡️ *Temp:* `{stats['cpu_temp']}`\n"
                f"🕒 *Hora:* `{get_current_time_str()}`"
            )
            telegram_reporter.send_telegram_photo(image_path, caption)
        except Exception as e:
            logger.error(f"No se pudo enviar gráfica de diagnóstico para {r_id}: {e}")

    threading.Thread(target=_remediate, daemon=True).start()
    threading.Thread(target=_send_chart, daemon=True).start()


# ===================================================
# COLECTOR DE DATOS MIKROTIK
# ===================================================
def poll_single_router(router: dict):
    """Consulta un router MikroTik, actualiza métricas y dispara alertas."""
    r_id = router["id"]
    host = router["host"]
    port = router["port"]
    user = router["user"]
    password = router["password"]
    critical_interfaces = router.get("critical_interfaces", [])
    monitor_interfaces = router.get("monitor_interfaces", [])
    now = time.time()
    now_str = get_current_time_str()

    try:
        pool = routeros_api.RouterOsApiPool(
            host,
            username=user,
            password=password,
            port=port,
            use_ssl=False,
            plaintext_login=True,
        )
        api = pool.get_api()
        raw_interfaces = api.get_resource("/interface").get()

        # 1. Recursos de CPU y Memoria
        cpu_load = 0
        mem_percent = 0.0
        try:
            raw_resources = api.get_resource("/system/resource").get()
            if raw_resources:
                r0 = raw_resources[0]
                cpu_load = int(r0.get("cpu-load", 0))
                total_mem = int(r0.get("total-memory", 1))
                free_mem = int(r0.get("free-memory", 0))
                if total_mem > 0:
                    mem_percent = ((total_mem - free_mem) / total_mem) * 100.0
        except Exception as e_res:
            logger.debug(f"Error leyendo /system/resource en {r_id}: {e_res}")

        # 2. Salud de Hardware (Temperaturas y Sensores)
        health_data = {}
        try:
            raw_health = api.get_resource("/system/health").get()
            if raw_health and isinstance(raw_health, list):
                for item in raw_health:
                    s_name = item.get("name")
                    s_val = item.get("value")
                    if s_name and s_val is not None:
                        try:
                            health_data[s_name] = float(s_val)
                        except ValueError:
                            pass
            elif raw_health and isinstance(raw_health, dict):
                for s_name, s_val in raw_health.items():
                    try:
                        health_data[s_name] = float(s_val)
                    except (ValueError, TypeError):
                        pass
        except Exception as e_hea:
            logger.debug(f"Error leyendo /system/health en {r_id}: {e_hea}")

        pool.disconnect()

        # Actualizar estado de router UP y recursos
        with data_lock:
            metrics_store["routers"][r_id] = {
                "up": 1,
                "host": host,
                "last_check": now_str,
                "cpu_load": cpu_load,
                "mem_percent": mem_percent,
                "error": None,
            }
            for sensor_name, sensor_val in health_data.items():
                metrics_store["health"][(r_id, sensor_name)] = sensor_val

        # Comprobar recuperación del router
        prev_router_state = state_tracker["routers"].get(r_id, {}).get("up", True)
        if not prev_router_state:
            state_tracker["routers"].setdefault(r_id, {})["up"] = True
            state_tracker["routers"][r_id]["last_alert"] = now
            msg = f"🟢 *ROUTER RESTAURADO*\n*Equipo:* `{r_id}`\n*IP:* `{host}:{port}`\n*Hora:* `{now_str}`"
            send_telegram_alert(msg)
        else:
            state_tracker["routers"].setdefault(r_id, {})["up"] = True

        # Alerta de temperatura crítica (> 75°C)
        cpu_temp = health_data.get("cpu-temperature")
        if cpu_temp and cpu_temp >= 75:
            last_temp_alert = state_tracker["routers"].get(r_id, {}).get("last_temp_alert", 0)
            if (now - last_temp_alert) > 300: # Cooldown de 5 minutos
                state_tracker["routers"][r_id]["last_temp_alert"] = now
                send_telegram_alert(f"🔥 *TEMPERATURA ALTA*\n*Router:* `{r_id}` ({host})\n*CPU Temp:* `{cpu_temp}°C`\n*Hora:* `{now_str}`")

        # Alerta de alta carga de CPU (> 90%)
        if cpu_load >= 90:
            last_cpu_alert = state_tracker["routers"].get(r_id, {}).get("last_cpu_alert", 0)
            if (now - last_cpu_alert) > 300:
                state_tracker["routers"][r_id]["last_cpu_alert"] = now
                send_telegram_alert(f"⚠️ *ALTA CARGA DE CPU*\n*Router:* `{r_id}` ({host})\n*Carga CPU:* `{cpu_load}%`\n*Hora:* `{now_str}`")

        # Procesar interfaces
        for iface in raw_interfaces:
            name = iface.get("name")
            if_type = iface.get("type", "unknown")
            is_running = 1 if iface.get("running") == "true" else 0
            disabled = iface.get("disabled") == "true"

            # LISTA BLANCA: Si se definieron interfaces específicas para este router, omitir las demás
            if monitor_interfaces and name not in monitor_interfaces:
                continue

            # Si la interfaz está deshabilitada administrativamente, no alertar ni procesar
            if disabled:
                continue

            rx_bytes = int(iface.get("rx-byte", 0))
            tx_bytes = int(iface.get("tx-byte", 0))
            rx_errors = int(iface.get("rx-error", 0))
            tx_errors = int(iface.get("tx-error", 0))

            key = (r_id, name)

            # Cálculo de tasas de transferencia (bps)
            rx_rate_bps = 0.0
            tx_rate_bps = 0.0

            with data_lock:
                prev_metric = metrics_store["interfaces"].get(key)
                if prev_metric:
                    dt = now - prev_metric["timestamp"]
                    if dt > 0:
                        delta_rx = rx_bytes - prev_metric["rx_bytes"]
                        delta_tx = tx_bytes - prev_metric["tx_bytes"]
                        # Prevenir deltas negativas (ej. reinicio de contadores)
                        if delta_rx >= 0:
                            rx_rate_bps = (delta_rx * 8) / dt
                        if delta_tx >= 0:
                            tx_rate_bps = (delta_tx * 8) / dt

                metrics_store["interfaces"][key] = {
                    "router_id": r_id,
                    "host": host,
                    "interface": name,
                    "type": if_type,
                    "running": is_running,
                    "rx_bytes": rx_bytes,
                    "tx_bytes": tx_bytes,
                    "rx_errors": rx_errors,
                    "tx_errors": tx_errors,
                    "rx_rate_bps": rx_rate_bps,
                    "tx_rate_bps": tx_rate_bps,
                    "timestamp": now,
                    "last_check": now_str,
                }

            # DETECCIÓN DE EVENTOS DE INTERFAZ (Up / Down)
            prev_iface_info = state_tracker["interfaces"].get(key)
            if prev_iface_info is not None:
                prev_running = prev_iface_info["running"]
                last_alert_time = prev_iface_info.get("last_alert", 0)

                # Anti-flapping: evitar spam si la interfaz oscila en menos de 30 segundos
                cooldown_ok = (now - last_alert_time) > 30

                if prev_running == 1 and is_running == 0 and cooldown_ok:
                    # 🚨 INTERFAZ CAYÓ
                    state_tracker["interfaces"][key] = {"running": 0, "last_alert": now}
                    msg = (
                        f"🚨 *INTERFAZ CAÍDA*\n"
                        f"*Router:* `{r_id}` ({host})\n"
                        f"*Interfaz:* `{name}` (`{if_type}`)\n"
                        f"*Estado:* Link DOWN\n"
                        f"*Hora:* `{now_str}`"
                    )
                    send_telegram_alert(msg)

                    # Si es una interfaz crítica, llamar al hook de automatización
                    if name in critical_interfaces:
                        on_critical_interface_down(router, name)

                elif prev_running == 0 and is_running == 1 and cooldown_ok:
                    # ✅ INTERFAZ RESTAURADA
                    state_tracker["interfaces"][key] = {"running": 1, "last_alert": now}
                    msg = (
                        f"✅ *INTERFAZ RESTAURADA*\n"
                        f"*Router:* `{r_id}` ({host})\n"
                        f"*Interfaz:* `{name}` (`{if_type}`)\n"
                        f"*Estado:* Link UP (Running)\n"
                        f"*Hora:* `{now_str}`"
                    )
                    send_telegram_alert(msg)
            else:
                state_tracker["interfaces"][key] = {"running": is_running, "last_alert": now}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Falla al conectar con router [{r_id}] ({host}:{port}): {error_msg}")
        with data_lock:
            metrics_store["routers"][r_id] = {
                "up": 0,
                "host": host,
                "last_check": now_str,
                "error": error_msg,
            }

        prev_router_state = state_tracker["routers"].get(r_id, {}).get("up", True)
        if prev_router_state:
            state_tracker["routers"][r_id] = {"up": False, "last_alert": now}
            msg = (
                f"💥 *ROUTER INALCANZABLE*\n"
                f"*Router:* `{r_id}`\n"
                f"*IP:* `{host}:{port}`\n"
                f"*Error:* `{error_msg}`\n"
                f"*Hora:* `{now_str}`"
            )
            send_telegram_alert(msg)


def poller_worker():
    """Bucle infinito que consulta todos los routers en paralelo cada intervalo."""
    logger.info(f"Iniciando ciclo de monitoreo cada {CHECK_INTERVAL_SECONDS} segundos...")
    while True:
        routers = obtener_routers()
        if not routers:
            logger.warning("No hay routers configurados en .env")
            time.sleep(CHECK_INTERVAL_SECONDS)
            continue

        start_t = time.time()
        # Consultar routers en paralelo
        with ThreadPoolExecutor(max_workers=min(len(routers), 12)) as executor:
            executor.map(poll_single_router, routers)

        elapsed = time.time() - start_t
        sleep_time = max(1.0, CHECK_INTERVAL_SECONDS - elapsed)
        time.sleep(sleep_time)


# ===================================================
# SERVIDOR HTTP EXPORTER (Prometheus + Dashboard JSON)
# ===================================================
class PrometheusMetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            # Formato estándar de texto para Prometheus
            lines = [
                "# HELP mikrotik_router_up Indica si el router responde a la API (1=si, 0=no)",
                "# TYPE mikrotik_router_up gauge",
            ]

            with data_lock:
                for r_id, r_info in metrics_store["routers"].items():
                    lines.append(f'mikrotik_router_up{{router_id="{r_id}",host="{r_info["host"]}"}} {r_info["up"]}')

                lines.extend([
                    "# HELP mikrotik_cpu_load_percent Carga de CPU en porcentaje (0-100)",
                    "# TYPE mikrotik_cpu_load_percent gauge",
                ])
                for r_id, r_info in metrics_store["routers"].items():
                    if "cpu_load" in r_info:
                        lines.append(f'mikrotik_cpu_load_percent{{router_id="{r_id}",host="{r_info["host"]}"}} {r_info["cpu_load"]}')

                lines.extend([
                    "# HELP mikrotik_memory_used_percent Porcentaje de memoria RAM utilizada",
                    "# TYPE mikrotik_memory_used_percent gauge",
                ])
                for r_id, r_info in metrics_store["routers"].items():
                    if "mem_percent" in r_info:
                        lines.append(f'mikrotik_memory_used_percent{{router_id="{r_id}",host="{r_info["host"]}"}} {r_info["mem_percent"]:.2f}')

                lines.extend([
                    "# HELP mikrotik_temperature_celsius Temperatura del hardware en grados Celsius",
                    "# TYPE mikrotik_temperature_celsius gauge",
                ])
                for (r_id, sensor_name), s_val in metrics_store["health"].items():
                    if "temp" in sensor_name.lower():
                        lines.append(f'mikrotik_temperature_celsius{{router_id="{r_id}",sensor="{sensor_name}"}} {s_val:.1f}')

                lines.extend([
                    "# HELP mikrotik_fan_speed_rpm Velocidad de los ventiladores en RPM",
                    "# TYPE mikrotik_fan_speed_rpm gauge",
                ])
                for (r_id, sensor_name), s_val in metrics_store["health"].items():
                    if "fan" in sensor_name.lower() and "speed" in sensor_name.lower():
                        lines.append(f'mikrotik_fan_speed_rpm{{router_id="{r_id}",fan="{sensor_name}"}} {s_val:.1f}')

                lines.extend([
                    "# HELP mikrotik_interface_running Estado de enlace (1=up, 0=down)",
                    "# TYPE mikrotik_interface_running gauge",
                ])
                for (r_id, name), iface in metrics_store["interfaces"].items():
                    lines.append(
                        f'mikrotik_interface_running{{router_id="{r_id}",interface="{name}",type="{iface["type"]}"}} {iface["running"]}'
                    )

                lines.extend([
                    "# HELP mikrotik_interface_rx_bytes_total Total de bytes recibidos",
                    "# TYPE mikrotik_interface_rx_bytes_total counter",
                ])
                for (r_id, name), iface in metrics_store["interfaces"].items():
                    lines.append(
                        f'mikrotik_interface_rx_bytes_total{{router_id="{r_id}",interface="{name}",type="{iface["type"]}"}} {iface["rx_bytes"]}'
                    )

                lines.extend([
                    "# HELP mikrotik_interface_tx_bytes_total Total de bytes transmitidos",
                    "# TYPE mikrotik_interface_tx_bytes_total counter",
                ])
                for (r_id, name), iface in metrics_store["interfaces"].items():
                    lines.append(
                        f'mikrotik_interface_tx_bytes_total{{router_id="{r_id}",interface="{name}",type="{iface["type"]}"}} {iface["tx_bytes"]}'
                    )

                lines.extend([
                    "# HELP mikrotik_interface_rx_errors_total Total de errores en recepcion",
                    "# TYPE mikrotik_interface_rx_errors_total counter",
                ])
                for (r_id, name), iface in metrics_store["interfaces"].items():
                    lines.append(
                        f'mikrotik_interface_rx_errors_total{{router_id="{r_id}",interface="{name}",type="{iface["type"]}"}} {iface["rx_errors"]}'
                    )

                lines.extend([
                    "# HELP mikrotik_interface_tx_errors_total Total de errores en transmision",
                    "# TYPE mikrotik_interface_tx_errors_total counter",
                ])
                for (r_id, name), iface in metrics_store["interfaces"].items():
                    lines.append(
                        f'mikrotik_interface_tx_errors_total{{router_id="{r_id}",interface="{name}",type="{iface["type"]}"}} {iface["tx_errors"]}'
                    )

                lines.extend([
                    "# HELP mikrotik_interface_rx_rate_bps Tasa actual de recepcion en bits por segundo",
                    "# TYPE mikrotik_interface_rx_rate_bps gauge",
                ])
                for (r_id, name), iface in metrics_store["interfaces"].items():
                    lines.append(
                        f'mikrotik_interface_rx_rate_bps{{router_id="{r_id}",interface="{name}",type="{iface["type"]}"}} {iface["rx_rate_bps"]:.2f}'
                    )

                lines.extend([
                    "# HELP mikrotik_interface_tx_rate_bps Tasa actual de transmision en bits por segundo",
                    "# TYPE mikrotik_interface_tx_rate_bps gauge",
                ])
                for (r_id, name), iface in metrics_store["interfaces"].items():
                    lines.append(
                        f'mikrotik_interface_tx_rate_bps{{router_id="{r_id}",interface="{name}",type="{iface["type"]}"}} {iface["tx_rate_bps"]:.2f}'
                    )

            output = "\n".join(lines) + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(output.encode("utf-8"))

        else:
            # Endpoint raíz '/' retorna estado general en formato JSON
            with data_lock:
                summary = {
                    "status": "online",
                    "exporter_port": EXPORTER_PORT,
                    "poll_interval": CHECK_INTERVAL_SECONDS,
                    "routers_monitored": len(metrics_store["routers"]),
                    "interfaces_monitored": len(metrics_store["interfaces"]),
                    "routers": metrics_store["routers"],
                    "metrics_endpoint": "/metrics"
                }
            payload = json.dumps(summary, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(payload)

    def log_message(self, format, *args):
        # Desactivar logs ruidosos de peticiones HTTP en consola
        return


def start_metrics_server(port: int):
    """Inicia el servidor HTTP de Prometheus en segundo plano."""
    server = HTTPServer(("0.0.0.0", port), PrometheusMetricsHandler)
    logger.info(f" Servidor Prometheus Exporter activo en http://0.0.0.0:{port}/metrics")
    server.serve_forever()


# ===================================================
# ENTRADA PRINCIPAL
# ===================================================
if __name__ == "__main__":
    logger.info("==================================================")
    logger.info(" INICIANDO MOTOR DE MONITOREO MIKROTIK")
    logger.info("==================================================")

    # 1. Iniciar servidor HTTP en un hilo demonio
    http_thread = threading.Thread(target=start_metrics_server, args=(EXPORTER_PORT,), daemon=True)
    http_thread.start()

    # 2. Iniciar planificador programado de Telegram si está configurado
    if TELEGRAM_REPORT_INTERVAL_MINUTES > 0 or bool(TELEGRAM_DAILY_REPORT_TIME):
        def _scheduler():
            import telegram_reporter
            telegram_reporter.start_report_scheduler(only_wan=True)

        sched_thread = threading.Thread(target=_scheduler, daemon=True)
        sched_thread.start()

    # 3. Iniciar colector en el hilo principal
    try:
        poller_worker()
    except KeyboardInterrupt:
        logger.info("Monitoreo detenido por el usuario.")
