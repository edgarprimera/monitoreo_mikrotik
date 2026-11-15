# Sistema de Monitoreo de Interfaces MikroTik

Sistema ligero, multi-hilo y escalable en Python para la monitorización en tiempo real de interfaces de red en múltiples routers MikroTik (RouterOS v6 y v7) a través de la API nativa.

## 🚀 Características

- **Soporte Multi-Router Dinámico**: Configuración centralizada vía variables de entorno (`.env`) sin límite de routers.
- **Monitoreo en Paralelo**: Consultas simultáneas con `ThreadPoolExecutor` para no retrasar el ciclo de recolección.
- **Detección Automática de Estado**: Monitoreo de interfaces físicas (`ether`, `sfp`), lógicas (`vlan`, `bridge`, `loopback`) y túneles (`wireguard`, etc.).
- **Métricas Prometheus Ready**: Exposición nativa de métricas en formato texto (`/metrics`) en el puerto 9177:
  - Estado del enlace (`running` 1/0).
  - Tráfico acumulado (`rx-byte`, `tx-byte`).
  - Tasas calculadas en tiempo real (`rx_rate_bps`, `tx_rate_bps`).
  - Errores de interfaz (`rx-error`, `tx-error`).
  - Estado del router (`up` 1/0).
- **Dashboard JSON en Tiempo Real**: Endpoint raíz (`http://localhost:9177/`) con el estado en vivo de todos los routers.
- **Alertas Inmediatas por Telegram**: Notificación instantánea con anti-flapping en caso de caída de enlace (*Link Down*), restauración (*Link Up*) o router inalcanzable.
- **Ganchos de Automatización**: Hook extensible `on_critical_interface_down` para ejecutar remediación segura en interfaces críticas.

---

## 📋 Requisitos e Instalación

1. **Python 3.10+**
2. Clonar el repositorio y acceder a la carpeta:
   ```bash
   git clone git@github.com:edgarprimera/monitoreo_mikrotik.git
   cd monitoreo_mikrotik
   ```
3. Instalar librerías:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🔒 Configuración en MikroTik

En cada router MikroTik, crea un usuario con permisos de solo lectura para el monitoreo (y `write`/`test` solo si requieres automatización activa):

```routeros
# 1. Crear grupo de monitoreo
/user group add name=group-monitoreo policy=read,api,test

# 2. Crear usuario restringido a la IP del servidor de monitoreo (ej: 10.141.10.50)
/user add name=usr_monitoreo group=group-monitoreo allowed-address=10.141.10.50/32 password="TuPasswordSeguro"

# 3. Habilitar servicio API con restricción
/ip service set api address=10.141.10.50/32 disabled=no
```

---

## ⚙️ Configuración del Entorno (`.env`)

Copia el archivo de ejemplo y edítalo con tus datos:
```bash
cp .env_example .env
```

Ejemplo de estructura en `.env`:
```env
EXPORTER_PORT=9177
CHECK_INTERVAL_SECONDS=10

# Notificaciones por Telegram (Opcional)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=-1001234567890

# Routers a monitorear (agrega tantos como necesites incrementando el índice)
ROUTER_1_ID=CORE_BRISAS
ROUTER_1_HOST=10.141.10.29
ROUTER_1_PORT=18728
ROUTER_1_USER=usr_monitoreo
ROUTER_1_PASS=TuPasswordSeguro
ROUTER_1_CRITICAL_IFACES=ether1,sfp-sfpplus1

ROUTER_2_ID=CORE_GUACARA
ROUTER_2_HOST=10.141.10.1
ROUTER_2_PORT=18728
ROUTER_2_USER=usr_monitoreo
ROUTER_2_PASS=TuPasswordSeguro
ROUTER_2_CRITICAL_IFACES=sfp-sfpplus1
```

---

## 🐳 Despliegue con Docker Compose (Recomendado)

El proyecto incluye un entorno completo llave en mano con **Python Exporter**, **Prometheus** y **Grafana** (con aprovisionamiento automático de origen de datos y dashboards).

### 1. Iniciar la infraestructura:
```bash
docker compose up -d --build
```

### 2. Puntos de acceso:
* 📊 **Grafana:** [http://localhost:3000](http://localhost:3000) (Usuario: `admin` / Clave: `admin`)
  - El dashboard **"MikroTik Network Interfaces Monitor"** ya viene preconfigurado con selección de routers e interfaces, tráfico Rx/Tx en Mbps y alertas.
* 📈 **Prometheus:** [http://localhost:9090](http://localhost:9090)
* ⚡ **Python Exporter / API:** [http://localhost:9177](http://localhost:9177) y [http://localhost:9177/metrics](http://localhost:9177/metrics)

### 3. Ver logs en tiempo real:
```bash
docker compose logs -f mikrotik-monitor
```

### 4. Detener el stack:
```bash
docker compose down
```

---

## 🧪 Ejecución Manual sin Docker

### 1. Diagnóstico Inicial de Conectividad
Prueba la conexión y lista las interfaces de todos los routers configurados:
```bash
python test_conexion.py
```

### 2. Iniciar el Motor de Monitoreo Continuo
```bash
python monitor_engine.py
```

Salida esperada:
- **Consola:** Logs con el estado de cada router y notificaciones.
- **Resumen en vivo:** Abre en tu navegador `http://localhost:9177/`
- **Métricas Prometheus:** Consulta `http://localhost:9177/metrics`

---

## 📊 Integración con Prometheus y Grafana

### En `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'mikrotik_exporter'
    scrape_interval: 10s
    static_configs:
      - targets: ['localhost:9177']
```

### Consultas PromQL para Grafana:
* **Tráfico RX en Mbps:**
  ```promql
  rate(mikrotik_interface_rx_bytes_total[1m]) * 8 / 1000000
  ```
  *(O usando directamente la métrica precalculada: `mikrotik_interface_rx_rate_bps / 1000000`)*
* **Tráfico TX en Mbps:**
  ```promql
  rate(mikrotik_interface_tx_bytes_total[1m]) * 8 / 1000000
  ```
* **Interfaces en estado Down:**
  ```promql
  mikrotik_interface_running == 0
  ```
* **Routers inalcanzables:**
  ```promql
  mikrotik_router_up == 0
  ```

---

## 📁 Estructura del Proyecto

```text
├── .env                  # Credenciales reales (ignorado por Git)
├── .env_example          # Plantilla de configuración
├── .gitignore            # Exclusión de archivos sensibles y temporales
├── README.md             # Documentación del sistema
├── config.py             # Cargador centralizado de variables y routers
├── monitor_engine.py     # Motor de monitoreo paralelo, exporter y alertas
├── requirements.txt      # Librerías necesarias
└── test_conexion.py      # Script de validación de conexión API
```
