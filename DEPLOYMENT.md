# Despliegue en producción

El dashboard es un servicio Python de larga duración: mantiene el proceso Dash,
ejecuta tareas programadas y, si está configurado, mantiene conexiones
WebSocket con dxLink/Tastytrade. Por eso debe desplegarse como **servicio
Docker/VM**, no como una función serverless.

## Opción recomendada

Usa cualquier proveedor que soporte:

1. Despliegue desde `Dockerfile`.
2. Un volumen persistente montado en `/data`.
3. Variables de entorno secretas.
4. Conexiones WebSocket salientes.

Railway y Fly.io cumplen estos requisitos. También se puede usar cualquier VM
con Docker. El proveedor no necesita conocer las credenciales de Tastytrade.

## Pasos

1. Crea un servicio a partir del repositorio y selecciona el `Dockerfile`.
2. Configura un volumen persistente en `/data`.
3. Define estas variables, sin comillas:

   ```text
   TASTYTRADE_CLIENT_ID=...
   TASTYTRADE_CLIENT_SECRET=...
   TT_REFRESH=...
   TASTYTRADE_REDIRECT_URI=https://TU_DOMINIO/oauth/callback
   GEX_DATA_DIR=/data
   ```

   `DXFEED_AUTH_TOKEN` puede usarse como alternativa al flujo OAuth de
   Tastytrade. No configures ambos a menos que sepas cuál debe tener prioridad.

4. Configura el puerto público del proveedor con el valor interno que inyecte
   en `PORT`. El contenedor escucha en `0.0.0.0`.
5. Registra **exactamente** la misma
   `TASTYTRADE_REDIRECT_URI` en la aplicación OAuth de Tastytrade. El esquema,
   dominio, ruta y barras finales deben coincidir.
6. Espera a que `https://TU_DOMINIO/healthz` responda:

   ```json
   {"service":"gex-dashboard","status":"ok"}
   ```

   Este endpoint solo verifica que el proceso web está vivo; no marca como
   fallido el servicio si Tastytrade está temporalmente desconectado.
7. Abre el dashboard y conecta Tastytrade desde la interfaz. Si el proveedor
   cambia el dominio público, actualiza primero la URI registrada en Tastytrade
   y después `TASTYTRADE_REDIRECT_URI`.

## Comprobaciones de diagnóstico

- `GET /healthz`: proceso web y puerto.
- `GET /api/v1/tastytrade/status`: estado de credenciales y conexión, sin
  revelar secretos.
- Los archivos de `data/` deben estar en el volumen `/data`; sin volumen se
  perderán al reiniciar o redeplegar.

No subas `.env`, `TT_REFRESH`, `TASTYTRADE_CLIENT_SECRET` ni tokens de dxFeed al
repositorio. Usa el gestor de secretos del proveedor.
