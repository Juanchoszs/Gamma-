# Deploy on Fly.io

This service publishes the React terminal at `/terminal/` and keeps Dash at
`/` as the fallback. The Docker image builds the React app itself, so the
ignored `frontend/dist` directory is never required in Git.

## Before the first deploy

1. Install and authenticate the Fly CLI:

   ```sh
   brew install flyctl
   fly auth login
   ```

2. Create the app only if `gamma-analytics` is not already owned by your Fly
   organization. Pick an available name and update `app` in `fly.toml`:

   ```sh
   fly launch --no-deploy
   ```

3. Create the persistent volume in the same region configured in `fly.toml`:

   ```sh
   fly volumes create gamma_data --app gamma-analytics --region iad --size 10
   ```

4. Register the production redirect URI in the Tastytrade OAuth application
   only if you intend to use OAuth renewal. Shared production disables the
   browser OAuth routes; the normal deployment authenticates with the refresh
   token set below.

## Set server-only secrets

Run this command in a terminal. It reads values interactively so they never
appear in shell history, Git, screenshots, browser code, or frontend bundles.

```sh
read -s 'TASTYTRADE_CLIENT_ID?Tastytrade client ID: '; echo
read -s 'TASTYTRADE_CLIENT_SECRET?Tastytrade client secret: '; echo
read -s 'TT_REFRESH?Tastytrade refresh token: '; echo
fly secrets set \
  TASTYTRADE_CLIENT_ID="$TASTYTRADE_CLIENT_ID" \
  TASTYTRADE_CLIENT_SECRET="$TASTYTRADE_CLIENT_SECRET" \
  TT_REFRESH="$TT_REFRESH" \
  --app gamma-analytics
unset TASTYTRADE_CLIENT_ID TASTYTRADE_CLIENT_SECRET TT_REFRESH
```

`GEX_SHARED_DEPLOYMENT=true` is intentionally a plain Fly environment value:
it disables all routes and UI callbacks that could replace or reveal the
server's broker credentials. Users need no environment variables.

## Deploy and verify

```sh
fly deploy --config fly.toml
fly checks list --app gamma-analytics
fly logs --app gamma-analytics
fly open --app gamma-analytics
```

Check `https://<your-app>.fly.dev/healthz` and then open
`https://<your-app>.fly.dev/terminal/`.

Do not set broker credentials in `VITE_*` variables, `fly.toml`, `.env.example`,
or GitHub Actions. Fly injects secrets only into the running server process.

## Operational note

A shared terminal redistributes data obtained with one broker account. Confirm
the Tastytrade and dxFeed account terms permit this audience and usage before
making the URL public. Keep the app restricted until that is confirmed.
