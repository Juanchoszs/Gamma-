FROM python:3.11-slim

# Crear usuario estándar para ejecutar el servicio sin privilegios
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Instalar dependencias
COPY --chown=user ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

# Copiar archivos de la aplicación
COPY --chown=user . /app

ENV HOST=0.0.0.0
# Render inyecta PORT en tiempo de ejecución; no fijarlo en la imagen.
EXPOSE 10000

CMD ["python", "run.py"]
