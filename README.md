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
  - Carga de CPU en porcentaje (`mikrotik_cpu_load_percent`).
  - Uso de memoria RAM en porcentaje (`mikrotik_memory_used_percent`).
  - Sensores de temperatura de hardware (`mikrotik_temperature_celsius` para CPU, placa, SFP y switch).
- **Dashboard JSON en Tiempo Real**: Endpoint raíz (`http://localhost:9177/`) con el estado en vivo de todos los routers.
- **Alertas Inmediatas por Telegram**: Notificación instantánea con anti-flapping en caso de caída de enlace (*Link Down*), restauración (*Link Up*), router inalcanzable, alta carga de CPU (>90%) o temperatura crítica (>75°C).
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

# 2. Crear usuario restringido a la IP del servidor de monitoreo (ej: 192.168.88.50)
/user add name=usr_monitoreo group=group-monitoreo allowed-address=192.168.88.50/32 password="TuPasswordSeguro"

# 3. Habilitar servicio API con restricción
/ip service set api address=192.168.88.50/32 disabled=no
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
ROUTER_1_ID=RB-CORE-01
ROUTER_1_HOST=192.168.88.1
ROUTER_1_PORT=8728
ROUTER_1_USER=usr_monitoreo
ROUTER_1_PASS=TuPasswordSeguro1
# Lista blanca: SOLO se monitorean, grafican y alertan estas interfaces
ROUTER_1_MONITOR_IFACES=ether1,sfp-sfpplus1,sfp-sfpplus2
ROUTER_1_CRITICAL_IFACES=ether1,sfp-sfpplus1

ROUTER_2_ID=RB-DISTRIBUCION-02
ROUTER_2_HOST=192.168.88.2
ROUTER_2_PORT=8728
ROUTER_2_USER=usr_monitoreo
ROUTER_2_PASS=TuPasswordSeguro2
ROUTER_2_MONITOR_IFACES=ether1,sfp-sfpplus1
ROUTER_2_CRITICAL_IFACES=ether1
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

## 🌐 Guía de Despliegue en un VPS (Servidor en la Nube)

Esta guía detalla los pasos para instalar y poner en producción este sistema de monitoreo en un servidor VPS remoto (Ubuntu 22.04 / 24.04 LTS o Debian 12 en DigitalOcean, Linode, AWS, Hetzner, etc.).

### 1. Requisitos Mínimos del VPS
* **Sistema Operativo:** Ubuntu 22.04 / 24.04 LTS o Debian 12.
* **Hardware:** 1 vCPU, 1 GB RAM, 20 GB de disco SSD.
* **Conectividad con los MikroTik:** 
  * El VPS debe poder alcanzar los routers en sus puertos API (ej. a través de una VPN como **WireGuard** o túnel SSTP/OpenVPN, o mediante IPs públicas con *allowlist* en el firewall de RouterOS).

---

### 2. Actualizar el Servidor e Instalar Docker

Conéctate a tu VPS por SSH y ejecuta:

```bash
# Actualizar repositorios y paquetes
sudo apt update && sudo apt upgrade -y

# Instalar dependencias básicas
sudo apt install -y git curl ufw

# Instalar Docker mediante el script oficial automatizado
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Permitir uso de Docker sin sudo para tu usuario
sudo usermod -aG docker $USER
newgrp docker

# Verificar instalación
docker --version && docker compose version
```

---

### 3. Seguridad y Firewall del VPS (UFW)

Para evitar exponer puertos internos a internet, configura el firewall `ufw` en el VPS:

```bash
# Reglas por defecto
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Permitir SSH (¡No te quedes afuera!)
sudo ufw allow 22/tcp

# Permitir acceso al panel de Grafana
sudo ufw allow 3000/tcp

# (Opcional) Si conectas los MikroTik al VPS vía WireGuard:
# sudo ufw allow 51820/udp

# Activar firewall
sudo ufw enable
```

> [!IMPORTANT]
> Los puertos **9090** (Prometheus) y **9177** (Exporter Python) no deben abrirse al público en el firewall; los contenedores se comunican entre sí a través de la red privada interna de Docker.

---

### 4. Clonar el Proyecto y Configurar Credenciales

```bash
# 1. Clonar el repositorio
git clone https://github.com/edgarprimera/monitoreo_mikrotik.git
cd monitoreo_mikrotik

# 2. Crear archivo de variables de entorno a partir de la plantilla
cp .env_example .env

# 3. Editar con los datos de tus routers y token de Telegram
nano .env
```
*(Guarda los cambios con `Ctrl + O`, `Enter` y sal con `Ctrl + X`).*

---

### 5. Iniciar los Servicios en Segundo Plano

Ejecuta el despliegue con Docker Compose:

```bash
docker compose up -d --build
```

Comprueba que los tres contenedores estén en estado `Up`:
```bash
docker compose ps
```

Verifica los logs del colector:
```bash
docker compose logs -f mikrotik-monitor
```

---

### 6. Acceso al Panel de Grafana en el VPS

Abre tu navegador e ingresa a:
👉 **`http://IP_PUBLICA_DE_TU_VPS:3000`**
* **Usuario:** `admin`
* **Contraseña inicial:** `admin` *(el sistema te pedirá cambiarla en el primer inicio de sesión)*.

Ve a **Dashboards** $\rightarrow$ **MikroTik NOC - Monitoreo Global** para ver el panel en vivo.

---

### 7. Comandos Útiles de Mantenimiento en el VPS

* **Actualizar el sistema si haces cambios en GitHub:**
  ```bash
  git pull
  docker compose up -d --build
  ```
* **Aplicar cambios tras editar el `.env`:**
  ```bash
  docker compose up -d mikrotik-monitor
  ```
* **Reiniciar todo el stack:**
  ```bash
  docker compose restart
  ```
* **Hacer un test rápido de conexión desde la terminal del VPS:**
  ```bash
  docker compose exec mikrotik-monitor python test_conexion.py
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

## 📸 Reportes con Gráficas por Router en Telegram (`telegram_reporter.py`)

El sistema incluye un generador nativo de diagnósticos gráficos que consulta Prometheus y envía a Telegram una imagen de alta resolución (estilo NOC Dark) por cada router con su resumen técnico en vivo.

Cada gráfica incluye 3 subplots sincronizados:
1. **Tráfico de Interfaces Monitoreadas (Mbps):** Líneas de entrada (Rx ⬇️) y salida (Tx ⬆️) con colores independientes por enlace.
2. **Carga de CPU (%):** Evolución temporal con sombreado y línea de umbral crítico al 85%.
3. **Sensores de Temperatura (°C):** Registro térmico de CPU, placa, switch y módulos SFP con límite al 75°C.

### 1. Ejecutar Prueba Manual Bajo Demanda
Genera y envía las gráficas de todos los routers a Telegram:
```bash
# En el host local o VPS
python telegram_reporter.py

# O directamente dentro del contenedor Docker:
docker compose exec mikrotik-monitor python telegram_reporter.py
```

Para generar únicamente la de un router específico:
```bash
python telegram_reporter.py --router BRISAS_1
```

### 2. Programar Horarios y Reportes Automáticos Periódicos
Puedes programar el bot para que inicie a una hora específica del día y luego envíe los reportes cada **X minutos** dentro de una ventana de tiempo (ej. horario de oficina):

Edita tu archivo `.env`:
```ini
# Enviar gráficas de todos los routers cada 60 minutos (0 = desactivado / solo manual o alertas)
TELEGRAM_REPORT_INTERVAL_MINUTES=60

# Hora de inicio diaria (HH:MM en hora de Caracas, ej: 08:00)
TELEGRAM_REPORT_START_TIME=08:00

# Hora de fin diaria (opcional, ej: 22:00. Si se omite, corre las 24 horas)
TELEGRAM_REPORT_END_TIME=22:00
```
Y aplica los cambios:
```bash
docker compose up -d mikrotik-monitor
```

El planificador sincroniza automáticamente los reportes con los minutos exactos (ejemplo: 08:00, 09:00, 10:00... hasta las 22:00) y se suspende durante la noche hasta las 08:00 del día siguiente.

### 3. Reporte Diario Ejecutivo de 24 Horas a Canal Independiente
Puedes configurar el envío automático de un balance diario de 24 horas a un **canal o grupo de Telegram separado** (ideal para directivos o clientes):

Edita tu archivo `.env`:
```ini
# ID del canal o grupo exclusivo para el reporte diario (ej. -1001234567890 o @mi_canal)
TELEGRAM_DAILY_CHAT_ID=-1001234567890

# Hora de envío del balance diario (HH:MM en hora de Caracas, ej: 23:59 o 00:00)
TELEGRAM_DAILY_REPORT_TIME=23:59
```

Cada noche a la hora indicada, el bot enviará al canal:
* Gráfica completa con las últimas 24 horas continuas de consumo WAN, CPU y temperatura.
* Pico máximo de descarga y subida (`Rx Max` y `Tx Max` en Mbps).
* Promedios de consumo diario (`Rx Avg` y `Tx Avg` en Mbps).
* Estimación del volumen total transferido en el día (**GB consumidos**).
* Picos de temperatura de hardware y carga máxima de procesamiento.

Para probar el reporte diario inmediatamente sin esperar a la medianoche:
```bash
python telegram_reporter.py --daily
# O dentro de Docker / VPS:
docker compose exec mikrotik-monitor python telegram_reporter.py --daily
```

### 4. Diagnóstico Automático en Caídas Críticas
Cuando una interfaz definida en `ROUTER_X_CRITICAL_IFACES` pasa a estado `DOWN`, el sistema dispara automáticamente la alerta de texto y genera de inmediato la gráfica con los últimos 30 minutos de comportamiento previo a la caída para facilitar el diagnóstico.

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
