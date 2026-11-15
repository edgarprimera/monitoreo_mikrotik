FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copiar paquetes pre-descargados e instalar de forma 100% local y offline
COPY wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels

# Copiar el código de la aplicación
COPY config.py monitor_engine.py telegram_reporter.py ./

# Exponer el puerto del exporter de métricas
EXPOSE 9177

# Ejecutar el motor de monitoreo
CMD ["python", "monitor_engine.py"]
