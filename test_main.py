import gzip
import json
import os

os.environ["API_KEY_TEST"] = "test"  # read at import

import httpx
import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app, headers={"x-api-key": "test"})
PAGE = "http://1.1.1.1/recipe"  # public IP literal: SSRF guard passes without DNS

RECIPE = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Pancakes",
    "totalTime": "PT25M",
    "recipeYield": "4 servings",
    "image": "https://img.example/pancakes.jpg",
    "nutrition": {"@type": "NutritionInformation", "calories": "1.250 kcal"},
    "recipeIngredient": ["200 g flour", "2 eggs", "300 ml milk"],
    "recipeInstructions": [
        {"@type": "HowToStep", "text": "Mix everything."},
        {"@type": "HowToStep", "text": "Fry in a pan."},
    ],
}
RECIPE_HTML = f'<html><head><script type="application/ld+json">{json.dumps(RECIPE)}</script></head><body></body></html>'


@pytest.fixture
def serve(monkeypatch):
    """Route main.http to a handler instead of the network; keeps the real headers and SSRF hook."""

    def install(handler):
        mock = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
            headers=main.http.headers,
            event_hooks=main.http.event_hooks,
        )
        monkeypatch.setattr(main, "http", mock)

    return install


def page(body=RECIPE_HTML, status=200, **headers):
    """Streamed response: main reads it via aiter_raw, which a content= response doesn't allow."""
    data = body.encode() if isinstance(body, str) else body
    headers = {"content-type": "text/html; charset=utf-8", **{k.replace("_", "-"): v for k, v in headers.items()}}
    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(data))


def scrape(url=PAGE):
    return client.get("/scrape", params={"url": url})


def test_rejects_missing_or_wrong_api_key():
    assert TestClient(main.app).get("/").status_code == 401
    assert TestClient(main.app, headers={"x-api-key": "nope"}).get("/").status_code == 401


def test_health():
    assert client.get("/").json() == {"status": "UP"}


def test_extracts_schema_org_recipe(serve):
    serve(lambda request: page())
    response = scrape()
    assert response.status_code == 200
    assert response.json() == {
        "title": "Pancakes",
        "totalTime": 25,
        "servings": 4,
        "image": "https://img.example/pancakes.jpg",
        "kcal": 1250,
        "instructions": ["Mix everything.", "Fry in a pan."],
        "ingredientGroups": [{"purpose": None, "ingredients": ["200 g flour", "2 eggs", "300 ml milk"]}],
    }


def test_sends_identity_encoding_and_user_agent(serve):
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return page()

    serve(handler)
    scrape()
    assert seen["accept-encoding"] == "identity"
    assert seen["user-agent"] == main.USER_AGENT


def test_decodes_gzip_despite_identity(serve):
    serve(lambda request: page(gzip.compress(RECIPE_HTML.encode()), content_encoding="gzip"))
    assert scrape().json()["title"] == "Pancakes"


def test_rejects_gzip_bomb(serve):
    serve(lambda request: page(gzip.compress(b"\0" * (main.MAX_PAGE_BYTES + 1)), content_encoding="gzip"))
    assert scrape().status_code == 502


def test_rejects_oversized_page(serve):
    serve(lambda request: page(b"a" * (main.MAX_PAGE_BYTES + 1)))
    assert scrape().status_code == 502


def test_rejects_unsupported_encoding(serve):
    serve(lambda request: page(b"x", content_encoding="br"))
    assert scrape().status_code == 502


def test_upstream_error_is_502_with_generic_detail(serve):
    serve(lambda request: httpx.Response(404))
    response = scrape()
    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to fetch URL"}


def test_page_without_recipe_is_404(serve):
    serve(lambda request: page("<html><body>hello</body></html>"))
    assert scrape().status_code == 404


def test_follows_redirect_and_uses_final_url(serve):
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": PAGE})
        return page()

    serve(handler)
    assert scrape("http://1.1.1.1/old").json()["title"] == "Pancakes"


def test_blocks_redirect_to_private_host(serve):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    serve(handler)
    assert scrape().status_code == 400
    assert requested == [PAGE]  # the private hop never reached the transport


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.1/", "http://[::1]/", "http://169.254.169.254/"])
def test_blocks_private_hosts(url):
    assert scrape(url).status_code == 400


@pytest.mark.parametrize("url", ["ftp://1.1.1.1/", "file:///etc/passwd", "http://[::1", "not a url"])
def test_rejects_bad_urls(url):
    assert scrape(url).status_code == 400


@pytest.mark.parametrize(
    "value, expected",
    [
        ("4 servings", 4),
        ("1.250 kcal", 1250),
        ("1,250 kcal", 1250),
        ("304,5", 305),
        ("12.345,6", 12346),
        ("0.250", None),
        ("none", None),
        (None, None),
    ],
)
def test_parse_int(value, expected):
    assert main.parse_int(value) == expected


def test_decode_html_charset():
    latin = "<p>Käse</p>".encode("latin-1")
    assert main.decode_html(latin, "latin-1") == "<p>Käse</p>"
    assert "Käse" in main.decode_html(b'<meta charset="iso-8859-1">' + latin, None)
    assert main.decode_html("Käse".encode(), None) == "Käse"
    assert main.decode_html(b"x", "no-such-charset") == "x"
