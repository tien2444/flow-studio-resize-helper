import assert from 'node:assert/strict';
import test from 'node:test';
import { friendlyDriveError } from '../web/lib/studio/local-processor.ts';

test('Drive rate-limit JSON is replaced with a concise recovery message', () => {
  const message = friendlyDriveError(
    'Google Drive returned HTTP 403: {"error":{"message":"User rate limit exceeded.","errors":[{"reason":"userRateLimitExceeded"}]}}',
  );
  assert.match(message, /Google Drive đang giới hạn tốc độ/);
  assert.match(message, /file vẫn an toàn trên máy/);
  assert.doesNotMatch(message, /\{"error"/);
});

test('unrelated Drive errors keep their useful detail', () => {
  assert.equal(
    friendlyDriveError('Google Drive returned HTTP 403: permission denied'),
    'Google Drive returned HTTP 403: permission denied',
  );
});
