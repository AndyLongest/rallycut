import json
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")

from rallycut.gemini import call_gemini_prepared,prepare_native_video


def bundle(tmp_path):
    (tmp_path / "frame.jpg").write_bytes(b"test-image")
    (tmp_path / "request.json").write_text(json.dumps({"fps": 1, "video": {"duration_seconds": 3},
        "windows": [{"start_seconds": 0, "end_seconds": 3, "prompt": "No labels given",
                     "frames": [{"timestamp_seconds": 1, "image": "frame.jpg"}]}]}), encoding="utf-8")


def test_native_gemini_payload_and_checkpoint(tmp_path):
    bundle(tmp_path)
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps({"rallies": [{"start_seconds": 0, "end_seconds": 2,
            "evidence": "test", "needs_review": True}], "limitations": []}),
            usage_metadata=None, model_version="test-model-version")
    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    result = call_gemini_prepared(tmp_path, "test-model", client, "test-service")
    assert result["status"] == "inferred"
    assert not result["manual_labels_included"]
    assert calls[0]["contents"][1].text == "Video time 1.000 seconds"
    assert calls[0]["contents"][2].inline_data.mime_type == "image/jpeg"
    call_gemini_prepared(tmp_path, "test-model", client, "test-service")
    assert len(calls) == 1
    with pytest.raises(ValueError, match="checkpoint"):
        call_gemini_prepared(tmp_path, "another-model", client, "test-service")


def test_unknown_native_request_is_never_automatically_repeated(tmp_path):
    bundle(tmp_path)
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        raise TimeoutError("ambiguous provider billing")
    client = SimpleNamespace(models=SimpleNamespace(generate_content=fail))
    with pytest.raises(TimeoutError):
        call_gemini_prepared(tmp_path, "test", client, "test")
    with pytest.raises(RuntimeError, match="previous Gemini attempt"):
        call_gemini_prepared(tmp_path, "test", client, "test")
    assert len(calls) == 1


def test_native_video_payload_uses_video_metadata_and_low_resolution(tmp_path):
    (tmp_path/'video.mp4').write_bytes(b'test-video')
    (tmp_path/'request.json').write_text(json.dumps({'input_kind':'native_video','fps':2,
        'audio_included':True,'video':{'duration_seconds':3},'windows':[{'start_seconds':0,
        'end_seconds':3,'video_file':'video.mp4','fps':2,'prompt':'No annotations sent'}]}),encoding='utf-8')
    calls=[]
    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text='{"rallies":[],"limitations":[]}',usage_metadata=None,model_version='test')
    client=SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    r=call_gemini_prepared(tmp_path,'test',client,'test')
    assert calls[0]['contents'][0].inline_data.mime_type=='video/mp4'
    assert calls[0]['contents'][0].video_metadata.fps==2
    assert calls[0]['config'].media_resolution.value=='MEDIA_RESOLUTION_LOW'
    assert r['audio_included'] and r['method']=='gemini_native_video'


def test_invalid_video_sampling_is_rejected_before_preparation_or_remote_call(tmp_path):
    with pytest.raises(ValueError,match='sampling fps'):
        prepare_native_video({},tmp_path/'not-created',sample_fps=0)
    assert not (tmp_path/'not-created').exists()
