"""Measure a five-user read workload and verify actual Tesseract output over HTTP."""

import io
import json
import os
import secrets
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

import httpx
import pymupdf
from PIL import Image, ImageDraw, ImageFont

BASE = os.getenv("E2E_URL", "http://127.0.0.1:8080") + "/api/v1"
CLAIM = {
    "claimant_name": "Synthetic Review",
    "policy_number": "SYN-QA",
    "incident_date": "2026-02-01",
    "claim_amount": "125",
    "currency": "USD",
    "incident_description": "Vehicle collision damage",
}


def authenticated():
    client = httpx.Client(base_url=BASE, timeout=20)
    credentials = {
        "email": f"smoke-{secrets.token_hex(8)}@example.invalid",
        "password": secrets.token_urlsafe(24),
    }
    client.post("/auth/register", json=credentials).raise_for_status()
    response = client.post("/auth/login", json=credentials)
    response.raise_for_status()
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    return client


def measured_user(client, barrier):
    route = "/claims/" + client.post("/claims", json=CLAIM).raise_for_status().json()["id"]
    values = []
    try:
        barrier.wait(timeout=15)
        for _ in range(10):
            for path in ("/claims", "/dashboard", route, route + "/documents"):
                start = time.perf_counter()
                client.get(path).raise_for_status()
                values.append((time.perf_counter() - start) * 1000)
    finally:
        client.delete(route).raise_for_status()
        client.post("/auth/logout").raise_for_status()
        client.close()
    return values


def ocr_check():
    image = Image.new("RGB", (1400, 240), "white")
    ImageDraw.Draw(image).multiline_text(
        (40, 25),
        "Police Report\nIncident Date: 2026-02-01",
        fill="black",
        font=ImageFont.load_default(size=48),
        spacing=16,
    )
    stream = io.BytesIO()
    image.save(stream, "PNG")
    png = stream.getvalue()
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=700, height=120)
        page.insert_image(page.rect, stream=png)
        scan = pdf.tobytes()
    with closing(authenticated()) as client:
        route = "/claims/" + client.post("/claims", json=CLAIM).raise_for_status().json()["id"]
        client.post(
            route + "/documents", files={"file": ("scan.pdf", scan, "application/pdf")}
        ).raise_for_status()
        client.post(
            route + "/documents", files={"file": ("image.png", png, "image/png")}
        ).raise_for_status()
        end = time.monotonic() + 90
        while time.monotonic() < end:
            docs = client.get(route + "/documents").raise_for_status().json()
            if all(d["status"] != "QUEUED" for d in docs):
                break
            time.sleep(0.5)
        assert len(docs) == 2 and all(
            d["status"] == "READY" and d["metadata_json"]["ocr_pages"] == [1] for d in docs
        ), docs
        facts = client.get(route).raise_for_status().json()["fields"]
        assert {
            f["filename"] for f in facts if f["name"] == "incident_date" and f["value"] == "2026-02-01"
        } == {"scan.pdf", "image.png"}
        client.delete(route).raise_for_status()
        client.post("/auth/logout").raise_for_status()


if __name__ == "__main__":
    ocr_check()
    clients = [authenticated() for _ in range(5)]
    barrier = Barrier(5)
    with ThreadPoolExecutor(max_workers=5) as pool:
        times = [
            sample
            for group in pool.map(lambda c: measured_user(c, barrier), clients)
            for sample in group
        ]
    p95 = statistics.quantiles(times, n=100, method="inclusive")[94]
    print(
        json.dumps(
            {"concurrent_users": 5, "requests": len(times), "p95_ms": round(p95, 1), "ocr_documents": 2}
        )
    )
    assert p95 < 1000
