from __future__ import annotations

import pytest

from scripts.build_vera_local_video_guides import partition_narration_scenes


def test_partition_narration_scenes_preserves_complete_sentences() -> None:
    narration = "One. Two. Three. Four. Five. Six."

    scenes = partition_narration_scenes(narration, 6)

    assert scenes == ["One.", "Two.", "Three.", "Four.", "Five.", "Six."]


@pytest.mark.parametrize(
    "narration",
    (
        "One. Two. Three. Four. Five.",
        "One. Two. Three. Four. Five. Six",
    ),
)
def test_partition_narration_scenes_without_six_complete_sentences_raises(
    narration: str,
) -> None:
    with pytest.raises(ValueError, match="complete sentence|terminal punctuation"):
        partition_narration_scenes(narration, 6)
