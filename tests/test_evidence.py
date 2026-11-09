from types import SimpleNamespace
from unittest.mock import Mock
import pymupdf
import pytest
from PIL import Image
from app.ai.provider import LocalProvider, OpenAIProvider
from app.db import Document
from app.documents import pages, process, preview
from app.schemas import Extraction, Fact


def test_reject_unanchored_values(tmp_path, monkeypatch):
    monkeypatch.setattr("app.documents.STATE", tmp_path)
    doc = Document(id="generated", mime="application/pdf")
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((20, 40), "Claim Form: Missing date")
        pdf.save(tmp_path / "generated.upload")
    fake = Mock(spec=LocalProvider, model="fixture")
    fake.extract.return_value = Extraction(
        kind="CLAIM_FORM",
        facts=[Fact(name="incident_date", value="2026-01-01", quote="Claim Form: Missing date")],
    )
    db = Mock()
    process(db, doc, fake)
    db.add.assert_not_called()
    assert preview(doc, 1).startswith(b"\x89PNG")
    assert doc.status == "READY"


def test_mixed_pdf_calls_ocr_only_for_scanned_page(monkeypatch, tmp_path):
    monkeypatch.setattr("app.documents.STATE", tmp_path)
    ocr = Mock(return_value="Scanned evidence")
    monkeypatch.setattr("app.documents.pytesseract.image_to_string", ocr)
    doc = Document(id="scan", mime="application/pdf")
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((40, 50), "First page")
        pdf.new_page()
        pdf.save(tmp_path / "scan.upload")
    text, scanned = pages(doc)
    assert scanned == [2] and text[1] == "Scanned evidence"
    ocr.assert_called_once()
    Image.new("RGB", (50, 50)).save(tmp_path / "photo.upload", "JPEG")
    assert pages(Document(id="photo", mime="image/jpeg")) == (["Scanned evidence"], [1])


def test_openai_provider_contract(monkeypatch):
    client = Mock()
    monkeypatch.setattr("app.ai.provider.OpenAI", lambda **kwargs: client)
    ai = OpenAIProvider()
    client.responses.parse.return_value.output_parsed = Extraction(kind="OTHER", facts=[])
    result = ai.extract("Untrusted input")
    assert result.facts == []
    args = client.responses.parse.call_args.kwargs
    assert args["store"] is False and args["text_format"] is Extraction
    client.responses.create.return_value.output = [
        SimpleNamespace(type="function_call", name="unlisted", arguments="{}")
    ]
    with pytest.raises(ValueError):
        ai.call("search_policy")
