import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from backend.app import app, Bridge
from backend.engine import Engine
from backend.profiles import profile
from backend.responses import simulated_response
from configure_topic import configure
from vision import parse_args, zone_presence


def test_configuration_matches_all_three_files_and_keeps_existing_topic(tmp_path):
    (tmp_path/'wokwi').mkdir()
    (tmp_path/'wokwi'/'sketch.ino').write_text('const char* TOPIC_BASE = "purva-sanket/REPLACE_WITH_RANDOM_TEAM_ID";\n')
    (tmp_path/'.env').write_text('# Team settings\nPURVA_WEB_PORT=8001\nCUSTOM_SETTING=keep\n')
    topic = configure(tmp_path)
    assert configure(tmp_path) == topic
    assert (tmp_path/'topic.txt').read_text().strip() == topic
    assert f'"{topic}"' in (tmp_path/'wokwi'/'sketch.ino').read_text()
    env = (tmp_path/'.env').read_text()
    assert env.count('PURVA_TOPIC=') == 1
    assert f'PURVA_TOPIC={topic}' in env
    assert 'PURVA_WEB_PORT=8001' in env and 'CUSTOM_SETTING=keep' in env
    assert configure(tmp_path, new=True) != topic


def test_placeholder_topic_is_rejected_before_any_connection(tmp_path, monkeypatch):
    monkeypatch.setenv('PURVA_INPUT_MODE', 'mqtt')
    monkeypatch.setenv('PURVA_TOPIC', 'purva-sanket/REPLACE_WITH_RANDOM_TEAM_ID')
    monkeypatch.setenv('PURVA_DB', str(tmp_path/'data'/'purva.db'))
    with pytest.raises(ValueError, match='Generate a unique'):
        with TestClient(app):
            pass
    assert not (tmp_path/'data'/'purva.db').exists()


def test_api_health_does_not_hide_input_faults_and_episode_persists(tmp_path, monkeypatch):
    monkeypatch.setenv('PURVA_INPUT_MODE', 'mqtt')
    monkeypatch.setenv('PURVA_TOPIC', 'purva-sanket/api-test-1234')
    monkeypatch.setenv('PURVA_DB', str(tmp_path/'purva.db'))
    monkeypatch.setattr(Bridge, 'start', lambda self: None)
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/static/app.js').status_code == 200
        assert client.get('/api/health').json()['database'] == 'reachable'
        assert client.get('/api/state').json()['monitoring_health'] == 'DEGRADED'
        for seq in range(2):
            packet=profile(1,0,seq=seq)
            control=app.state.engine.control_payload()
            app.state.engine.mark_control_sent(control["command_id"])
            packet.update(simulated_response(control))
            assert client.post('/api/telemetry', json=packet).json()['accepted']
        assert client.post('/api/action', json={'kind':'restart'}).status_code == 200
        client.post('/api/telemetry', json=profile(3,0,seq=2)).raise_for_status()
        state = client.get('/api/state').json()
        episode_id = state['episode']['id']
        assert state['stop_latched'] and not state['motor_command']
        assert client.post('/api/action', json={'kind':'restart'}).status_code == 409
        assert client.post('/api/action', json={'kind':'acknowledge'}).status_code == 200
        assert client.get('/api/history').json()['episodes'][0]['id'] == episode_id
    with TestClient(app) as client:
        state = client.get('/api/state').json()
        assert state['episode']['id'] == episode_id
        assert state['monitoring_health'] == 'DEGRADED'
        assert state['stop_latched']


def test_bridge_rejects_bad_payloads_and_routes_control_and_scene(tmp_path):
    engine = Engine(tmp_path/'purva.db')
    bridge = Bridge(engine, 'mqtt', 'purva-sanket/bridge-test-1234')
    messages = []

    class Client:
        def subscribe(self, topic, qos):
            assert topic == bridge.topic+'/telemetry' and qos == 1
        def publish(self, topic, payload, qos, retain):
            messages.append((topic, json.loads(payload), qos, retain))
            if topic.endswith('/control'):
                bridge.stop_event.set()
            return SimpleNamespace(rc=0)

    bridge.client = Client()
    bridge.on_connect(bridge.client, None, None, SimpleNamespace(is_failure=False), None)
    for seq in range(2):
        control=engine.control_payload()
        engine.mark_control_sent(control["command_id"])
        packet = profile(1,0,seq=seq)
        packet.update(simulated_response(control))
        bridge.on_message(bridge.client, None, SimpleNamespace(payload=json.dumps(packet).encode()))
    engine.operator_action('restart')
    bridge.select_scene(3)
    bridge.run()
    assert messages[0] == (bridge.topic+'/scenario', {'scene':3}, 1, False)
    assert messages[1][0] == bridge.topic+'/control'
    assert messages[1][1]['motor_on'] is True
    assert messages[1][1]['restart_nonce'] == 1
    assert messages[1][2:] == (1, False)
    bridge.on_message(bridge.client, None, SimpleNamespace(payload=b'x'*4097))
    assert 'Oversized' in bridge.last_error
    packet['temp_c'] = float('nan')
    bridge.on_message(bridge.client, None, SimpleNamespace(payload=json.dumps(packet).encode()))
    assert bridge.last_error.startswith('Rejected telemetry:')
    assert len(engine.history()['samples']) == 2


def test_vision_uses_footpoint_and_ignores_confidence_outside_zone():
    assert zone_presence([[0,0,80,20]], [.99], (30,30,70,70)) == (False,0.0)
    assert zone_presence([[0,0,80,20],[35,0,55,50]], [.99,.73], (30,30,70,70)) == (True,.73)


def test_headless_video_options_validate_zone_and_source():
    args = parse_args(['--source','/media/factory_demo.mp4','--headless','--loop'])
    assert args.headless and args.loop and args.max_fps == 5
    with pytest.raises(SystemExit):
        parse_args(['--source','0','--loop'])
    with pytest.raises(SystemExit):
        parse_args(['--zone','.8','.1','.2','.9'])
