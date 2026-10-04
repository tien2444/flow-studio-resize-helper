import assert from 'node:assert/strict';
import test from 'node:test';
import {
  detectHelperPlatform,
  HELPER_DOWNLOADS,
  helperDownload,
} from '../web/lib/studio/helper-platform.ts';

test('helper installer follows the browser operating system', () => {
  assert.equal(detectHelperPlatform('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'), 'windows');
  assert.equal(detectHelperPlatform('Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)'), 'mac');
  assert.equal(detectHelperPlatform('Mozilla/5.0 (X11; Linux x86_64)'), 'other');
  assert.equal(helperDownload('windows'), HELPER_DOWNLOADS.windows);
  assert.equal(helperDownload('mac'), HELPER_DOWNLOADS.mac);
});
