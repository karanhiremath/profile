from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('run.py')


class AuthEventTest(unittest.TestCase):
    def test_routing_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = dict(id='0' * 20 + '-' + 'a' * 32, type='auth.needs-login',
                        session='aws:base:default', ts=datetime.now(timezone.utc).isoformat(),
                        login='aws', expires_at=None, identity=None)
            command = [sys.executable, str(SCRIPT), 'auth-event', '--target-sid', 'coordinator']
            env = dict(os.environ, PI_AGENT=tmp)
            for _ in range(2):
                subprocess.run(command, env=env, input=json.dumps(body), text=True, check=True)
            inbox, = (Path(tmp) / 'jobs/sessions/coordinator').glob('*.status.json')
            lane, = (Path(tmp) / 'jobs/streams/cauth').glob('*.status.json')
            target = json.loads(inbox.read_text())
            display = json.loads(lane.read_text())
            self.assertEqual(target['targetSid'], 'coordinator')
            self.assertEqual(target['status'], 'failed')
            self.assertEqual(target['operatorCommand'], 'aws login --profile default')
            self.assertEqual(display['status'], 'update')
            self.assertNotIn('targetSid', display)
            self.assertEqual(len(Path(target['eventsPath']).read_text().splitlines()), 1)
            body['access_token'] = 'not-for-output'
            result = subprocess.run(command, env=env, input=json.dumps(body), text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(body['access_token'], result.stderr + result.stdout)
