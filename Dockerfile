FROM python:3.12-slim

# Evitar que Python genere archivos .pyc y forzar salida de logs sin buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copiar requerimientos e instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY config.py monitor_engine.py ./

# Exponer el puerto del exporter de métricas
EXPOSE 9177

# Ejecutar el motor de monitoreo
CMD ["python", "monitor_engine.py"]
