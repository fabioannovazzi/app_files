"""Explicit real-model acceptance; never downloads weights from a test run."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from reportlab.pdfgen.canvas import Canvas

__all__: list[str] = []


@pytest.mark.skipif(
    not os.environ.get("PRIVACY_FILTER_TEST_MODEL"),
    reason="requires explicitly prepared local model",
)
def test_real_model_filters_all_formats_through_stdio(tmp_path: Path) -> None:
    text = "My name is Alice Johnson. Email me at alice.johnson@example.com."
    source, output = tmp_path / "input", tmp_path / "output"
    source.mkdir()
    (source / "sample.txt").write_text(text)
    (source / "sample.md").write_text(text)
    with ZipFile(source / "sample.docx", "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            + text
            + "</w:t></w:r></w:p></w:body></w:document>",
        )
    canvas = Canvas(str(source / "sample.pdf"))
    canvas.drawString(20, 700, text)
    canvas.save()

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-I",
                "-m",
                "mparanza_privacy_filter.server",
                "--input-dir",
                str(source),
                "--output-dir",
                str(output),
                "--model-dir",
                os.environ["PRIVACY_FILTER_TEST_MODEL"],
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool(
                    "privacy_filter_batch",
                    {"paths": ["sample.txt", "sample.md", "sample.docx", "sample.pdf"]},
                )
                assert not response.isError
                result = json.loads(response.content[0].text)
                assert len(result["results"]) == 4
                for artifact in result["results"]:
                    assert artifact["ok"], artifact
                    filtered = await session.call_tool(
                        "privacy_filter_read", {"artifact_id": artifact["artifact_id"]}
                    )
                    assert not filtered.isError
                    rendered = json.loads(filtered.content[0].text)["redacted_text"]
                    assert "Alice Johnson" not in rendered
                    assert "alice.johnson@example.com" not in rendered
                    assert "[PRIVATE_PERSON]" in rendered
                    assert "[PRIVATE_EMAIL]" in rendered
                    assert Path(artifact["output_path"]).read_text() == rendered
                (tmp_path / "acceptance-results.json").write_text(
                    json.dumps(result, indent=2)
                )

    asyncio.run(exercise())
    assert (source / "sample.txt").read_text() == text
