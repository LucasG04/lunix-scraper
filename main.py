import asyncio
import ipaddress
import logging
import os
import re
import socket
import zlib
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from recipe_scrapers import scrape_html
from recipe_scrapers._exceptions import RecipeScrapersExceptions

API_KEYS = {v for k, v in os.environ.items() if k.startswith("API_KEY_") and v}
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_PAGE_BYTES = 5 * 1024 * 1024
FETCH_DEADLINE_SECONDS = 20  # whole download; lunix-api gives up after 30

log = logging.getLogger("uvicorn.error")


def check_api_key(x_api_key: Annotated[str | None, Header()] = None):
    if x_api_key not in API_KEYS:
        raise HTTPException(401, "Unauthorized: Invalid API key")


app = FastAPI(dependencies=[Depends(check_api_key)], docs_url=None, redoc_url=None, openapi_url=None)


async def block_private_hosts(request: httpx.Request):
    # Runs for every hop, so redirects can't reach internal addresses either.
    # raw_host = the IDNA-encoded name httpx connects to (url.host is decoded Unicode).
    host = request.url.raw_host.decode("ascii")
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    if any(not ipaddress.ip_address(info[4][0]).is_global for info in infos):
        raise HTTPException(400, "URL not allowed")


http = httpx.AsyncClient(
    follow_redirects=True,
    timeout=15,
    # identity: no compressed bodies, so MAX_PAGE_BYTES caps what is held in memory.
    headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
    event_hooks={"request": [block_private_hosts]},
)


def safe(field):
    try:
        return field() or None
    except RecipeScrapersExceptions:
        return None  # field not on the page
    except Exception:
        log.exception("recipe field %s failed", field.__name__)
        return None


def parse_int(value) -> int | None:
    """First positive number in value, half up: "1.250 kcal" / "1,250 kcal" → 1250, "304,5" → 305, "0.250" → None."""
    match = re.search(r"\d[\d.,]*", str(value or ""))
    if not match:
        return None
    number = match.group().rstrip(".,")
    if re.fullmatch(r"[1-9]\d{0,2}([.,]\d{3})+", number):  # only thousands separators
        number = re.sub(r"[.,]", "", number)
    else:  # the last separator is the decimal point: "12.345,6" → 12345.6
        whole, _, fraction = number.replace(",", ".").rpartition(".")
        number = f"{whole.replace('.', '')}.{fraction}" if whole else fraction
    return int(float(number) + 0.5) or None


def decode_html(body: bytes, header_charset: str | None) -> str:
    """Charset from Content-Type, else from <meta charset> / http-equiv, else UTF-8."""
    charset = header_charset
    if not charset:
        match = re.search(rb"""<meta[^>]+charset=["']?([\w-]+)""", body[:4096], re.IGNORECASE)
        charset = match.group(1).decode() if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:  # unknown charset name
        return body.decode("utf-8", errors="replace")


def fetch_failed(url: str, reason) -> HTTPException:
    # Generic detail: upstream status/errors would be a probing oracle. Cause goes to the log.
    log.info("fetch %s failed: %r", url, reason)
    return HTTPException(502, "Failed to fetch URL")


async def fetch_html(url: str) -> tuple[str, str]:
    """Page text and final URL (after redirects), capped in size and total time."""
    try:
        async with asyncio.timeout(FETCH_DEADLINE_SECONDS), http.stream("GET", url) as response:
            if response.is_error:
                raise fetch_failed(url, response.status_code)
            # Servers may compress despite "identity": decode raw bytes ourselves so the
            # cap bounds the *decompressed* size (no decompression bombs).
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if encoding in ("gzip", "x-gzip", "deflate"):
                decoder = zlib.decompressobj(wbits=47)  # auto-detects gzip / zlib header
            elif encoding in ("", "identity"):
                decoder = None
            else:
                raise fetch_failed(url, f"unsupported Content-Encoding {encoding}")
            body = bytearray()
            raw_bytes = 0  # capped too: data after the gzip end lands in unused_data, uncounted by body
            async for chunk in response.aiter_raw():
                raw_bytes += len(chunk)
                if decoder:
                    chunk = decoder.decompress(chunk, MAX_PAGE_BYTES + 1 - len(body))
                body += chunk
                if max(raw_bytes, len(body)) > MAX_PAGE_BYTES or (decoder and decoder.unconsumed_tail):
                    raise fetch_failed(url, "page too large")
            return decode_html(bytes(body), response.charset_encoding), str(response.url)
    except (httpx.InvalidURL, ValueError):  # malformed URL / host (incl. UnicodeError)
        raise HTTPException(400, "Invalid URL")
    except (httpx.HTTPError, OSError, zlib.error) as error:  # incl. TimeoutError, corrupt gzip
        raise fetch_failed(url, error)


def extract(html: str, url: str) -> dict | None:
    try:
        scraper = scrape_html(html, org_url=url, supported_only=False)
    except RecipeScrapersExceptions as error:
        log.info("no recipe at %s: %s", url, type(error).__name__)
        return None
    except Exception:
        log.exception("scrape_html failed for %s", url)
        return None

    groups = safe(scraper.ingredient_groups) or []
    recipe = {
        "title": safe(scraper.title),
        "totalTime": safe(scraper.total_time),
        "servings": parse_int(safe(scraper.yields)),
        "image": safe(scraper.image),
        "kcal": parse_int((safe(scraper.nutrients) or {}).get("calories")),
        "instructions": safe(scraper.instructions_list) or [],
        "ingredientGroups": [{"purpose": g.purpose, "ingredients": g.ingredients} for g in groups if g.ingredients],
    }
    return recipe if recipe["title"] and recipe["ingredientGroups"] else None


@app.get("/")
def health():
    return {"status": "UP"}


@app.get("/scrape")
async def scrape(url: str):
    try:
        scheme = urlsplit(url).scheme
    except ValueError:  # e.g. "http://[::1"
        raise HTTPException(400, "Invalid URL")
    if scheme not in ("http", "https"):
        raise HTTPException(400, "URL must be http(s)")
    html, final_url = await fetch_html(url)
    # Parsing is CPU-bound: keep it off the event loop.
    recipe = await asyncio.to_thread(extract, html, final_url)
    if not recipe:
        raise HTTPException(404, "No recipe found")
    return recipe
