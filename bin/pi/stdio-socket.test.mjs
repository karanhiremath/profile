import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {listenUnix} from '../../config/pi/extensions/lib/stdio-socket.ts';

test('listenUnix refuses to unlink a regular file', () => {
  const root = mkdtempSync(join(tmpdir(), 'pi-stdio-socket-'));
  const path = join(root, 'not-a-socket');
  writeFileSync(path, 'keep');
  try {
    assert.throws(() => listenUnix(path), /not a socket/);
  } finally {
    rmSync(root, {recursive: true, force: true});
  }
});
