# Sistema de Monitoreo de Interfaces MikroTik

Sistema ligero y escalable en Python para la monitorización en tiempo real de interfaces de red en múltiples routers MikroTik (RouterOS v6 y v7) a través de la API nativa.

## 🚀 Características

- **Soporte Multi-Router Dinámico**: Configuración centralizada vía variables de entorno (`.env`) sin límite de routers.
- **Detección Automática de Estado**: Monitoreo de interfaces físicas (`ether`, `sfp`), lógicas (`vlan`, `bridge`, `loopback`) y túneles (`wireguard`, etc.).
- **Métricas Prometheus Ready**: Exposición de métricas de tráfico (`rx-byte`, `tx-byte`), errores y estado del enlace (`running`) para visualización en Grafana.
- **Alertas Inmediatas por Telegram**: Notificación instantánea en caso de caída de enlace (*Link Down*) o router inalcanzable.
- **Ganchos de Automatización**: Posibilidad de ejecutar acciones correctivas (failover, reinicio o log) en interfaces críticas.

---

## 📋 Requisitos Previos

- **Python 3.10+**
- Servicio API habilitado en los routers MikroTik (`/ip service enable api` o puerto custom).
- Dependencias de Python:
  ```bash
  pip install -r requirements.txt
  ```

---

## 🔒 Configuración en MikroTik (Buenas Prácticas)

En cada router MikroTik, crea un usuario con permisos controlados y restringido a la IP del servidor de monitoreo:

```routeros
# 1. Crear grupo de monitoreo
/user group add name=group-monitoreo policy=read,api,test

# 2. Crear usuario restringido a la IP de monitoreo (ejemplo: 10.141.10.50)
/user add name=usr_monitoreo group=group-monitoreo allowed-address=10.141.10.50/32 password="TuPasswordSeguro"

# 3. Habilitar servicio API con restricción de origen
/ip service set api address=10.141.10.50/32 disabled=no
```

---

## ⚙️ Puesta en Marcha

1. **Clonar el repositorio:**
   ```bash
   git clone git@github.com:edgarprimera/monitoreo_mikrotik.git
   cd monitoreo_mikrotik
   ```

2. **Configurar el archivo de entorno:**
   Copia el archivo de ejemplo:
   ```bash
   cp .env_example .env
   ```
   Edita `.env` con las IPs, puertos, usuarios y contraseñas de tus routers.

3. **Verificar conectividad:**
   Ejecuta el script de prueba para validar que todos los routers respondan correctamente:
   ```bash
   python test_conexion.py
   ```

---

## 📁 Estructura del Proyecto

```text
├── .env                  # Credenciales reales (ignorado por Git)
├── .env_example          # Plantilla de configuración
├── .gitignore            # Exclusión de archivos sensibles
├── README.md             # Documentación del proyecto
├── requirements.txt      # Librerías necesarias
└── test_conexion.py      # Script de validación de conexión API
```

---

## 🛡️ Seguridad
El archivo `.env` contiene credenciales sensibles y está configurado en `.gitignore` para no ser subido jamás al repositorio de GitHub.
