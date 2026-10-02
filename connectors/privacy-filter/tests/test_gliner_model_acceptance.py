"""Opt-in local GLiNER2 acceptance through the actual stdio MCP protocol."""

from __future__ import annotations

import asyncio
import hashlib
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
    not os.environ.get("GLINER2_TEST_MODEL"),
    reason="requires explicitly prepared local GLiNER2 model",
)
def test_real_gliner_model_filters_four_formats_and_long_text(tmp_path: Path) -> None:
    text = "La cliente si chiama Maria Verdi. Email personale: maria.verdi@example.com."
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
    (source / "long.txt").write_text(
        "Il rapporto descrive le attivita dello studio. " * 90 + text
    )
    paths = ["sample.txt", "sample.md", "sample.docx", "sample.pdf", "long.txt"]
    original_hashes = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in paths
    }

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-I",
                "-m",
                "mparanza_privacy_filter.server",
                "--engine",
                "gliner2",
                "--input-dir",
                str(source),
                "--output-dir",
                str(output),
                "--model-dir",
                os.environ["GLINER2_TEST_MODEL"],
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.call_tool(
                    "gliner2_pii_batch", {"paths": paths}
                )
                assert not response.isError
                result = json.loads(response.content[0].text)
                assert len(result["results"]) == 5
                for artifact in result["results"]:
                    assert artifact["ok"], artifact
                    assert artifact["engine"] == "gliner2"
                    filtered = await session.call_tool(
                        "gliner2_pii_read", {"artifact_id": artifact["artifact_id"]}
                    )
                    assert not filtered.isError
                    rendered = json.loads(filtered.content[0].text)["redacted_text"]
                    assert "Maria Verdi" not in rendered
                    assert "maria.verdi@example.com" not in rendered
                    assert "[EMAIL]" in rendered
                    assert Path(artifact["output_path"]).read_text() == rendered
                (tmp_path / "acceptance-results.json").write_text(
                    json.dumps(result, indent=2)
                )

    asyncio.run(exercise())
    assert {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in paths
    } == original_hashes
