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

## Verificación manual con Postman

Esta prueba valida directamente el `refresh_token`, sin pasar por Render.
Postman debe ejecutarse en tu equipo y las credenciales deben introducirse
como variables locales o temporales; no guardes valores reales en una
colección compartida.

1. Crea una petición nueva con método **POST**:

   ```text
   https://api.tastyworks.com/oauth/token
   ```

2. En **Headers** añade:

   | Key | Value |
   | --- | --- |
   | `User-Agent` | `gex-postman/1.0` |
   | `Content-Type` | `application/json` |

3. En **Body → raw → JSON** introduce:

   ```json
   {
     "grant_type": "refresh_token",
     "refresh_token": "{{TT_REFRESH}}",
     "client_secret": "{{TASTYTRADE_CLIENT_SECRET}}"
   }
   ```

4. Define en el entorno local de Postman estas variables:

   ```text
   TT_REFRESH
   TASTYTRADE_CLIENT_SECRET
   ```

   Usa el icono de ojo para confirmar que Postman está usando el valor
   activo. No incluyas `TASTYTRADE_CLIENT_ID` en esta petición: Tastytrade
   documenta `client_id` como opcional para renovar un grant y el servidor lo
   infiere del refresh token.

5. Pulsa **Send**. Una renovación correcta devuelve `200 OK` y un JSON con
   `access_token`, `token_type` y `expires_in`. No guardes ni compartas el
   `access_token`.

6. Si devuelve `400` con `invalid_grant` / `Invalid JWT`, el refresh token no
   es válido para Tastytrade (grant eliminado, secreto regenerado, token
   truncado o valor pegado con comillas/espacios). Crea un grant nuevo y
   repite la prueba.

7. Si devuelve `200`, Render no debe usar valores distintos. Copia los mismos
   valores exactos a sus variables `TT_REFRESH` y
   `TASTYTRADE_CLIENT_SECRET`, guarda y ejecuta un redeploy.

Para verificar el servicio web por separado, crea otra petición **GET** a:

```text
https://TU_DOMINIO/healthz
```

Debe devolver `200 OK`:

```json
{"service":"gex-dashboard","status":"ok"}
```
