from __future__ import annotations

from pathlib import Path

from modules.slides import pptx_jobs, print_jobs


def test_print_jobs_mark_interrupted_pending_and_running_jobs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        print_jobs,
        "_STORE",
        print_jobs.JsonRecordStore(tmp_path / "print_jobs.json"),
    )

    print_jobs.create_job("pending-job", "deck-1")
    print_jobs.create_job("running-job", "deck-1")
    print_jobs.update_job_status("running-job", "running")

    interrupted_count = print_jobs.mark_interrupted_jobs()
    pending_job = print_jobs.get_job("pending-job")
    running_job = print_jobs.get_job("running-job")

    assert interrupted_count == 2
    assert pending_job is not None
    assert pending_job.status == "failed"
    assert (
        pending_job.detail
        == "PDF export interrupted by server restart. Please run it again."
    )
    assert running_job is not None
    assert running_job.status == "failed"


def test_pptx_jobs_mark_interrupted_pending_and_running_jobs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        pptx_jobs,
        "_STORE",
        pptx_jobs.JsonRecordStore(tmp_path / "pptx_jobs.json"),
    )

    pptx_jobs.create_job("pending-job", "deck-1")
    pptx_jobs.create_job("running-job", "deck-1")
    pptx_jobs.update_job_status("running-job", "running")

    interrupted_count = pptx_jobs.mark_interrupted_jobs()
    pending_job = pptx_jobs.get_job("pending-job")
    running_job = pptx_jobs.get_job("running-job")

    assert interrupted_count == 2
    assert pending_job is not None
    assert pending_job.status == "failed"
    assert (
        pending_job.detail
        == "PPTX export interrupted by server restart. Please run it again."
    )
    assert running_job is not None
    assert running_job.status == "failed"
