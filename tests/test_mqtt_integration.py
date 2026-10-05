"""Real local MQTT transport with a synthetic device; no public broker required."""
import asyncio
import json
import socket
import time
import httpx
import paho.mqtt.client as mqtt
from amqtt.broker import Broker
from backend.app import app, lifespan
from backend.profiles import profile
from backend.responses import simulated_response


async def wait_until(predicate, timeout=8):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(.05)
    raise AssertionError('MQTT integration condition did not arrive before timeout')


def test_live_mqtt_telemetry_scene_control_vision_and_database(tmp_path, monkeypatch):
    with socket.socket() as port_socket:
        port_socket.bind(('127.0.0.1',0))
        port = port_socket.getsockname()[1]
    topic = 'purva-sanket/local-integration-1234'
    monkeypatch.setenv('PURVA_INPUT_MODE','mqtt')
    monkeypatch.setenv('PURVA_TOPIC',topic)
    monkeypatch.setenv('PURVA_MQTT_HOST','127.0.0.1')
    monkeypatch.setenv('PURVA_MQTT_PORT',str(port))
    monkeypatch.setenv('PURVA_DB',str(tmp_path/'purva.db'))

    async def exercise():
        broker = Broker({
            'listeners': {'default': {'type':'tcp','bind':f'127.0.0.1:{port}'}},
            'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous':True}},
        })
        await broker.start()
        controls, scenes = [], []
        device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='purva-test-device')

        def connected(client, userdata, flags, reason, properties):
            client.subscribe(topic+'/control',qos=1)
            client.subscribe(topic+'/scenario',qos=1)

        def received(client, userdata, message):
            payload = json.loads(message.payload)
            (controls if message.topic.endswith('/control') else scenes).append(payload)

        device.on_connect, device.on_message = connected, received
        try:
            async with lifespan(app):
                device.connect_async('127.0.0.1',port,keepalive=15)
                device.loop_start()
                await wait_until(lambda: app.state.bridge.connected and device.is_connected() and bool(controls))
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    async def publish(scene, sequence):
                        packet = profile(scene,0,session='mqtt-test-session',seq=sequence)
                        packet['source'] = 'MQTT integration: synthetic device'
                        packet.update(simulated_response(controls[-1]))
                        device.publish(topic+'/telemetry',json.dumps(packet),qos=1,retain=False)
                        await wait_until(lambda: app.state.engine.last_seq == sequence)
                        await wait_until(lambda: controls[-1]['command_id'] == app.state.engine.responses.current['command_id'])

                    for sequence in range(12):
                        await publish(1,sequence)
                    assert (await client.get('/api/health')).json()['mqtt_connected']
                    assert (await client.get('/api/state')).json()['response']['confirmed']
                    assert (await client.post('/api/action',json={'kind':'restart'})).status_code == 200
                    await wait_until(lambda: controls[-1]['motor_on'])
                    assert (await client.post('/api/scene',json={'scene':3})).status_code == 200
                    await wait_until(lambda: bool(scenes) and scenes[-1]['scene'] == 3)
                    await publish(3,12)
                    await wait_until(lambda: not controls[-1]['motor_on'] and controls[-1]['warning'])
                    await publish(3,13)
                    state = (await client.get('/api/state')).json()
                    episode_id = state['episode']['id']
                    assert not state['motor_command']
                    assert state['response']['confirmed']
                    assert state['response']['feedback_running'] is False
                    await client.post('/api/vision',json={'present':True,'valid':True,'source':'vision','confidence':.8})
                    state = (await client.get('/api/state')).json()
                    assert 'exposure' in json.loads(state['episode']['evidence_json'])
                    assert state['vision']['source'] == 'vision'
                    await publish(5,14)
                    state = (await client.get('/api/state')).json()
                    assert state['temperature_c'] is None
                    assert state['monitoring_health'] == 'DEGRADED'
                    assert state['episode']['id'] == episode_id
                    assert (await client.post('/api/action',json={'kind':'restart'})).status_code == 409
                    history = (await client.get('/api/history')).json()
                    assert len(history['samples']) == 15
                    assert history['episodes'][0]['id'] == episode_id
                    assert history['response_commands']
                    assert (await client.post('/api/fault',json={'name':'cooling_missing','enabled':True})).status_code == 200
                    assert 'rule_warning' in (await client.get('/api/comparison/export')).text
        finally:
            device.disconnect()
            device.loop_stop()
            await broker.shutdown()

    asyncio.run(exercise())
