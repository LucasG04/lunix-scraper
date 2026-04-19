# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the server (uses bun for direct TypeScript execution, no build step needed)
npm start  # runs: bun run src/server.ts

# Type-check without running
npx tsc --noEmit
```

There are no tests and no lint scripts configured.

## Architecture

This is an Express HTTP server that scrapes recipe data from ninja kitchen websites and parses it into a structured format.

### Request flow

1. Client sends `GET /scrape-ninja?url=<recipe-url>` with an `x-api-key` header
2. `apiKeyAuthMiddleware` in `src/middleware.ts` validates the key against all env vars prefixed `API_KEY_` (loaded at startup via `fetchAllApiKeys`)
3. `src/server.ts` fetches the URL directly with `fetch()` using a browser User-Agent, then loads the HTML into Cheerio
4. `processNinjaCheerio` in `src/scrapers/ninja-scraper.ts` extracts title, total time, servings, ingredients, steps, and image from the Cheerio-loaded DOM
5. Each raw ingredient string is sent to OpenAI via `parseIngredientByChatGPT` to parse it into `{ amount, unit, name }`

### Key design details

- The `openai` client is a lazy singleton exported as `openai()` from `src/openai.ts` and imported by `src/utils/parse-ingredients.ts`.
- Only metric ingredients are scraped (selector `[data-unit="metric"]`); a regex-based parser (`parseIngredientByRegex`) exists in the file but is commented out in favor of GPT parsing.
- API keys are loaded once at startup; adding new `API_KEY_*` env vars requires a server restart.

### Environment variables

| Variable         | Purpose                                                                    |
| ---------------- | -------------------------------------------------------------------------- |
| `OPENAI_API_KEY` | OpenAI API key for ingredient parsing                                      |
| `API_KEY_*`      | One or more API keys for authenticating requests (e.g. `API_KEY_TEST=abc`) |
| `PORT`           | Server port (default: 3000)                                                |

### Deployment

Pushes to `main` trigger a GitHub Actions workflow that builds and pushes a multi-arch Docker image (`linux/amd64`, `linux/arm64`) to `ghcr.io/lucasg04/lunix-scraper:latest`.
