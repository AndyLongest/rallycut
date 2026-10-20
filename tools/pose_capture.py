"""Observe the actual upstream stream without changing its yielded values."""

import json
from collections import deque

import numpy as np


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


def install_capture():
    from extraction.pose_extractor import PoseExtractor
    from preprocessing.data_preprocessor import DataPreprocessor
    from features.feature_engineer import FeatureEngineer

    samples, vectors = [], []
    original_iterator = PoseExtractor.frame_iterator_pyav
    original_pose = PoseExtractor.iter_pose_frames
    original_preprocess = DataPreprocessor.iter_preprocess_frames
    original_features = FeatureEngineer.create_feature_vector

    def iterator(self, *a, **kw):
        for frame, timestamp in original_iterator(self, *a, **kw):
            if hasattr(self, '_diagnostic_times'):
                start, end = self._diagnostic_range
                if start <= timestamp <= end:
                    self._diagnostic_times.append(float(timestamp))
            yield frame, timestamp

    def pose(self, *a, **kw):
        # Actual PyAV PTS, including skipped frames: never infer time from index/5.
        self._diagnostic_times = deque()
        start = kw.get('start_time_seconds', a[2] if len(a) > 2 else 0)
        duration = kw.get('duration_seconds', a[3] if len(a) > 3 else 60)
        self._diagnostic_range = (start, start + duration)
        try:
            for record in original_pose(self, *a, **kw):
                timestamp = self._diagnostic_times.popleft()
                if record.get('annotation_status', 0) >= 0:
                    samples.append({'timestamp_seconds': timestamp, 'raw': plain(record)})
                yield record
        finally:
            del self._diagnostic_times

    def preprocess(self, *a, **kw):
        width = kw.get('src_width', a[2] if len(a) > 2 else None)
        height = kw.get('src_height', a[3] if len(a) > 3 else None)
        for record in original_preprocess(self, *a, **kw):
            filtered, target, near, far = record
            if target >= 0:
                samples[-1].update(filtered=plain(filtered), near=plain(near), far=plain(far),
                                   source_size=[width, height],
                                   reference_size=[self.screen_width, self.screen_height])
            yield record

    def features(self, *a, **kw):
        result = original_features(self, *a, **kw)
        vectors.append(np.asarray(result).copy())
        samples[-1]['feature_index'] = len(vectors) - 1
        return result

    PoseExtractor.frame_iterator_pyav = iterator
    PoseExtractor.iter_pose_frames = pose
    DataPreprocessor.iter_preprocess_frames = preprocess
    FeatureEngineer.create_feature_vector = features

    def save(output):
        if not samples or len(samples) != len(vectors):
            raise RuntimeError('Pose/feature capture alignment failed')
        if any(s.get('feature_index') != i for i, s in enumerate(samples)):
            raise RuntimeError('Feature capture ordering failed')
        matrix = np.stack(vectors)
        if matrix.shape != (len(samples), 362):
            raise RuntimeError(f'Unexpected feature shape: {matrix.shape}')
        with (output / 'pose_samples.jsonl').open('w', encoding='utf-8') as stream:
            for record in samples:
                stream.write(json.dumps(record, allow_nan=False) + '\n')
        np.savez_compressed(output / 'actual_features.npz', features=matrix,
                            timestamps=np.array([s['timestamp_seconds'] for s in samples]))
        return {'samples': len(samples), 'feature_shape': list(matrix.shape),
                'timestamps': 'actual PyAV PTS', 'coordinates': 'raw/filtered native; near/far reference',
                'upstream_values_modified': False}

    return save
