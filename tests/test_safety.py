import json
import pytest
from backend.engine import Engine
from backend.profiles import profile
from backend.responses import simulated_response


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now
    def advance(self, seconds=1): self.now += seconds


@pytest.fixture
def setup(tmp_path):
    clock=Clock()
    return Engine(tmp_path/'test.db',clock),clock


def feed(engine,clock,scene,steps,seq=0):
    for step in range(steps):
        clock.advance()
        control=engine.control_payload()
        engine.mark_control_sent(control["command_id"])
        packet=profile(scene,step,seq=seq+step)
        packet.update(simulated_response(control))
        engine.ingest(packet)
    return engine.evaluate()


def test_six_scenes_and_deliberate_restart(setup):
    engine,clock=setup
    state=feed(engine,clock,1,12)
    assert state['monitoring_health']=='AVAILABLE'
    assert state['episode'] is None
    assert state['ml']['status']=='NORMAL'
    engine.operator_action('restart')
    assert engine.evaluate()['motor_command']
    state=feed(engine,clock,2,26,12)
    episode=state['episode']['id']
    assert 'recurrence' in json.loads(state['episode']['evidence_json'])
    state=feed(engine,clock,3,3,38)
    assert state['episode']['id']==episode
    assert 'cooling' in json.loads(state['episode']['evidence_json'])
    assert state['stop_latched'] and not state['motor_command']
    state=feed(engine,clock,4,3,41)
    assert 'exposure' in json.loads(state['episode']['evidence_json'])
    state=feed(engine,clock,5,3,44)
    assert state['temperature_c'] is None
    assert state['monitoring_health']=='DEGRADED'
    assert state['episode']['id']==episode
    engine.operator_action('acknowledge')
    assert engine.active_episode() is not None
    engine.operator_action('corrective_action',note='Restored cooling and temperature input')
    state=feed(engine,clock,6,80,47)
    assert state['episode'] is None
    assert not state['motor_command']  # closure never restarts the motor
    engine.operator_action('restart')
    assert engine.evaluate()['motor_command']
    history=engine.history()
    assert history['episodes'][0]['status']=='CLOSED'
    assert history['episodes'][0]['corrective_note']
    assert history['actions']


def test_episode_survives_process_restart(setup):
    engine,clock=setup
    state=feed(engine,clock,3,3)
    episode_id=state['episode']['id']
    restored=Engine(engine.database,clock)
    state=restored.evaluate()
    assert state['episode']['id']==episode_id
    assert state['monitoring_health']=='DEGRADED'
    assert state['stop_latched']


def test_duplicate_and_out_of_order_data_do_not_refresh_health(setup):
    engine,clock=setup
    feed(engine,clock,1,3)
    packet=profile(1,2,seq=2)
    clock.advance(8)
    assert not engine.ingest(packet)
    assert not engine.ingest(profile(1,1,seq=1))
    assert engine.evaluate()['monitoring_health']=='DEGRADED'


def test_recovery_breaks_when_input_is_lost(setup):
    engine,clock=setup
    feed(engine,clock,3,3)
    engine.operator_action('acknowledge')
    engine.operator_action('corrective_action',note='Restored airflow feedback')
    state=feed(engine,clock,6,20,3)
    assert state['episode'] is not None
    episode_id=state['episode']['id']
    feed(engine,clock,5,1,23)
    state=engine.evaluate()
    assert state['episode']['id']==episode_id
    assert state['recovery_seconds']==0
    assert state['temperature_c'] is None
    with pytest.raises(ValueError): engine.operator_action('restart')


def test_camera_loss_retains_warning_and_blocks_restart(setup):
    engine,clock=setup
    feed(engine,clock,3,3)
    engine.update_vision(False,valid=False,source='vision')
    state=engine.evaluate()
    assert state['episode'] is not None
    assert state['monitoring_health']=='DEGRADED'
    with pytest.raises(ValueError): engine.operator_action('restart')


def test_rules_still_apply_in_maintenance(setup):
    engine,clock=setup
    engine.set_mode('MAINTENANCE')
    state=feed(engine,clock,3,2)
    assert 'cooling_stop' in [r['code'] for r in state['current_evidence']]
    assert state['stop_latched']
