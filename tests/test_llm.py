import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from rallycut.llm import call_prepared, parse_response, reconcile_windows


def interval(a, b):
    return {"start_seconds": a, "end_seconds": b}


def test_window_does_not_accept_relative_times_as_absolute():
    with pytest.raises(ValueError, match="outside"):
        parse_response(json.dumps({"rallies": [interval(0, 7)]}), 50, 100)


def test_model_must_return_valid_nonoverlapping_finite_times():
    with pytest.raises(ValueError):
        parse_response('{"rallies":[{"start_seconds":1,"end_seconds":NaN}]}', 0, 20)


def test_fenced_json_is_accepted_but_marked_for_review():
    result, _ = parse_response('```json\n{"rallies":[{"start_seconds":1,"end_seconds":7}]}\n```', 0, 20)
    assert result[0]["needs_review"]


def test_unordered_nonoverlapping_model_output_is_sorted_without_new_cuts():
    rows=[interval(8,9),interval(1,4)]
    result,limitations=parse_response(json.dumps({'rallies':rows}),0,10)
    assert [(r['start_seconds'],r['end_seconds']) for r in result]==[(1,4),(8,9)]
    assert limitations and 'sorted' in limitations[0]


def test_overlapping_windows_merge_continuing_rally_but_not_adjacent_rallies():
    result = reconcile_windows([[interval(0, 8), interval(10, 20)], [interval(12, 25), interval(25, 28)]])
    assert [(r["start_seconds"], r["end_seconds"]) for r in result] == [(0, 8), (10, 25), (25, 28)]


def test_ambiguous_window_conflict_is_visible():
    with pytest.raises(ValueError, match="overlapping"):
        reconcile_windows([[interval(0, 10)], [interval(9, 20)]])


def test_unconfigured_service_is_not_reported_as_inferred(monkeypatch, tmp_path):
    monkeypatch.delenv("RALLYCUT_VLM_URL", raising=False)
    monkeypatch.delenv("RALLYCUT_VLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="Set RALLYCUT"):
        call_prepared(tmp_path)


def test_local_protocol_and_resumption_do_not_repeat_completed_call(monkeypatch, tmp_path):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(request)
            body = json.dumps({"choices": [{"message": {"content": json.dumps(
                {"rallies": [interval(0, 2)]})}}], "usage": {"total_tokens": 42}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    (tmp_path / "frame.jpg").write_bytes(b"protocol-test-image")
    (tmp_path / "request.json").write_text(json.dumps({"video": {"duration_seconds": 3},
        "windows": [{"start_seconds": 0, "end_seconds": 3, "prompt": "independent prompt",
                     "frames": [{"timestamp_seconds": 1, "image": "frame.jpg"}]}]}), encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv("RALLYCUT_VLM_URL", f"http://127.0.0.1:{server.server_port}/chat/completions")
    monkeypatch.setenv("RALLYCUT_VLM_MODEL", "test-stub")
    monkeypatch.delenv("RALLYCUT_VLM_API_KEY", raising=False)
    try:
        assert call_prepared(tmp_path)["status"] == "inferred"
        assert call_prepared(tmp_path)["usage"][0]["total_tokens"] == 42
        assert len(calls) == 1
        content = calls[0]["messages"][0]["content"]
        assert content[1]["text"] == "Video time 1.000 seconds"
        assert content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        monkeypatch.setenv("RALLYCUT_VLM_MODEL", "different-model")
        with pytest.raises(ValueError, match="checkpoint"):
            call_prepared(tmp_path)
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
