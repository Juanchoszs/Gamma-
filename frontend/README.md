# Gamma React Terminal

React is the new presentation layer for the market workspace. Python remains
the source of truth for ingestion, persistence, GEX, levels, options flow and
market-intelligence APIs.

The main React surface is a deep-linkable institutional terminal. The overview
uses the `/api/v1/<symbol>/market/overlay` view model, which reuses the existing
Python GEX and options-flow engines. Dash remains available at the root while
the migration is validated.

## Development

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/terminal/`. The Vite proxy forwards `/api` to the
Python service on `http://127.0.0.1:8081`.

Useful deep links include `/terminal/map?symbol=SPY&bucket=ALL` and
`/terminal/?symbol=SPY&bucket=ALL&flow=CALLS`. Symbols, expiration buckets and
overlay filters are kept in the URL for sharing and back/forward navigation.

## Production build

```bash
cd frontend
npm run build
```

Frontend contract tests:

```bash
cd frontend
npm test
```

The Python service serves the compiled terminal at
`http://127.0.0.1:8081/terminal/`. The legacy Dash workspace remains available
at the root while the migration is validated.
