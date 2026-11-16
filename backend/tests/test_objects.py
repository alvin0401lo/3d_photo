"""Selected-object pipeline contracts. Mock Tripo responses do not establish live generation quality."""
import base64
import io
import json
import struct

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import config, main, objects, store

REGION = {'x': .25, 'y': .1, 'width': .5, 'height': .8}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path / 'storage')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setenv('TRIPO_API_KEY', '')
    monkeypatch.delenv('TRIPO_MODEL', raising=False)
    with TestClient(main.app) as api: yield api


def create(client):
    output = io.BytesIO()
    Image.new('RGB', (200, 200), 'orange').save(output, 'PNG')
    response = client.post('/api/projects', files={'file': ('person-fixture.png', output.getvalue())})
    assert response.status_code == 201
    return response.json()


def test_subject_selection_crop_validation_and_persistence(client):
    project = create(client)
    response = client.put(f"/api/projects/{project['id']}/subject", json=REGION)
    assert response.status_code == 200
    selected = response.json()['subject']
    assert len(selected['token']) == 64
    crop = Image.open(io.BytesIO(client.get(selected['assets']['preview']).content))
    assert crop.size == (100, 160) and not crop.getexif()
    store.init()
    assert store.get_project(project['id'])['subject'] == selected
    for invalid in [{**REGION, 'x': .9}, {**REGION, 'width': .01}, {**REGION, 'y': -1}, {**REGION, 'height': 0}]:
        assert client.put(f"/api/projects/{project['id']}/subject", json=invalid).status_code == 422
    assert client.get(f"/api/projects/{project['id']}/files/subject?selection=../secret").status_code == 404
    assert client.get(project['assets']['image']).status_code == 200


def test_object_generation_requires_selection_consent_and_private_key(client, monkeypatch):
    project = create(client); url = f"/api/projects/{project['id']}/object-jobs"
    assert client.post(url, json={'allow_external_processing': True}).status_code == 422
    client.put(f"/api/projects/{project['id']}/subject", json=REGION)
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={'allow_external_processing': True}).status_code == 503
    monkeypatch.setenv('TRIPO_API_KEY', 'fixture-private-key')
    caps = client.get('/api/capabilities')
    assert caps.json()['object_generation']['configured'] and 'fixture-private-key' not in caps.text
    payload = {'allow_external_processing': True, 'orientation': 'align_image'}
    queued = client.post(url, json=payload, headers={'Idempotency-Key': 'same-click'})
    assert queued.status_code == 202
    job = queued.json()
    assert job['parameters']['selection'] == REGION and job['parameters']['orientation'] == 'align_image'
    assert client.post(url, json=payload, headers={'Idempotency-Key': 'same-click'}).json()['id'] == job['id']
    with pytest.raises(ValueError): store.enqueue(project['id'], job_type='panorama')
    client.post('/api/jobs/' + job['id'] + '/cancel')
    assert store.get_job(job['id'])['status'] == 'cancelled'


def test_tripo_model_configuration_fails_cleanly(client, monkeypatch):
    project = create(client)
    client.put(f"/api/projects/{project['id']}/subject", json=REGION)
    monkeypatch.setenv('TRIPO_MODEL', 'invalid-model')
    assert not client.get('/api/capabilities').json()['object_generation']['configured']
    assert client.post(f"/api/projects/{project['id']}/object-jobs", json={'allow_external_processing': True}).status_code == 503


def task(client, monkeypatch):
    monkeypatch.setenv('TRIPO_API_KEY', 'private-test-key')
    project = create(client)
    return store.enqueue(project['id'], job_type='object', parameters={'selection': REGION, 'model': 'v3.1-20260211', 'allow_external_processing': True, 'orientation': 'align_image'})


def test_tripo_upload_submission_poll_download_and_publication_contract(client, monkeypatch):
    job = task(client, monkeypatch); store.claim(); seen = []; states = iter(['queued', 'running', 'success'])
    model = (store.ROOT / 'examples' / 'cesium-man.glb').read_bytes()
    def handler(request):
        seen.append((request.method, str(request.url)))
        if request.url.path == '/v3/files':
            assert request.headers['authorization'] == 'Bearer private-test-key'
            assert 'multipart/form-data' in request.headers['content-type']
            assert b'filename="subject.jpg"' in request.content
            start, end = request.content.find(b'\xff\xd8'), request.content.rfind(b'\xff\xd9') + 2
            crop = Image.open(io.BytesIO(request.content[start:end]))
            assert crop.size == (100, 160)
            return httpx.Response(200, json={'code': 0, 'data': {'file_token': 'file_fixture'}})
        if request.url.path == '/v3/generation/image-to-model':
            assert request.headers['authorization'] == 'Bearer private-test-key'
            body = json.loads(request.content)
            assert body == {'input': 'file_fixture', 'model': 'v3.1-20260211', 'texture': True, 'pbr': True, 'face_limit': 50000, 'orientation': 'align_image'}
            return httpx.Response(200, json={'code': 0, 'data': {'task_id': 'remote-task'}})
        if request.url.host == 'cdn.tripo3d.ai':
            assert 'authorization' not in request.headers
            return httpx.Response(200, content=model)
        assert store.get_job(job['id'])['remote_id'] == 'remote-task'
        return httpx.Response(200, json={'code': 0, 'data': {'status': next(states), 'progress': 50, 'output': {'model_url': 'https://cdn.tripo3d.ai/output/model.glb?signature=fixture'}, 'credits_consumed': 30}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        result = objects.run(job, lambda message: None, remote, poll_interval=0)
    store.update_job(job['id'], status='completed', result=json.dumps(result))
    assert result['provider'] == 'tripo' and result['consumed_credits'] == 30
    assert sum(method == 'POST' and '/generation/image-to-model' in url for method, url in seen) == 1
    assert client.get(result['assets']['object_model']).content == model
    assert 'signature' not in client.get(result['assets']['object_manifest']).text
    assert store.get_project(job['project_id'])['object']['ai_generated']
    other = create(client)
    assert client.get(f"/api/projects/{other['id']}/files/object_model?job_id={job['id']}").status_code == 404
    assert client.get(f"/api/projects/{job['project_id']}/files/raw?job_id={job['id']}").status_code == 404


def test_failed_task_resumes_without_a_second_post(client, monkeypatch):
    job = task(client, monkeypatch)
    store.update_job(job['id'], status='failed', remote_id='saved-task', error='interrupted')
    assert client.post('/api/jobs/' + job['id'] + '/resume').status_code == 202
    resumed = store.claim()
    seen = []
    def handler(request):
        seen.append(request.method)
        if request.url.host == 'tripo-data.rg1.data.tripo3d.com': return httpx.Response(200, content=(store.ROOT / 'examples' / 'cesium-man.glb').read_bytes())
        return httpx.Response(200, json={'code': 0, 'data': {'status': 'success', 'output': {'model_url': 'https://tripo-data.rg1.data.tripo3d.com/model.glb?Signature=fixture'}}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        result = objects.run(resumed, lambda message: None, remote, poll_interval=0)
    assert 'POST' not in seen and result['remote_id'] == 'saved-task'


def test_previous_meshy_task_cannot_be_resumed_as_tripo(client, monkeypatch):
    project = create(client)
    old = store.enqueue(project['id'], job_type='object', parameters={'selection': REGION, 'model': 'meshy-7.1', 'allow_external_processing': True})
    store.update_job(old['id'], status='failed', remote_id='old-provider-task', error='interrupted')
    response = client.post('/api/jobs/' + old['id'] + '/resume')
    assert response.status_code == 409 and 'previous image-to-3D provider' in response.text


@pytest.mark.parametrize('status', [400, 401, 402, 403, 429, 500])
def test_tripo_rejection_is_redacted_and_not_resubmitted(client, monkeypatch, status):
    job = task(client, monkeypatch); requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={'message': 'private-test-key raw secret'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        with pytest.raises(ValueError) as error: objects.run(job, lambda message: None, remote)
    assert 'private-test-key' not in str(error.value) and len(requests) == 1


def test_tripo_application_rate_limit_error_is_redacted(client, monkeypatch):
    job = task(client, monkeypatch); requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'code': 1007, 'message': 'private-test-key raw secret'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        with pytest.raises(ValueError, match='Tripo rate limit') as error:
            objects.run(job, lambda message: None, remote)
    assert 'private-test-key' not in str(error.value) and len(requests) == 1


def test_cancelled_object_never_submits_and_running_cancel_stops_local_polling(client, monkeypatch):
    job = task(client, monkeypatch); store.update_job(job['id'], cancel=1)
    with pytest.raises(ValueError, match='cancelled before'): objects.run(job, lambda message: None)
    store.update_job(job['id'], cancel=0); requests = []
    def handler(request):
        requests.append(request.method)
        if request.url.path == '/v3/generation/image-to-model':
            store.update_job(job['id'], cancel=1)
            return httpx.Response(200, json={'code': 0, 'data': {'task_id': 'cancel-me'}})
        if request.url.path == '/v3/files': return httpx.Response(200, json={'code': 0, 'data': {'file_token': 'file_fixture'}})
        return httpx.Response(200, json={})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        with pytest.raises(ValueError, match='cancelled locally'): objects.run(store.get_job(job['id']), lambda message: None, remote)
    assert requests == ['POST', 'POST']


def test_cancellation_during_upload_prevents_paid_generation_submission(client, monkeypatch):
    job = task(client, monkeypatch); requests = []
    def handler(request):
        requests.append(request.url.path)
        store.update_job(job['id'], cancel=1)
        return httpx.Response(200, json={'code': 0, 'data': {'file_token': 'file_fixture'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        with pytest.raises(ValueError, match='before the Tripo generation task'):
            objects.run(job, lambda message: None, remote, poll_interval=0)
    assert requests == ['/v3/files']


def test_glb_validation_and_asset_url_boundary():
    with pytest.raises(ValueError): objects.validate_glb(b'not a glb')
    model = (store.ROOT / 'examples' / 'cesium-man.glb').read_bytes()
    assert objects.validate_glb(model)['meshes']
    for url in ['http://cdn.tripo3d.ai/model.glb', 'https://127.0.0.1/model.glb', 'https://cdn.tripo3d.ai.evil.example/model.glb']:
        with pytest.raises(ValueError): objects.download_model(None, url)
    document = json.dumps({'meshes': [{}], 'scenes': [{}], 'buffers': [{'uri': 'https://external.invalid/mesh.bin'}]}).encode()
    document += b' ' * (-len(document) % 4)
    broken = struct.pack('<4sIIII', b'glTF', 2, 20 + len(document), len(document), 0x4E4F534A) + document
    with pytest.raises(ValueError, match='self-contained'): objects.validate_glb(broken)


@pytest.mark.parametrize('host', ['cdn.tripo3d.ai', 'cdn.tripo3d.com', 'tripo-data.rg1.data.tripo3d.com', 'tripo-data.rg2.data.tripo3d.ai'])
def test_regional_model_download_and_checked_redirect(host):
    model = (store.ROOT / 'examples' / 'cesium-man.glb').read_bytes()
    seen = []
    def handler(request):
        seen.append(request)
        assert request.method == 'GET' and 'authorization' not in request.headers
        if len(seen) == 1:
            return httpx.Response(302, headers={'location': f'https://{host}/model.glb?Signature=fixture'})
        assert request.url.params['Signature'] == 'fixture'
        return httpx.Response(200, content=model)
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        assert objects.download_model(remote, 'https://cdn.tripo3d.ai/start') == model
    assert len(seen) == 2


@pytest.mark.parametrize('url', [
    'http://tripo-data.rg1.data.tripo3d.com/model.glb',
    'https://127.0.0.1/model.glb', 'https://169.254.169.254/model.glb',
    'https://tripo-data.rg1.data.tripo3d.com.evil.example/model.glb',
    'https://evil-data.tripo3d.com/model.glb', 'https://evil.example/model.glb',
    'https://user:secret@cdn.tripo3d.ai/model.glb',
    'https://cdn.tripo3d.ai:8443/model.glb', 'https://cdn.tripo3d.ai:bad/model.glb',
])
def test_invalid_download_and_redirect_are_rejected_before_fetch(url):
    with pytest.raises(ValueError): objects.download_model(None, url)
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={'location': url})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        # httpx rejects malformed Location ports while constructing next_request,
        # even with redirects disabled. run() redacts RequestError for the UI.
        with pytest.raises((ValueError, httpx.RequestError)):
            objects.download_model(remote, 'https://cdn.tripo3d.ai/start')
    assert len(seen) == 1


def test_model_redirect_loop_is_bounded():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(307, headers={'location': '/again'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as remote:
        with pytest.raises(ValueError, match='redirected too many times'):
            objects.download_model(remote, 'https://cdn.tripo3d.ai/start')
    assert len(seen) == 4


def test_parallel_startup_migrates_existing_subject_data_without_loss(client):
    from concurrent.futures import ThreadPoolExecutor
    project = create(client)
    with store.connection() as db:
        db.execute('ALTER TABLE projects DROP COLUMN subject')
        db.execute('ALTER TABLE jobs DROP COLUMN remote_id')
    with ThreadPoolExecutor(max_workers=4) as executor:
        for result in executor.map(lambda _: store.init(), range(4)): pass
    assert store.get_project(project['id'])['subject'] is None
    assert store.get_project(project['id'])['name'] == project['name']
