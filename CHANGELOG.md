# Registro de Cambios (CHANGELOG)

Todos los cambios notables en este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/lang/es/).

---

## [1.4.3] - 2026-11-15

### Añadido
- **Planificador Inteligente de Horarios para Reportes en Telegram:**
  - Variables de control `TELEGRAM_REPORT_START_TIME` (hora de inicio) y `TELEGRAM_REPORT_END_TIME` (hora de fin) en `.env`.
  - Algoritmo de sincronización horaria exacta que alinea los disparos periódicos a horas y minutos en punto (ej. 08:00, 09:00, 10:00... cada X minutos).
  - Suspensión nocturna automática: el bot suspende el envío de gráficas fuera de la ventana operativa y reanuda a la hora de inicio del día siguiente (manteniendo activas las alertas críticas 24/7).
  - Parámetros de línea de comandos en `telegram_reporter.py` para planificador independiente (`--schedule`, `--start`, `--end`, `--interval`).

---

## [1.4.2] - 2026-11-15

### Añadido
- **Soporte de Zona Horaria Nativa (`America/Caracas`):**
  - Configuración centralizada de zona horaria mediante `TZ=America/Caracas` en `.env` y `docker-compose.yml`.
  - Normalización en Python con `zoneinfo.ZoneInfo` para garantizar que todas las alertas de Telegram, pies de foto y los ejes temporales (`HH:MM`) de las gráficas reflejen con total exactitud la hora de Caracas (VET, UTC-4).
  - Inclusión de variables de entorno de zona horaria en Prometheus y Grafana (`GF_DATE_FORMATS_DEFAULT_TIMEZONE=America/Caracas`).

---

## [1.4.1] - 2026-11-15

### Añadido
- **Enfoque Exclusivo en Interfaces WAN para el Bot de Telegram:**
  - Soporte para variables explícitas `ROUTER_X_WAN_IFACE` y `ROUTER_X_LAN_IFACES` en `.env`.
  - Mecanismo de auto-detección inteligente: si no se especifica `WAN_IFACE`, el colector identifica automáticamente cualquier interfaz que contenga la palabra `WAN` en su nombre.
  - Rediseño de la gráfica de tráfico del reporte: área sombreada limpia de ancho de banda para Descarga / Rx (`#00e676`) y Subida / Tx (`#00b0ff`) centrada en el enlace de salida a Internet.
  - Opción de línea de comandos `--all-ifaces` en `telegram_reporter.py` para alternar entre reporte exclusivo de WAN o reporte global de todas las interfaces.

---

## [1.4.0] - 2026-11-15

### Añadido
- **Reportes con Gráficas de Diagnóstico por Router para Telegram (`telegram_reporter.py`):**
  - Generador de imágenes de alta resolución (1200x850 px) con estilo NOC Dark por cada router MikroTik.
  - Subplots individuales: Tráfico en tiempo real por interfaz monitoreada (Mbps Rx y Tx con colores contrastantes), Carga de CPU (%) con área sombreada y umbral de alerta (85%), y Sensores de Temperatura (°C) para CPU, placa, switch y módulos SFP.
  - Envío automático mediante la API de Telegram Bot (`sendPhoto`) con pie de foto enriquecido en Markdown (IP, CPU, RAM, temperaturas y tasas de tráfico en vivo).
  - Soporte de ejecución manual de prueba bajo demanda: `python telegram_reporter.py` (o `--router <ID>`).
  - Configuración flexible de reportes periódicos mediante la variable `TELEGRAM_REPORT_INTERVAL_MINUTES` en `.env` (desactivado por defecto `0` para modo de prueba).
  - Integración en el hook de fallas críticas: envío automático de la gráfica de diagnóstico del router cuando una interfaz crítica pasa a estado DOWN.
  - Inclusión de dependencias de renderizado gráfico (`matplotlib`, `contourpy`, `kiwisolver`, etc.) en la carpeta `wheels/` para preservación de construcción 100% offline.

---

## [1.3.1] - 2026-11-15

### Añadido
- **Guía Completa de Despliegue en VPS en `README.md`:**
  - Requisitos mínimos de servidor (Ubuntu 22.04/24.04 LTS o Debian 12, 1 vCPU, 1 GB RAM).
  - Script automatizado de instalación de Docker y Docker Compose.
  - Configuración de firewall con UFW (apertura de SSH y puerto 3000 de Grafana, aislamiento de puertos internos 9090 y 9177).
  - Instrucciones paso a paso para clonar, configurar variables de entorno `.env` e iniciar los servicios con `docker compose`.
  - Guía de mantenimiento, comandos de actualización (`git pull`), reinicio y diagnóstico remoto.

---

## [1.3.0] - 2026-11-15

### Añadido
- **Monitoreo de Salud de Hardware:**
  - Lectura periódica de carga de CPU (`%`) y memoria RAM utilizada (`%`) desde `/system/resource`.
  - Lectura de sensores térmicos de hardware desde `/system/health`: temperatura de CPU, temperatura de placa (`board-temperature1`/`board-temperature2`), módulos SFP y chip de conmutación.
  - Alertas preventivas automáticas por Telegram ante sobrecalentamiento de CPU (>75°C) o sobrecarga prolongada de CPU (>90%).
- **Soporte Completo para VLANs WAN:**
  - Inclusión de VLANs de transporte y clientes (`97-WAN-NERVICON`, `95-NERVICOM_WAN`, `VLAN-300`, `VLAN-301`, etc.) en las gráficas globales y tablas de estado.
- **Rediseño Completo del Dashboard NOC en Grafana:**
  - Panel unificado de operaciones de red (NOC) para monitorear todos los routers en una sola pantalla sin necesidad de selectores desplegables.
  - Cuadrícula amplia y legible con tarjetas de estado de routers.
  - Medidores circulares (Gauges) grandes para carga de CPU.
  - Gráficas históricas de evolución térmica y de procesamiento en el tiempo.

### Arreglado
- **Corrección de Legibilidad:** Eliminación de la compresión horizontal en tiras delgadas en Grafana, pasando a una cuadrícula dinámica espaciosa (`3x2`) con tipografía clara y visible.
- **Corrección de Leyendas:** Asignación correcta de la etiqueta `(CPU)` a la gráfica de procesamiento y `(°C)` a la gráfica de temperaturas.
- **Detección de Interfaz en BRISAS_2:** Corrección de la IP de host en `.env` para `BRISAS_2` (`10.141.10.30:8590`), permitiendo la detección y graficación inmediata de `VLAN-301_TNC_TELECOM_OSPF_WAN`.
- **Eliminación de Bloqueos de VLAN:** Remoción de la regla de exclusión en Grafana que ocultaba inadvertidamente las interfaces WAN de tipo VLAN.

---

## [1.2.0] - 2026-11-15

### Añadido
- **Filtrado por Lista Blanca de Interfaces:**
  - Soporte para `ROUTER_X_MONITOR_IFACES` y `ROUTER_X_CRITICAL_IFACES` en `.env`.
  - Reducción drástica del ruido: de 151 interfaces sin usar (puertos Ethernet vacíos, loopbacks, bridges) a únicamente las interfaces críticas seleccionadas por el administrador.
- **Empaquetado Offline (`wheels/`):**
  - Inclusión de dependencias Python predescargadas en la carpeta `wheels/` para garantizar construcción 100% offline y evitar bloqueos de resolución DNS en entornos de red aislados.

### Cambiado
- **Anonimización de Documentación:** Actualización de `README.md` y `.env_example` con rangos de IP estándar Clase C (`192.168.88.x`) y nombres genéricos para proteger la topología real de producción.

---

## [1.1.0] - 2026-11-15

### Añadido
- **Motor de Monitoreo Continuo en Paralelo (`monitor_engine.py`):**
  - Consultas concurrentes multi-hilo (`ThreadPoolExecutor`) a múltiples routers MikroTik sin bloqueos.
  - Cálculo automático de tasas de tráfico en tiempo real (Rx / Tx en bps y Mbps).
  - Servidor Exporter HTTP nativo de Prometheus en el puerto `9177` (`/metrics`) sin librerías externas pesadas.
  - Endpoint de estado y diagnóstico en vivo en formato JSON (`http://localhost:9177/`).
- **Módulo de Alertas Inmediatas por Telegram:**
  - Notificaciones en milisegundos ante caídas de enlace (*Link Down*), recuperación (*Link Up*) y caídas de routers (*Unreachable*).
  - Mecanismo *anti-flapping* con ventana de enfriamiento para prevenir saturación de alertas.
  - Gancho extensible de automatización (`on_critical_interface_down`).
- **Infraestructura Completa con Docker Compose (`docker-compose.yml`):**
  - Orquestación de tres servicios: `mikrotik-monitor`, `prometheus` y `grafana`.
  - Aprovisionamiento automatizado de origen de datos Prometheus y dashboard preconfigurado.

---

## [1.0.0] - 2026-11-15

### Añadido
- **Inicialización del Proyecto:**
  - Vinculación al repositorio remoto en GitHub mediante autenticación por llave SSH.
  - Configuración estricta de seguridad en `.gitignore` para impedir que las credenciales e IPs de `.env` se suban al repositorio.
  - Archivo de plantilla `.env_example` documentado.
  - Script de validación y diagnóstico inicial de conectividad API (`test_conexion.py`).
  - Módulo centralizado de configuración dinámica multi-router (`config.py`).
  - Documentación inicial de arquitectura y buenas prácticas en MikroTik (`README.md`).
