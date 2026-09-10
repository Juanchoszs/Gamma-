FROM python:3.11-slim

# Crear usuario estándar y los directorios escribibles antes de cambiar de
# usuario.
RUN useradd -m -u 1000 user && mkdir -p /data /app/logs && chown -R user:user /data /app
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Copiar archivos de la aplicación
COPY --chown=user . /app

ENV HOST=0.0.0.0
ENV GEX_DATA_DIR=/data
# El proveedor inyecta PORT en tiempo de ejecución; no fijarlo en la imagen.
EXPOSE 10000

# Instalar el proyecto desde pyproject.toml para mantener una única fuente
# de dependencias entre local, CI y producción.
RUN pip install --no-cache-dir --user .

CMD ["python", "run.py"]
