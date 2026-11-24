import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock

from validate_ready import DispatchError, Forge, observe, routes


class ValidateReadyTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root / 'state'
        self.case = self.root / 'case'
        self.state.mkdir()
        self.case.mkdir()
        job = 'candidate-ready-' + '0' * 64
        self.path = self.root / (job + '.status.json')
        self.repository = 'registry.example.test/project/worker'
        self.image = self.repository + '@sha256:' + 'a' * 64
        self.key = 'cbuild-ready-' + 'a' * 64
        self.id_ = 'id_' + self.key
        self.route = ('fips', 'voice', 'cluster', 'release', 'worker')
        self.event = dict(schema='pi.job-watcher.v1', jobId=job, source='cbuild', targetSid='sid',
                          stream='candidate-ready', type='job.finished', status='succeeded',
                          eventType='candidate-ready', ts=datetime.now(timezone.utc).isoformat(),
                          candidate=dict(zip(('infra', 'model', 'cluster', 'release', 'component'),
                                             self.route), rollout='pod-1', image=self.image))
        self.config = 'voice-attach'
        self.forge = Mock(origin='https://forge.example.test')
        self.forge.request.return_value = (202, dict(id=self.id_, workflow_id=self.id_,
                                                     idempotency_key=self.key, status='pending'))
        self.path.write_text(json.dumps(self.event))

    def run_event(self, sid='sid'):
        return observe(self.path, sid, {self.route: (self.repository, self.config)},
                       self.state, self.forge, self.case)

    def test_concurrent_replay_and_repair_post_only_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            left, right = list(pool.map(lambda _: self.run_event(), range(2)))
        self.assertEqual(left, right)
        self.assertEqual(json.loads(left.read_text())['workflow_id'], self.id_)
        left.unlink()
        self.assertTrue(self.run_event().exists())
        self.forge.request.assert_called_once_with(body={
            'config_ref': self.config, 'overrides': {'candidate': {'image': self.image}},
            'trigger': {'source': 'workflow'}, 'idempotency_key': self.key,
        })

    def test_timeout_readback_without_resubmit(self):
        self.forge.request.side_effect = TimeoutError
        with self.assertRaises(TimeoutError):
            self.run_event()
        self.assertEqual(list(self.case.iterdir()), [])
        self.forge.request.side_effect = None
        run = {'id': self.id_, 'config_ref': self.config, 'trigger': {'actor': 'cbuild'},
               'effective_config': {'candidate': {'image': self.image}}}
        self.forge.request.return_value = (200, {**run, 'effective_config': {}})
        with self.assertRaises(DispatchError):
            self.run_event()
        self.forge.request.return_value = (200, run)
        self.assertEqual(json.loads(self.run_event().read_text())['status'], 'reconciled')
        self.assertEqual(sum('body' in call.kwargs for call in self.forge.request.call_args_list), 1)
        self.forge.request.assert_called_with('/' + self.id_)

    def test_conflict_requires_matching_readback(self):
        self.forge.request.side_effect = [(409, {}), (200, {'id': self.id_, 'config_ref': 'other'})]
        with self.assertRaises(DispatchError):
            self.run_event()
        self.assertEqual(list(self.case.iterdir()), [])

    def test_wrong_sid_unapproved_repository_and_stale(self):
        with self.assertRaises(DispatchError):
            self.run_event(sid='other')
        self.event['candidate']['image'] = self.image.replace('/worker', '/other')
        self.path.write_text(json.dumps(self.event))
        with self.assertRaises(DispatchError):
            self.run_event()
        self.event['candidate']['image'] = self.image
        self.event['ts'] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        self.path.write_text(json.dumps(self.event))
        self.assertIsNone(self.run_event())
        self.forge.request.assert_not_called()

    def test_route_requires_attach_mode(self):
        file = self.root / 'routes.json'
        row = {**self.event['candidate'], 'repository': self.repository, 'config_ref': self.config,
               'mode': 'reinstall'}
        file.write_text(json.dumps({'schema': 'aos.validate-on-ready.routes.v1', 'routes': [row]}))
        with self.assertRaises(DispatchError):
            routes(file)

    def test_forge_http_request_contract(self):
        client = Forge('https://forge.example.test', 'dummy')
        client.opener = MagicMock()
        response = client.opener.open.return_value.__enter__.return_value
        response.status = 202
        response.read.return_value = b'{}'
        self.assertEqual(client.request(body={'idempotency_key': self.key}), (202, {}))
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.full_url, 'https://forge.example.test/v1/validations')
        self.assertEqual(request.get_header('X-forge-actor'), 'cbuild')
        self.assertEqual(request.get_header('X-api-key'), 'dummy')
        with self.assertRaises(DispatchError):
            Forge('http://forge.example.test', 'dummy')
