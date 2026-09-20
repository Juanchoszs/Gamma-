FROM node:22-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar aplicación y el terminal React compilado. El dist no se versiona ni
# se incluye en el contexto Docker: se construye en la etapa anterior.
COPY . .
COPY --from=frontend-build /frontend/dist ./frontend/dist

# La aplicación escribe snapshots y logs. El volumen Fly se monta en /data,
# así que el proceso no debe ejecutarse como root.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

# Exponer puerto
EXPOSE 8050

# Variable de entorno para producción
ENV PYTHONUNBUFFERED=1 \
    GEX_DATA_DIR=/data

USER appuser

# Comando de inicio
CMD ["python", "run.py"]
