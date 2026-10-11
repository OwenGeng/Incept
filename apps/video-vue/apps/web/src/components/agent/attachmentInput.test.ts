import assert from 'node:assert/strict';
import test from 'node:test';
import { selectAttachments } from './attachmentInput.ts';

test('accepts image/video selections in order and infers missing MIME from known extensions', () => {
  const files = [{ name: 'client.png', type: 'image/png', size: 10 }, { name: 'clip.MP4', type: '', size: 20 }];
  const result = selectAttachments(files, 0);
  assert.deepEqual(result.accepted.map(item => [item.file.name, item.mimeType]), [['client.png', 'image/png'], ['clip.MP4', 'video/mp4']]);
  assert.deepEqual(result.errors, []);
});
test('rejects unsupported, empty and oversized files without blocking valid files', () => {
  const result = selectAttachments([{ name: 'bad.pdf', type: 'application/pdf', size: 10 }, { name: 'empty.png', type: 'image/png', size: 0 }, { name: 'big.mp4', type: 'video/mp4', size: 450_000_001 }, { name: 'ok.jpg', type: 'image/jpeg', size: 100 * 1024 * 1024 }], 0);
  assert.equal(result.accepted.length, 1);
  assert.equal(result.errors.length, 3);
});
test('video admission is exactly 450 million decimal bytes while images retain 100 MiB', () => {
  const result = selectAttachments([
    { name: 'large.mp4', type: 'video/mp4', size: 450_000_000 },
    { name: 'over.mp4', type: 'video/mp4', size: 450_000_001 },
    { name: 'large.jpg', type: 'image/jpeg', size: 100 * 1024 * 1024 },
    { name: 'over.jpg', type: 'image/jpeg', size: 100 * 1024 * 1024 + 1 },
  ], 0);
  assert.deepEqual(result.accepted.map(item => item.file.name), ['large.mp4', 'large.jpg']);
  assert.ok(result.errors.some(error => error.includes('450 MB')));
  assert.ok(result.errors.some(error => error.includes('100 MiB')));
});
test('enforces the twenty-attachment limit including existing drafts', () => {
  const files = [{ name: 'one.png', type: 'image/png', size: 10 }, { name: 'two.png', type: 'image/png', size: 10 }];
  assert.equal(selectAttachments(files, 19).accepted.length, 1);
  assert.equal(selectAttachments(files, 20).accepted.length, 0);
  assert.ok(selectAttachments(files, 19).errors.some(error => error.includes('20')));
});
