"""Guard diagnostic stage attribution and non-mutating observation."""

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
import types

import numpy as np


def load_tool(name):
    file = Path(__file__).resolve().parents[1] / 'tools' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_score_capture_preserves_objects_and_nominal_time(monkeypatch, tmp_path):
    @dataclass
    class Config:
        threshold: float = .5

    result = [(2.0, 2.4)]
    tracks = np.array([[.7,.8,.4],[.4,.2,.1],[.1,.2,.8]], dtype=np.float32)
    before = tracks.copy()

    class Model:
        request = types.SimpleNamespace(start_time=2, fps=5)
        def _decode_config(self):
            return Config()
        def postprocess(self, values):
            assert values is tracks
            return result

    module = types.ModuleType('rallyclip_engine.models')
    module.HeatmapHybridModel = Model
    monkeypatch.setitem(sys.modules, 'rallyclip_engine.models', module)
    save = load_tool('score_capture').install_score_capture()
    assert Model().postprocess(tracks) is result
    np.testing.assert_array_equal(tracks, before)
    audit = save(tmp_path)
    output = np.load(tmp_path/'model_scores.npz')
    np.testing.assert_allclose(output['timestamps'], [2,2.2,2.4])
    np.testing.assert_array_equal(output['pointness'], tracks[0])
    assert audit['upstream_values_modified'] is False
    assert json.loads((tmp_path/'score_capture.json').read_text())['decoded_intervals'] == [[2,2.4]]


def test_continuous_high_score_is_not_reported_as_merging():
    explain = load_tool('diagnose_scores').explain_event
    trace = {'runs':[{'raw_start_seconds':0,'raw_end_seconds':50,
                      'refined_end_seconds':49.9,'discard_reason':None,'merged_group':0}],
             'after_merge':[(.1,49.9)]}
    label, detail = explain(35, None, trace, {}, 2)
    assert label == '回合中分数连续跨过人工结束'
    assert '0.00–50.00' in detail


def test_filtered_candidate_and_merged_candidate_remain_distinct():
    explain = load_tool('diagnose_scores').explain_event
    run = {'raw_start_seconds':9.8,'raw_end_seconds':10,
           'refined_start_seconds':9.8,'refined_end_seconds':10,
           'duration_seconds':.2,'discard_reason':'too_short','merged_group':None}
    trace = {'runs':[run],'after_merge':[]}
    assert explain(10,None,trace,{},2)[0] == '候选被时长过滤'
    run.update(discard_reason=None,merged_group=0)
    trace['after_merge']=[(9.8,20)]
    assert explain(10,None,trace,{},2)[0] == '附近候选被合并'


def test_matched_end_is_not_relabeled_due_to_missing_input():
    explain = load_tool('diagnose_scores').explain_event
    assert explain(10,11,{}, {'far_missing':20},2)[0] == '结束点已匹配'
