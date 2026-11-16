import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta
import math
import requests

import matplotlib
matplotlib.use("Agg")  # Backend no interactivo para servidores
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_DAILY_CHAT_ID,
    PROMETHEUS_URL,
    TELEGRAM_REPORT_INTERVAL_MINUTES,
    TELEGRAM_REPORT_WINDOW_MINUTES,
    TELEGRAM_REPORT_START_TIME,
    TELEGRAM_REPORT_END_TIME,
    TELEGRAM_DAILY_REPORT_TIME,
    APP_TIMEZONE,
    obtener_routers,
    get_current_time_str,
    timestamp_to_datetime,
)

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TelegramReporter")

OUTPUT_DIR = "graficas_telegram"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Paleta de colores para múltiples interfaces WAN (Dark NOC Theme)
IFACE_COLORS = [
    {"rx": "#00e676", "tx": "#00b0ff"},  # Verde neón / Cyan
    {"rx": "#76ff03", "tx": "#2979ff"},  # Lima / Azul eléctrico
    {"rx": "#ffd600", "tx": "#ff9100"},  # Amarillo / Naranja
    {"rx": "#e040fb", "tx": "#ff4081"},  # Magenta / Rosa neón
    {"rx": "#00e5ff", "tx": "#651fff"},  # Turquesa / Violeta
]

SENSOR_COLORS = {
    "cpu-temperature": "#ff5252",       # Rojo coral
    "board-temperature1": "#e040fb",    # Magenta / Violeta
    "board-temperature2": "#b388ff",    # Lavanda
    "switch-temperature": "#ffd600",   # Amarillo
    "sfp-temperature": "#1de9b6",       # Verde agua
}


def query_prometheus_range(query: str, start: float, end: float, step: str = "15s") -> list:
    """Ejecuta una consulta query_range a la API HTTP de Prometheus."""
    url = f"{PROMETHEUS_URL}/api/v1/query_range"
    try:
        resp = requests.get(url, params={"query": query, "start": start, "end": end, "step": step}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return data.get("data", {}).get("result", [])
    except Exception as e:
        logger.error(f"Error consultando Prometheus ({query}): {e}")
    return []


def query_prometheus_instant(query: str) -> list:
    """Ejecuta una consulta instantánea a Prometheus."""
    url = f"{PROMETHEUS_URL}/api/v1/query"
    try:
        resp = requests.get(url, params={"query": query}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return data.get("data", {}).get("result", [])
    except Exception as e:
        logger.error(f"Error en consulta instantánea ({query}): {e}")
    return []


def generate_router_chart(router: dict, window_minutes: int = None, only_wan: bool = True) -> str:
    """
    Genera una gráfica completa de alta resolución para un router MikroTik.
    Por defecto se enfoca exclusivamente en la(s) interfaz(ces) WAN.
    Incluye:
      1. Tráfico WAN (Mbps Rx y Tx con sombreado de ancho de banda)
      2. Carga de CPU (%) con umbral crítico al 85%
      3. Temperaturas de hardware (°C)
      4. Rango de tiempo medido y zona horaria en el pie de la gráfica
    """
    if window_minutes is None:
        window_minutes = TELEGRAM_REPORT_WINDOW_MINUTES

    r_id = router["id"]
    host = router["host"]
    now = time.time()
    start = now - (window_minutes * 60)

    # Texto amigable para la ventana temporal en títulos
    if window_minutes == 60:
        window_title_str = "Última 1 hora (60 min)"
    elif window_minutes % 60 == 0:
        window_title_str = f"Últimas {window_minutes // 60} horas ({window_minutes} min)"
    else:
        window_title_str = f"Últimos {window_minutes} min"

    # Determinar qué interfaces graficar
    if only_wan and router.get("wan_interfaces"):
        target_ifaces = router["wan_interfaces"]
        is_wan_mode = True
    else:
        target_ifaces = router.get("monitor_interfaces", [])
        is_wan_mode = False

    # 1. Consultar métricas en Prometheus
    series_rx_raw = query_prometheus_range(f'mikrotik_interface_rx_rate_bps{{router_id="{r_id}"}}', start, now)
    series_tx_raw = query_prometheus_range(f'mikrotik_interface_tx_rate_bps{{router_id="{r_id}"}}', start, now)
    series_cpu = query_prometheus_range(f'mikrotik_cpu_load_percent{{router_id="{r_id}"}}', start, now)
    series_temp = query_prometheus_range(f'mikrotik_temperature_celsius{{router_id="{r_id}"}}', start, now)

    # Filtrar solo interfaces seleccionadas (WAN)
    series_rx = [s for s in series_rx_raw if not target_ifaces or s["metric"].get("interface") in target_ifaces]
    series_tx = [s for s in series_tx_raw if not target_ifaces or s["metric"].get("interface") in target_ifaces]

    # 2. Configurar figura con estilo NOC Dark
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True)
    fig.patch.set_facecolor("#181b1f")

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#20242b")
        ax.tick_params(colors="#d8d9da", labelsize=8)
        ax.grid(True, color="#2f3542", linestyle="--", linewidth=0.6, alpha=0.8)
        for spine in ax.spines.values():
            spine.set_color("#3c4352")

    # --- PANEL 1: TRÁFICO WAN ---
    if is_wan_mode and len(target_ifaces) == 1:
        # Enfoque limpio con sombreado de área para una sola WAN
        wan_name = target_ifaces[0]
        has_wan_rx = False
        has_wan_tx = False

        for s in series_rx:
            times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
            mbps = [float(v[1]) / 1e6 for v in s["values"]]
            ax1.plot(times, mbps, label="WAN Descarga / Rx (Mbps)", color="#00e676", linewidth=2.0)
            ax1.fill_between(times, mbps, color="#00e676", alpha=0.18)
            has_wan_rx = True

        for s in series_tx:
            times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
            mbps = [float(v[1]) / 1e6 for v in s["values"]]
            ax1.plot(times, mbps, label="WAN Subida / Tx (Mbps)", color="#00b0ff", linewidth=2.0)
            ax1.fill_between(times, mbps, color="#00b0ff", alpha=0.15)
            has_wan_tx = True

        ax1.set_title(
            f"Router: {r_id}  |  Enlace WAN: {wan_name}  |  {window_title_str}",
            color="#ffffff",
            fontsize=12,
            fontweight="bold",
            pad=10,
        )
    else:
        # Modo multi-interfaz / multi-WAN
        ifaces_seen = {}
        color_idx = 0

        for s in series_rx:
            iface = s["metric"].get("interface", "iface")
            if iface not in ifaces_seen:
                ifaces_seen[iface] = IFACE_COLORS[color_idx % len(IFACE_COLORS)]
                color_idx += 1
            times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
            mbps = [float(v[1]) / 1e6 for v in s["values"]]
            c = ifaces_seen[iface]["rx"]
            ax1.plot(times, mbps, label=f"{iface} (Rx / In)", color=c, linewidth=1.8)

        for s in series_tx:
            iface = s["metric"].get("interface", "iface")
            if iface not in ifaces_seen:
                ifaces_seen[iface] = IFACE_COLORS[color_idx % len(IFACE_COLORS)]
                color_idx += 1
            times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
            mbps = [float(v[1]) / 1e6 for v in s["values"]]
            c = ifaces_seen[iface]["tx"]
            ax1.plot(times, mbps, label=f"{iface} (Tx / Out)", color=c, linewidth=1.8, linestyle="--")

        wan_label = "Enlaces WAN" if is_wan_mode else "Interfaces Monitoreadas"
        ax1.set_title(
            f"Router: {r_id}  |  {wan_label}: {', '.join(target_ifaces)}  |  {window_title_str}",
            color="#ffffff",
            fontsize=12,
            fontweight="bold",
            pad=10,
        )

    ax1.set_ylabel("Tráfico (Mbps)", color="#ffffff", fontsize=9, fontweight="bold")
    h1, l1 = ax1.get_legend_handles_labels()
    if h1:
        ax1.legend(loc="upper right", facecolor="#181b1f", edgecolor="#3c4352", labelcolor="#ffffff", fontsize=8)

    # --- PANEL 2: CARGA DE CPU ---
    for s in series_cpu:
        times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
        vals = [float(v[1]) for v in s["values"]]
        ax2.plot(times, vals, label="Carga de CPU (%)", color="#ff9100", linewidth=1.8)
        ax2.fill_between(times, vals, color="#ff9100", alpha=0.15)
    
    ax2.axhline(85, color="#ff5252", linestyle=":", linewidth=1.2, label="Umbral Crítico (85%)")
    ax2.set_ylabel("CPU (%)", color="#ffffff", fontsize=9, fontweight="bold")
    ax2.set_ylim(0, 100)
    ax2.legend(loc="upper right", facecolor="#181b1f", edgecolor="#3c4352", labelcolor="#ffffff", fontsize=8)

    # --- PANEL 3: TEMPERATURAS ---
    has_temp = False
    for s in series_temp:
        sensor = s["metric"].get("sensor", "sensor")
        times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
        vals = [float(v[1]) for v in s["values"]]
        c = SENSOR_COLORS.get(sensor, "#40c4ff")
        ax3.plot(times, vals, label=f"{sensor} (°C)", color=c, linewidth=1.6)
        has_temp = True

    if not has_temp:
        ax3.text(0.5, 0.5, "Sin sensores de temperatura reportados", color="#888888",
                 ha="center", va="center", transform=ax3.transAxes, fontsize=10)

    ax3.axhline(75, color="#ff5252", linestyle=":", linewidth=1.2, label="Límite Térmico (75°C)")
    ax3.set_ylabel("Temperatura (°C)", color="#ffffff", fontsize=9, fontweight="bold")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax3.legend(loc="upper right", facecolor="#181b1f", edgecolor="#3c4352", labelcolor="#ffffff", fontsize=8, ncol=3)

    # Pie de gráfica con el rango exacto de tiempo medido y zona horaria
    start_dt = timestamp_to_datetime(start)
    end_dt = timestamp_to_datetime(now)
    start_str = start_dt.strftime("%H:%M")
    end_str = end_dt.strftime("%H:%M")
    tz_name = getattr(APP_TIMEZONE, "key", "America/Caracas")

    if start_dt.date() == end_dt.date():
        periodo_str = f"Tiempo medido: {start_str} a {end_str} ({start_dt.strftime('%d/%m/%Y')})  •  Zona: {tz_name}"
    else:
        periodo_str = f"Tiempo medido: {start_dt.strftime('%d/%m %H:%M')} a {end_dt.strftime('%d/%m %H:%M')}  •  Zona: {tz_name}"

    ax3.set_xlabel(
        periodo_str,
        color="#00e5ff",
        fontsize=9.5,
        fontweight="bold",
        labelpad=8,
    )

    plt.tight_layout()

    # Guardar imagen
    image_filename = f"{r_id}.png"
    image_path = os.path.join(OUTPUT_DIR, image_filename)
    plt.savefig(image_path, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    return image_path


def get_current_router_stats(r_id: str, target_ifaces: list = None) -> dict:
    """Obtiene los valores actuales instantáneos de CPU, temperatura y tráfico del router."""
    stats = {
        "cpu_load": 0,
        "mem_percent": 0.0,
        "cpu_temp": "N/D",
        "board_temp": "N/D",
        "traffic": {},  # {iface: {"rx_mbps": float, "tx_mbps": float}}
    }

    # CPU
    res_cpu = query_prometheus_instant(f'mikrotik_cpu_load_percent{{router_id="{r_id}"}}')
    if res_cpu:
        stats["cpu_load"] = int(float(res_cpu[0]["value"][1]))

    # Memoria
    res_mem = query_prometheus_instant(f'mikrotik_memory_used_percent{{router_id="{r_id}"}}')
    if res_mem:
        stats["mem_percent"] = round(float(res_mem[0]["value"][1]), 1)

    # Temperaturas
    res_temp = query_prometheus_instant(f'mikrotik_temperature_celsius{{router_id="{r_id}"}}')
    for s in res_temp:
        sensor = s["metric"].get("sensor")
        val = round(float(s["value"][1]), 1)
        if sensor == "cpu-temperature":
            stats["cpu_temp"] = f"{val}°C"
        elif sensor in ("board-temperature1", "board-temperature"):
            stats["board_temp"] = f"{val}°C"

    # Tráfico actual
    res_rx = query_prometheus_instant(f'mikrotik_interface_rx_rate_bps{{router_id="{r_id}"}}')
    for s in res_rx:
        iface = s["metric"].get("interface")
        if target_ifaces and iface not in target_ifaces:
            continue
        rx_mbps = round(float(s["value"][1]) / 1e6, 2)
        if iface not in stats["traffic"]:
            stats["traffic"][iface] = {"rx_mbps": rx_mbps, "tx_mbps": 0.0}
        else:
            stats["traffic"][iface]["rx_mbps"] = rx_mbps

    res_tx = query_prometheus_instant(f'mikrotik_interface_tx_rate_bps{{router_id="{r_id}"}}')
    for s in res_tx:
        iface = s["metric"].get("interface")
        if target_ifaces and iface not in target_ifaces:
            continue
        tx_mbps = round(float(s["value"][1]) / 1e6, 2)
        if iface not in stats["traffic"]:
            stats["traffic"][iface] = {"rx_mbps": 0.0, "tx_mbps": tx_mbps}
        else:
            stats["traffic"][iface]["tx_mbps"] = tx_mbps

    return stats


def build_router_caption(router: dict, stats: dict, only_wan: bool = True, window_minutes: int = None) -> str:
    """Construye un mensaje explicativo y elegante en Markdown para acompañar la imagen."""
    r_id = router["id"]
    host = router["host"]
    now_str = get_current_time_str()
    w_min = window_minutes if window_minutes is not None else TELEGRAM_REPORT_WINDOW_MINUTES

    if w_min == 60:
        ventana_txt = "Última 1 hora (60 min)"
    elif w_min % 60 == 0:
        ventana_txt = f"Últimas {w_min // 60} horas ({w_min} min)"
    else:
        ventana_txt = f"Últimos {w_min} min"

    lineas_trafico = []
    if stats["traffic"]:
        for iface, rates in stats["traffic"].items():
            lineas_trafico.append(f"  • `{iface}`: ⬇️ `{rates['rx_mbps']} Mbps` | ⬆️ `{rates['tx_mbps']} Mbps`")
    else:
        lineas_trafico.append("  • _Sin tráfico reportado en este instante_")

    tipo_reporte = "WAN" if only_wan else "GLOBAL"
    titulo_trafico = "🌐 *Tráfico WAN:*" if only_wan else "📡 *Tráfico de Interfaces:*"

    caption = (
        f"📊 *REPORTE DE ESTADO {tipo_reporte} - {r_id}*\n"
        f"🌐 *Host:* `{host}`\n"
        f"⏱️ *Ventana de Gráfica:* `{ventana_txt}`\n"
        f"⚡ *CPU:* `{stats['cpu_load']}%` | 💾 *RAM:* `{stats['mem_percent']}%`\n"
        f"🌡️ *Temp CPU:* `{stats['cpu_temp']}` | *Placa:* `{stats['board_temp']}`\n"
        f"{titulo_trafico}\n"
        + "\n".join(lineas_trafico) + "\n"
        f"🕒 *Hora:* `{now_str}`"
    )
    return caption


def send_telegram_photo(image_path: str, caption: str, target_chat_id: str = None) -> bool:
    """Envía la imagen con su pie de foto formateado a Telegram (al chat general o canal diario)."""
    chat_id = (target_chat_id or TELEGRAM_CHAT_ID).strip()
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        logger.info(
            f"[MODO LOCAL / PRUEBA]: Imagen generada en '{image_path}'\n"
            f"(Para recibirla en Telegram, define TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID / TELEGRAM_DAILY_CHAT_ID en .env)\n"
            f"--- Pie de Foto ---\n{caption}\n"
        )
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, "rb") as photo_file:
            files = {"photo": (os.path.basename(image_path), photo_file, "image/png")}
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            resp = requests.post(url, data=data, files=files, timeout=20)
            if resp.status_code == 200:
                logger.info(f"✅ Imagen enviada exitosamente a Telegram ({chat_id}): {image_path}")
                return True
            else:
                logger.error(f"Error en respuesta de Telegram para {chat_id} ({resp.status_code}): {resp.text}")
    except Exception as err:
        logger.error(f"Error enviando foto a Telegram ({chat_id}): {err}")
    return False


def generate_daily_24h_chart(router: dict) -> tuple[str, dict]:
    """
    Genera una gráfica ejecutiva de 24 Horas para un router MikroTik enfocada en la WAN.
    Calcula picos máximos, promedios de tráfico y volumen transferido (GB).
    """
    r_id = router["id"]
    host = router["host"]
    now = time.time()
    start = now - 86400  # 24 horas exactas
    target_ifaces = router.get("wan_interfaces", []) or router.get("monitor_interfaces", [])
    wan_name = target_ifaces[0] if target_ifaces else "WAN"

    # Consultar Prometheus con step de 120s (720 puntos en 24h)
    series_rx_raw = query_prometheus_range(f'mikrotik_interface_rx_rate_bps{{router_id="{r_id}"}}', start, now, step="120s")
    series_tx_raw = query_prometheus_range(f'mikrotik_interface_tx_rate_bps{{router_id="{r_id}"}}', start, now, step="120s")
    series_cpu = query_prometheus_range(f'mikrotik_cpu_load_percent{{router_id="{r_id}"}}', start, now, step="120s")
    series_temp = query_prometheus_range(f'mikrotik_temperature_celsius{{router_id="{r_id}"}}', start, now, step="120s")

    series_rx = [s for s in series_rx_raw if not target_ifaces or s["metric"].get("interface") in target_ifaces]
    series_tx = [s for s in series_tx_raw if not target_ifaces or s["metric"].get("interface") in target_ifaces]

    stats = {
        "wan_name": wan_name,
        "max_rx": 0.0,
        "avg_rx": 0.0,
        "max_tx": 0.0,
        "avg_tx": 0.0,
        "total_gb": 0.0,
        "max_cpu": 0.0,
        "avg_cpu": 0.0,
        "max_cpu_temp": "N/D",
        "max_board_temp": "N/D",
    }

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True)
    fig.patch.set_facecolor("#181b1f")

    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#20242b")
        ax.tick_params(colors="#d8d9da", labelsize=8)
        ax.grid(True, color="#2f3542", linestyle="--", linewidth=0.6, alpha=0.8)
        for spine in ax.spines.values():
            spine.set_color("#3c4352")

    # --- PANEL 1: TRÁFICO WAN 24 HORAS ---
    rx_bytes_total = 0.0
    for s in series_rx:
        times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
        mbps = [float(v[1]) / 1e6 for v in s["values"]]
        if mbps:
            stats["max_rx"] = max(mbps)
            stats["avg_rx"] = sum(mbps) / len(mbps)
            rx_bytes_total += sum(float(v[1]) * 120.0 / 8.0 for v in s["values"])
        ax1.plot(times, mbps, label=f"Descarga / Rx (Pico: {stats['max_rx']:.1f} Mbps | Prom: {stats['avg_rx']:.1f} Mbps)", color="#00e676", linewidth=1.8)
        ax1.fill_between(times, mbps, color="#00e676", alpha=0.18)

    tx_bytes_total = 0.0
    for s in series_tx:
        times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
        mbps = [float(v[1]) / 1e6 for v in s["values"]]
        if mbps:
            stats["max_tx"] = max(mbps)
            stats["avg_tx"] = sum(mbps) / len(mbps)
            tx_bytes_total += sum(float(v[1]) * 120.0 / 8.0 for v in s["values"])
        ax1.plot(times, mbps, label=f"Subida / Tx (Pico: {stats['max_tx']:.1f} Mbps | Prom: {stats['avg_tx']:.1f} Mbps)", color="#00b0ff", linewidth=1.8)
        ax1.fill_between(times, mbps, color="#00b0ff", alpha=0.15)

    stats["total_gb"] = (rx_bytes_total + tx_bytes_total) / 1e9

    ax1.set_ylabel("Tráfico WAN (Mbps)", color="#ffffff", fontsize=9, fontweight="bold")
    ax1.set_title(f"REPORTE DIARIO 24 HORAS: {r_id}  |  WAN: {wan_name}", color="#ffffff", fontsize=12, fontweight="bold", pad=10)
    ax1.legend(loc="upper right", facecolor="#181b1f", edgecolor="#3c4352", labelcolor="#ffffff", fontsize=8)

    # --- PANEL 2: CPU 24 HORAS ---
    for s in series_cpu:
        times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
        vals = [float(v[1]) for v in s["values"]]
        if vals:
            stats["max_cpu"] = max(vals)
            stats["avg_cpu"] = sum(vals) / len(vals)
        ax2.plot(times, vals, label=f"Carga de CPU (Pico: {stats['max_cpu']:.0f}% | Prom: {stats['avg_cpu']:.1f}%)", color="#ff9100", linewidth=1.6)
        ax2.fill_between(times, vals, color="#ff9100", alpha=0.15)
    ax2.axhline(85, color="#ff5252", linestyle=":", label="Umbral Crítico (85%)", linewidth=1.2)
    ax2.set_ylabel("CPU (%)", color="#ffffff", fontsize=9, fontweight="bold")
    ax2.set_ylim(0, 100)
    ax2.legend(loc="upper right", facecolor="#181b1f", edgecolor="#3c4352", labelcolor="#ffffff", fontsize=8)

    # --- PANEL 3: TEMPERATURAS 24 HORAS ---
    has_temp = False
    for s in series_temp:
        sensor = s["metric"].get("sensor", "sensor")
        times = [timestamp_to_datetime(float(v[0])) for v in s["values"]]
        vals = [float(v[1]) for v in s["values"]]
        c = SENSOR_COLORS.get(sensor, "#40c4ff")
        pico_t = max(vals) if vals else 0
        if sensor == "cpu-temperature":
            stats["max_cpu_temp"] = f"{pico_t:.0f}°C"
        elif sensor in ("board-temperature1", "board-temperature"):
            stats["max_board_temp"] = f"{pico_t:.0f}°C"
        ax3.plot(times, vals, label=f"{sensor} (Max: {pico_t:.0f}°C)", color=c, linewidth=1.5)
        has_temp = True

    if not has_temp:
        ax3.text(0.5, 0.5, "Sin sensores de temperatura reportados", color="#888888",
                 ha="center", va="center", transform=ax3.transAxes, fontsize=10)

    ax3.axhline(75, color="#ff5252", linestyle=":", linewidth=1.2, label="Límite Térmico (75°C)")
    ax3.set_ylabel("Temperatura (°C)", color="#ffffff", fontsize=9, fontweight="bold")
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%d-%b"))
    ax3.legend(loc="upper right", facecolor="#181b1f", edgecolor="#3c4352", labelcolor="#ffffff", fontsize=8, ncol=3)

    # Pie de gráfica con el rango exacto de 24 horas y zona horaria
    start_dt = timestamp_to_datetime(start)
    end_dt = timestamp_to_datetime(now)
    tz_name = getattr(APP_TIMEZONE, "key", "America/Caracas")
    ax3.set_xlabel(
        f"Período evaluado (24 Horas): {start_dt.strftime('%d/%m/%Y %H:%M')} a {end_dt.strftime('%d/%m/%Y %H:%M')}  •  Zona: {tz_name}",
        color="#00e5ff",
        fontsize=9.5,
        fontweight="bold",
        labelpad=8,
    )

    plt.tight_layout()
    image_filename = f"{r_id}_24H.png"
    image_path = os.path.join(OUTPUT_DIR, image_filename)
    plt.savefig(image_path, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)

    return image_path, stats


def build_daily_24h_caption(router: dict, stats: dict) -> str:
    """Construye un mensaje ejecutivo de balance de 24 horas para Telegram."""
    r_id = router["id"]
    host = router["host"]
    now_str = get_current_time_str()

    caption = (
        f"📊 *REPORTE DIARIO DE 24 HORAS: {r_id}*\n"
        f"🌐 *Host:* `{host}`\n"
        f"🌐 *Enlace WAN:* `{stats['wan_name']}`\n\n"
        f"📈 *Consumo y Métricas WAN (24 Horas):*\n"
        f"  • ⬇️ *Pico Descarga (Rx Max):* `{stats['max_rx']:.2f} Mbps`\n"
        f"  • ⬇️ *Promedio Descarga (Rx Avg):* `{stats['avg_rx']:.2f} Mbps`\n"
        f"  • ⬆️ *Pico Subida (Tx Max):* `{stats['max_tx']:.2f} Mbps`\n"
        f"  • ⬆️ *Promedio Subida (Tx Avg):* `{stats['avg_tx']:.2f} Mbps`\n"
        f"  • 📦 *Volumen Transferido Estimado:* `{stats['total_gb']:.2f} GB`\n\n"
        f"⚡ *Salud de Hardware en 24h:*\n"
        f"  • 💻 *Carga CPU:* Pico `{stats['max_cpu']:.0f}%` | Promedio `{stats['avg_cpu']:.1f}%`\n"
        f"  • 🌡️ *Temperatura CPU Máxima:* `{stats['max_cpu_temp']}`\n"
        f"  • 🌡️ *Temperatura Placa Máxima:* `{stats['max_board_temp']}`\n\n"
        f"🕒 *Cierre Diario:* `{now_str}`"
    )
    return caption


def run_daily_report(target_router: str = None) -> None:
    """Ejecuta el ciclo de reporte diario de 24h y lo envía al canal/chat diario de Telegram."""
    routers = obtener_routers()
    if not routers:
        logger.warning("No se encontraron routers configurados en el archivo .env.")
        return

    dest_chat = (TELEGRAM_DAILY_CHAT_ID or TELEGRAM_CHAT_ID).strip()
    logger.info(f"Iniciando Generación de Reportes Diarios de 24 Horas (Destino: {dest_chat})...")

    generados = 0
    enviados = 0

    for router in routers:
        r_id = router["id"]
        if target_router and r_id.lower() != target_router.lower():
            continue

        logger.info(f"Procesando reporte 24h para: {r_id} ({router['host']})...")
        try:
            image_path, stats = generate_daily_24h_chart(router)
            caption = build_daily_24h_caption(router, stats)

            enviado = send_telegram_photo(image_path, caption, target_chat_id=dest_chat)
            generados += 1
            if enviado:
                enviados += 1
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error generando reporte diario para {r_id}: {e}")

    logger.info(f"Finalizado Reporte Diario 24h: {generados} generadas, {enviados} enviadas a {dest_chat}.")


def run_report(target_router: str = None, window_minutes: int = None, only_wan: bool = True):
    """Ejecuta el ciclo de reporte generando y enviando una imagen por router."""
    if window_minutes is None:
        window_minutes = TELEGRAM_REPORT_WINDOW_MINUTES

    routers = obtener_routers()
    if not routers:
        logger.warning("No se encontraron routers configurados en el archivo .env.")
        return

    modo = "WAN Exclusivo" if only_wan else "Todas las Interfaces"
    logger.info(f"Iniciando generación de reportes ({modo}, Ventana: {window_minutes} min)...")

    generados = 0
    enviados = 0

    for router in routers:
        r_id = router["id"]
        if target_router and r_id.lower() != target_router.lower():
            continue

        target_ifaces = router.get("wan_interfaces", []) if only_wan else router.get("monitor_interfaces", [])
        logger.info(f"Procesando router: {r_id} ({router['host']}) - Interfaces objetivo: {target_ifaces}...")

        try:
            image_path = generate_router_chart(router, window_minutes=window_minutes, only_wan=only_wan)
            stats = get_current_router_stats(r_id, target_ifaces=target_ifaces)
            caption = build_router_caption(router, stats, only_wan=only_wan, window_minutes=window_minutes)

            enviado = send_telegram_photo(image_path, caption)
            generados += 1
            if enviado:
                enviados += 1
            
            # Pausa breve para respetar rate-limits de Telegram
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error generando reporte para {r_id}: {e}")

    logger.info(f"Finalizado: {generados} gráficas WAN generadas, {enviados} enviadas a Telegram.")


def calculate_next_report_time(
    start_time_str: str = None,
    end_time_str: str = None,
    interval_minutes: int = None,
    from_dt: datetime = None,
) -> tuple[datetime, float]:
    """
    Calcula la próxima fecha/hora exacta de reporte y los segundos de espera restantes.
    Sincroniza los envíos con intervalos exactos (ej. 08:00, 09:00, 10:00).
    """
    if start_time_str is None:
        start_time_str = TELEGRAM_REPORT_START_TIME
    if end_time_str is None:
        end_time_str = TELEGRAM_REPORT_END_TIME
    if interval_minutes is None:
        interval_minutes = TELEGRAM_REPORT_INTERVAL_MINUTES

    if from_dt is None:
        from_dt = datetime.now(APP_TIMEZONE) if APP_TIMEZONE else datetime.now()

    if interval_minutes <= 0:
        return from_dt, 0.0

    interval_sec = interval_minutes * 60

    # Si no se definió hora de inicio, el siguiente reporte es ahora + intervalo
    if not start_time_str:
        next_dt = from_dt + timedelta(seconds=interval_sec)
        return next_dt, max(0.0, (next_dt - from_dt).total_seconds())

    # Parsear hora de inicio (HH:MM)
    try:
        sh, sm = map(int, start_time_str.split(":"))
    except ValueError:
        sh, sm = 8, 0

    start_today = from_dt.replace(hour=sh, minute=sm, second=0, microsecond=0)

    # Parsear hora de fin si existe (HH:MM)
    end_today = None
    if end_time_str:
        try:
            eh, em = map(int, end_time_str.split(":"))
            end_today = from_dt.replace(hour=eh, minute=em, second=0, microsecond=0)
        except ValueError:
            end_today = None

    # Caso 1: Aún no llega la hora de inicio de hoy
    if from_dt < start_today:
        return start_today, max(0.0, (start_today - from_dt).total_seconds())

    # Caso 2: Ya pasó la hora de inicio de hoy, calcular el siguiente slot
    elapsed_sec = (from_dt - start_today).total_seconds()
    slots_passed = math.floor(elapsed_sec / interval_sec)
    next_slot = start_today + timedelta(seconds=(slots_passed + 1) * interval_sec)

    # Caso 3: Si hay hora de fin y el próximo slot supera la hora de fin
    if end_today and next_slot > end_today:
        # Se reprograma para la hora de inicio de mañana
        next_slot = start_today + timedelta(days=1)

    wait_sec = max(0.0, (next_slot - from_dt).total_seconds())
    return next_slot, wait_sec


def check_and_send_daily_report(last_daily_sent_date: list):
    """Revisa si llegó la hora del reporte diario de 24h al canal independiente."""
    if not TELEGRAM_DAILY_REPORT_TIME:
        return
    now_tz = datetime.now(APP_TIMEZONE) if APP_TIMEZONE else datetime.now()
    today_str = now_tz.strftime("%Y-%m-%d")
    if last_daily_sent_date and last_daily_sent_date[0] == today_str:
        return

    try:
        dh, dm = map(int, TELEGRAM_DAILY_REPORT_TIME.split(":"))
        target_today = now_tz.replace(hour=dh, minute=dm, second=0, microsecond=0)
    except ValueError:
        return

    # Si estamos en o superamos la hora objetivo dentro de una ventana de 5 minutos
    diff_sec = (now_tz - target_today).total_seconds()
    if 0 <= diff_sec <= 300:
        logger.info(f"🌟 [HORARIO REPORTE 24H] Hora {TELEGRAM_DAILY_REPORT_TIME} alcanzada. Enviando balance diario a canal...")
        last_daily_sent_date[0] = today_str
        try:
            run_daily_report()
        except Exception as err:
            logger.error(f"Error enviando reporte diario de 24h: {err}")


def start_report_scheduler(
    target_router: str = None,
    window_minutes: int = None,
    only_wan: bool = True,
    interval_minutes: int = None,
    start_time_str: str = None,
    end_time_str: str = None,
):
    """
    Bucle planificador inteligente para envío periódico de gráficas.
    Gestiona tanto los reportes periódicos como el reporte diario de 24h al canal de Telegram.
    """
    if window_minutes is None:
        window_minutes = TELEGRAM_REPORT_WINDOW_MINUTES

    interval = interval_minutes if interval_minutes is not None else TELEGRAM_REPORT_INTERVAL_MINUTES
    start_t = start_time_str if start_time_str is not None else TELEGRAM_REPORT_START_TIME
    end_t = end_time_str if end_time_str is not None else TELEGRAM_REPORT_END_TIME

    tz_name = getattr(APP_TIMEZONE, "key", "Local")
    logger.info("==================================================")
    logger.info("📅 INICIANDO PLANIFICADOR PROGRAMADO DE TELEGRAM")
    logger.info(f"   • Zona Horaria: {tz_name}")
    logger.info(f"   • Reportes Periódicos: Cada {interval} min (Inicio: {start_t or 'Inmediato'}, Fin: {end_t or '24h'})")
    logger.info(f"   • Ventana de Gráficas: {window_minutes} min")
    logger.info(f"   • Destino Periódico: {TELEGRAM_CHAT_ID or 'No configurado'}")
    logger.info(f"   • Reporte Diario 24h: {TELEGRAM_DAILY_REPORT_TIME or 'Desactivado'}")
    logger.info(f"   • Destino Canal 24h: {TELEGRAM_DAILY_CHAT_ID or TELEGRAM_CHAT_ID or 'No configurado'}")
    logger.info("==================================================")

    last_daily_sent = [None]

    while True:
        # 1. Chequeo de reporte diario de 24 horas
        check_and_send_daily_report(last_daily_sent)

        # 2. Si no hay intervalo periódico, solo verificar periódicamente el reporte diario
        if interval <= 0:
            time.sleep(15)
            continue

        next_dt, wait_sec = calculate_next_report_time(
            start_time_str=start_t,
            end_time_str=end_t,
            interval_minutes=interval,
        )
        wait_min = wait_sec / 60.0
        logger.info(f"⏳ Próximo reporte periódico: {next_dt.strftime('%Y-%m-%d %H:%M:%S')} (en {wait_min:.1f} min)")

        # Esperar hasta alcanzar la hora objetivo del próximo reporte
        while True:
            now_dt = datetime.now(APP_TIMEZONE) if APP_TIMEZONE else datetime.now()
            remaining_sec = (next_dt - now_dt).total_seconds()
            if remaining_sec <= 0.5:
                break

            # Dormir en bloques pequeños de hasta 5 segundos para verificar reporte diario
            sleep_step = min(remaining_sec, 5.0)
            time.sleep(max(sleep_step, 0.2))
            check_and_send_daily_report(last_daily_sent)

        logger.info(f"🚀 [HORARIO ALCANZADO] Enviando reporte periódico ({get_current_time_str()})...")
        try:
            run_report(target_router=target_router, window_minutes=window_minutes, only_wan=only_wan)
        except Exception as err:
            logger.error(f"Error en envío programado: {err}")

        # Pausa de 3 segundos para asegurar que el reloj sobrepase el slot recién ejecutado
        time.sleep(3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generador y emisor de gráficas MikroTik por router para Telegram.")
    parser.add_argument("--router", type=str, default=None, help="Nombre o ID del router específico (opcional)")
    parser.add_argument("--window", type=int, default=None, help=f"Ventana de tiempo en minutos (default: {TELEGRAM_REPORT_WINDOW_MINUTES} min según intervalo o .env)")
    parser.add_argument("--interval", type=int, default=None, help="Minutos entre cada reporte (ej: 60)")
    parser.add_argument("--start", type=str, default=None, help="Hora de inicio en formato HH:MM (ej: 08:00)")
    parser.add_argument("--end", type=str, default=None, help="Hora de fin en formato HH:MM (ej: 22:00)")
    parser.add_argument("--schedule", action="store_true", help="Activar modo planificador continuo respetando horario e intervalo")
    parser.add_argument("--daily", action="store_true", help="Generar y enviar inmediatamente el reporte diario de 24 horas al canal de Telegram")
    parser.add_argument("--all-ifaces", action="store_true", help="Graficar todas las interfaces monitoreadas en lugar de solo la WAN")
    args = parser.parse_args()

    only_wan_mode = not args.all_ifaces

    if args.daily:
        run_daily_report(target_router=args.router)
    elif args.schedule:
        start_report_scheduler(
            target_router=args.router,
            window_minutes=args.window,
            only_wan=only_wan_mode,
            interval_minutes=args.interval,
            start_time_str=args.start,
            end_time_str=args.end,
        )
    else:
        # Por defecto ejecución inmediata (ideal para pruebas y envíos manuales bajo demanda)
        run_report(target_router=args.router, window_minutes=args.window, only_wan=only_wan_mode)
