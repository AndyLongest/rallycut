import numpy as np
import pytest
from scenedetect.detectors import AdaptiveDetector

from rallycut.regional_scenes import RegionalSceneDetector, validate_scene_profile


def test_global_regression_and_regional_union_use_upstream_detector():
    detector = RegionalSceneDetector()
    reference = AdaptiveDetector(adaptive_threshold=3, min_scene_len=8,
                                 window_width=3, min_content_val=.5, luma_only=True)
    expected = []
    for i in range(40):
        frame = np.full((180,320,3), 40, np.uint8)
        if i >= 16:
            frame[80:140,30:75] = 180
        detector.process(i, frame)
        expected.extend(t/4 for t in reference.process_frame(i,frame))
    assert detector.cuts["global"] == expected == [4.0]
    assert detector.cuts["left_lower"] == [4.0]
    assert detector.cuts["right_lower"] == []
    assert detector.candidates() == [4.0]  # duplicate regional evidence is one cut


def test_static_scene_produces_no_candidates():
    detector = RegionalSceneDetector()
    for i in range(40):
        detector.process(i,np.full((180,320,3),50,np.uint8))
    assert detector.candidates() == []


def test_cached_profile_cannot_silently_skip_requested_regions():
    validate_scene_profile({"visual_stats": {}}, "global")
    validate_scene_profile({"visual_stats": {"scene_profile":"regional"}}, "regional")
    with pytest.raises(ValueError, match="differs"):
        validate_scene_profile({"visual_stats": {}}, "regional")
    with pytest.raises(ValueError, match="differs"):
        validate_scene_profile({"visual_stats": {"scene_profile":"regional"}}, "global")
