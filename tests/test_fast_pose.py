import numpy as np
from rallycut.fast_pose import interpolate_pose
from rallycut.teacher_comparison import compare_intervals


def record(x):
    return {"boxes": np.array([[x, 0, x+100, 200]], np.float32),
            "box_conf": np.array([.9], np.float32),
            "keypoints": np.full((1,17,2), x, np.float32),
            "conf": np.full((1,17), .8, np.float32), "annotation_status": 0}


def test_interpolation_preserves_originals_and_geometry():
    a, b = record(0), record(10)
    result = interpolate_pose(a, b, .5)
    np.testing.assert_allclose(result["keypoints"], 5)
    np.testing.assert_allclose(result["boxes"], [[5,0,105,200]])
    np.testing.assert_allclose(a["keypoints"], 0)


def test_cut_or_identity_jump_does_not_invent_skeleton():
    a, b = record(0), record(1000)
    np.testing.assert_array_equal(interpolate_pose(a,b,.4)["keypoints"], a["keypoints"])
    np.testing.assert_array_equal(interpolate_pose(a,b,.6)["keypoints"], b["keypoints"])


def test_sparse_iterator_keeps_grid_reduces_calls_and_restores(monkeypatch):
    import sys
    from types import ModuleType
    from rallycut.fast_pose import sparse_pose
    module = ModuleType("extraction.pose_extractor")
    class Model:
        calls = 0
        def predict(self, index):
            self.calls += 1
            return record(index)
    class Extractor:
        def __init__(self):
            self.batch_size = 8
            self.model = Model()
        def iter_pose_frames(self):
            for index in range(8):
                yield self.model.predict(index)
    module.PoseExtractor = Extractor
    monkeypatch.setitem(sys.modules, "extraction.pose_extractor", module)
    original = Extractor.iter_pose_frames
    extractor = Extractor()
    model = extractor.model
    with sparse_pose(3) as audit:
        rows = list(extractor.iter_pose_frames())
    assert len(rows) == 8
    assert model.calls == 3
    assert audit["pose_calls"] == 3
    np.testing.assert_allclose([r["keypoints"][0,0,0] for r in rows], [0,1,2,3,4,5,6,6])
    assert extractor.model is model
    assert extractor.batch_size == 8
    assert Extractor.iter_pose_frames is original


def test_teacher_agreement_reports_merge_even_when_time_overlap_high():
    teacher = [{"start_seconds":0,"end_seconds":20},{"start_seconds":21,"end_seconds":40}]
    student = [{"start_seconds":0,"end_seconds":40}]
    result = compare_intervals(student,teacher,40)
    assert result["active_time_iou"] > .95
    assert result["ends"]["missing"] == 1
    assert result["starts"]["missing"] == 1
    assert "not_human_truth" in result["reference_kind"]


def test_empty_scene_rechecks_and_visual_change_forces_detection(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    from rallycut.fast_pose import cropped_pose
    pose = ModuleType("extraction.pose_extractor")
    yolo = ModuleType("extraction.yolo_onnx_runner")
    yolo.Result = lambda *args: None  # Empty reuse never constructs cropped results.
    class Model:
        calls = 0
        def predict(self, **kwargs):
            self.calls += 1
            return [SimpleNamespace(boxes=[])]
    class Extractor:
        def __init__(self):
            self.model = Model()
            self.batch_size = 1
        def iter_pose_frames(self):
            for index in range(10):
                image = np.full((64,64,3), 0 if index < 3 else 100, np.uint8)
                yield self.model.predict(source=[image],imgsz=960)[0]
    pose.PoseExtractor = Extractor
    monkeypatch.setitem(sys.modules,"extraction.pose_extractor",pose)
    monkeypatch.setitem(sys.modules,"extraction.yolo_onnx_runner",yolo)
    extractor=Extractor()
    original_model=extractor.model
    with cropped_pose(10,256,5) as audit:
        rows=list(extractor.iter_pose_frames())
    assert len(rows) == 10
    assert audit["full_calls"] == 3  # initial, visible change at3, timeout at8
    assert audit["empty_reuses"] == 7
    assert audit["scene_resets"] == 1
    assert extractor.model is original_model
