"""Exercise upload isolation, browser media seeking, and local app lifecycle."""

import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from rallycut.local_app import AppServer, JobManager, atomic_json, byte_range


@pytest.fixture
def app(tmp_path):
    manager = JobManager(tmp_path, start_worker=False)
    server = AppServer(("127.0.0.1", 0), tmp_path, manager)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, manager, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    manager.close()
    server.server_close()
    thread.join(timeout=5)


def request(app, path, *, data=None, method=None, headers=None):
    server, _, base = app
    headers = {"X-RallyCut-Token": server.token, **(headers or {})}
    return urlopen(Request(base + path, data=data, method=method, headers=headers), timeout=5)


def upload(app, name="测试 发球.mp4", content=b"example video bytes"):
    with request(app, "/api/jobs", data=content, headers={
        "Content-Type": "application/octet-stream", "X-File-Name": quote(name),
    }) as response:
        assert response.status == 202
        return json.load(response)


def test_upload_uses_private_path_and_preserves_display_name(app):
    job = upload(app, "../某个 训练.mp4")
    manager = app[1]
    directory = manager.directory / job["id"]
    assert job["filename"] == "某个 训练.mp4"
    assert (directory / "source.mp4").read_bytes() == b"example video bytes"
    assert not (directory / "upload.part").exists()
    assert manager.snapshot(job["id"])["state"] == "queued"
    assert len(manager.list_jobs()) == 1


def test_external_origin_and_missing_token_cannot_create_job(app):
    for headers in ({"Origin": "https://unrelated.example"}, {"X-RallyCut-Token": "wrong"}):
        with pytest.raises(HTTPError) as caught:
            request(app, "/api/jobs", data=b"abc", headers=headers)
        assert caught.value.code == 403
    assert app[1].list_jobs() == []


def test_dns_rebinding_host_is_rejected(app):
    with pytest.raises(HTTPError) as caught:
        request(app, "/api/config", headers={"Host": "unrelated.example"})
    assert caught.value.code == 403


def test_invalid_upload_is_rejected_before_enqueue(app):
    with pytest.raises(HTTPError) as caught:
        upload(app, "run.exe")
    assert caught.value.code == 400
    assert app[1].list_jobs() == []


def test_media_seek_ranges_and_download(app):
    job = upload(app)
    manager = app[1]
    directory = manager.directory / job["id"]
    (directory / "media.mp4").write_bytes(b"0123456789")
    atomic_json(directory / "result.json", {"rallies": []})
    manager.jobs[job["id"]]["state"] = "completed"
    with request(app, f"/api/jobs/{job['id']}/media", headers={"Range": "bytes=3-6"}) as response:
        assert response.status == 206
        assert response.headers["Content-Range"] == "bytes 3-6/10"
        assert response.read() == b"3456"
    with request(app, f"/api/jobs/{job['id']}/media", headers={"Range": "bytes=-3"}) as response:
        assert response.read() == b"789"
    with pytest.raises(HTTPError) as caught:
        request(app, f"/api/jobs/{job['id']}/media", headers={"Range": "bytes=15-"})
    assert caught.value.code == 416
    with request(app, f"/api/jobs/{job['id']}/download") as response:
        assert "attachment" in response.headers["Content-Disposition"]
        assert json.load(response) == {"rallies": []}


def test_cancel_then_delete_never_deletes_original(app, tmp_path):
    original = tmp_path / "original.mp4"
    original.write_bytes(b"untouched")
    job = upload(app)
    base = f"/api/jobs/{job['id']}"
    with pytest.raises(HTTPError) as caught:
        request(app, base, method="DELETE")
    assert caught.value.code == 409
    with request(app, base + "/cancel", data=b"") as response:
        assert json.load(response)["state"] == "cancelled"
    with request(app, base, method="DELETE") as response:
        assert json.load(response)["deleted"] is True
    assert original.read_bytes() == b"untouched"
    assert not (app[1].directory / job["id"]).exists()


def test_interrupted_job_is_not_silently_treated_as_complete(tmp_path):
    job_id = "a" * 32
    directory = tmp_path / "data/jobs" / job_id
    directory.mkdir(parents=True)
    atomic_json(directory / "job.json",
                {"id": job_id, "state": "running", "filename": "old.mp4", "created_at": 1})
    manager = JobManager(tmp_path, start_worker=False)
    assert manager.snapshot(job_id)["state"] == "failed"
    assert "中断" in manager.snapshot(job_id)["message"]


@pytest.mark.parametrize("value", ["bytes=7-2", "bytes=-0", "items=0-1", "bytes=0-1,3-4"])
def test_invalid_seek_ranges(value):
    with pytest.raises(ValueError):
        byte_range(value, 10)
