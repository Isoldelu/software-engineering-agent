from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def test_step31_interview_deck_delivery_is_complete():
    required = (
        "docs/Software-Agent-Interview-Deck.pptx",
        "docs/interview-deck-script.md",
        "docs/deck/build_interview_deck.mjs",
        "docs/assets/interview-deck-preview.png",
    )
    assert all((ROOT / path).is_file() for path in required)
    assert (ROOT / required[0]).stat().st_size > 100_000
    assert (ROOT / required[3]).stat().st_size > 100_000


def test_step31_deck_has_five_slides_and_source_notes():
    deck = ROOT / "docs" / "Software-Agent-Interview-Deck.pptx"
    with ZipFile(deck) as archive:
        names = archive.namelist()
        textual_payload = b"\n".join(
            archive.read(name)
            for name in names
            if name.endswith((".xml", ".rels"))
        )
        slides = [
            name
            for name in names
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
        notes = [
            name
            for name in names
            if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml")
        ]
    assert len(slides) == 5
    assert len(notes) == 5
    assert b"D:\\" not in textual_payload
    assert b"C:\\Users\\44486" not in textual_payload
    assert b"/Users/44486" not in textual_payload
    assert b".codex" not in textual_payload
    assert b"33314875879" in textual_payload
    assert b"138" in textual_payload

    builder = (ROOT / "docs" / "deck" / "build_interview_deck.mjs").read_text(
        encoding="utf-8"
    )
    assert 'from "@oai/artifact-tool"' in builder
    assert "PresentationFile.exportPptx" in builder
    assert "speakerNotes" in builder
    assert "[Sources]" in builder
    assert "python-pptx" not in builder


def test_step31_script_preserves_compliance_and_evaluation_boundaries():
    script = (ROOT / "docs" / "interview-deck-script.md").read_text(
        encoding="utf-8"
    )
    assert "公开风格模拟数据" in script
    assert "不包含华为内部数据" in script
    assert "离线可复现基线" in script
    assert "不代表真实商业模型 A/B" in script
    assert "不会自动修改源码" in script
    assert "138 项自动化测试" in script
    assert "193 条冻结评测" in script
