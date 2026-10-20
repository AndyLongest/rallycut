import cv2
import numpy as np

from rallycut.ball_activity import MotionBallProposals, segment_ball_activity


def scene(x):
    frame=np.full((120,200,3),(130,85,45),dtype=np.uint8)
    cv2.circle(frame,(x,55),1,(0,255,255),-1)
    return frame


def test_stationary_centre_ball_does_not_extend_play():
    detector=MotionBallProposals(6,200,120)
    rows=[detector.update(i/6,scene(100)) for i in range(24)]
    assert not any(r['active'] for r in rows)


def test_moving_ball_then_net_stop_loses_activity():
    detector=MotionBallProposals(6,200,120)
    moving=[detector.update(i/6,scene(30+5*i)) for i in range(15)]
    stationary=[detector.update((15+i)/6,scene(100)) for i in range(18)]
    assert any(r['active'] for r in moving)
    assert not any(r['active'] for r in stationary[-6:])


def test_single_short_attempt_is_retained_and_fractional_eof_is_safe():
    rows=[{'t':1,'active':True},{'t':1.2,'active':True},{'t':1.4,'active':True},
          {'t':9.2,'active':True},{'t':9.4,'active':True},{'t':9.55,'active':True}]
    rallies,_=segment_ball_activity({'duration_seconds':9.600053},rows)
    assert len(rallies)==2
    assert rallies[-1]['end_seconds']==9.600053
