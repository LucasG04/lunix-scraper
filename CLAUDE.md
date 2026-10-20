# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
API_KEY_DEV=123 .venv/bin/uvicorn main:app --port 3000 --reload
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest
```

Tests (`test_main.py`) are offline: `main.http` is swapped for an `httpx.MockTransport` client (responses must use `stream=`, `fetch_html` reads `aiter_raw`); public IP literals like `1.1.1.1` pass the SSRF guard without DNS. No lint configured.

CI (`.github/workflows/ci.yml`, every PR incl. Renovate): builds the production image, runs pytest inside it, smoke-tests `GET /`. Read-only token, no secrets, no `pull_request_target`.

## Architecture

Single-file FastAPI service (`main.py`) that fetches a recipe page and extracts it with [recipe-scrapers](https://docs.recipe-scrapers.com/). Called only by lunix-api (`fetchScrapedRecipe` in `lunix-api/src/foodly/import.ts`).

- `GET /scrape?url=<recipe-url>` with `x-api-key` → `{ title, totalTime, servings, image, kcal, instructions: string[], ingredientGroups: [{ purpose, ingredients: string[] }] }`. Ingredients are raw lines; lunix-api parses them into amount/unit/name.
- `scrape_html(..., supported_only=False)`: site-specific scraper for the ~740 supported hosts, generic schema.org fallback for everything else.
- Errors: 400 bad/blocked URL, 502 fetch failed, 404 no recipe (no title or no ingredients).
- `block_private_hosts` (httpx request hook, runs on every redirect hop) rejects non-public IPs (SSRF guard); resolves `raw_host` (IDNA-encoded, what httpx connects to). Not DNS-rebinding safe (accepted).
- Fetch limits: 5 MB body, 20 s total (`MAX_PAGE_BYTES`, `FETCH_DEADLINE_SECONDS`); parsing runs in a thread (`asyncio.to_thread`); `Accept-Encoding: identity`; servers that compress anyway: gzip/deflate decoded with a bounded zlib decoder (cap = decompressed size), other encodings rejected. Charset: Content-Type, else `<meta charset>`, else UTF-8. 502 details stay generic, causes are logged.
- API keys = all non-empty `API_KEY_*` env vars, read at startup (restart to add keys). Applies to every route, incl. health `GET /`.

### Environment variables

| Variable    | Purpose                                                                    |
| ----------- | -------------------------------------------------------------------------- |
| `API_KEY_*` | One or more API keys for authenticating requests (e.g. `API_KEY_TEST=abc`) |
| `PORT`      | Server port in Docker (default: 3000)                                      |

### Deployment

Pushes to `main` trigger a GitHub Actions workflow that builds and pushes a multi-arch Docker image (`linux/amd64`, `linux/arm64`) to `ghcr.io/lucasg04/lunix-scraper:latest`.
