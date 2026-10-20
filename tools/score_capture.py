"""Observe the real stitched probability tracks before upstream decoding."""

from dataclasses import asdict
import json

import numpy as np


def install_score_capture():
    from rallyclip_engine.models import HeatmapHybridModel

    observed = []
    original = HeatmapHybridModel.postprocess

    def postprocess(self, model_output):
        tracks = np.array(model_output, copy=True)
        if tracks.ndim != 2 or tracks.shape[0] != 3:
            raise RuntimeError(f'Unexpected heatmap tracks: {tracks.shape}')
        times = float(self.request.start_time) + np.arange(tracks.shape[1]) / float(self.request.fps)
        config = asdict(self._decode_config())
        intervals = original(self, model_output)
        observed.append((tracks, times, config, intervals))
        return intervals

    HeatmapHybridModel.postprocess = postprocess

    def save(output):
        if len(observed) != 1:
            raise RuntimeError(f'Expected one observed analysis, got {len(observed)}')
        tracks, times, config, intervals = observed[0]
        if not np.isfinite(tracks).all() or tracks.min() < 0 or tracks.max() > 1:
            raise RuntimeError('Expected finite post-sigmoid probability tracks')
        np.savez_compressed(output / 'model_scores.npz', timestamps=times,
                            pointness=tracks[0], start=tracks[1], end=tracks[2])
        result = {'score_stage': 'sigmoid probabilities averaged across overlapping windows, before decode',
                  'time_basis': 'upstream decoder nominal grid: start_time + feature_index / fps',
                  'sample_count': tracks.shape[1], 'config': config,
                  'decoded_intervals': intervals, 'upstream_values_modified': False}
        (output / 'score_capture.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result

    return save
