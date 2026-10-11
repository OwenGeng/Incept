import assert from 'node:assert/strict';
import test from 'node:test';
import { attachmentWarnings, canReadAttachments, messagePrompt, resendMessageId, recoverDraft, cancelPayload } from './conversationInput.ts';

test('attachment-only messages send an explicit inspection request instead of an empty prompt', () => {
  assert.match(messagePrompt('', 1), /素材/);
  assert.equal(messagePrompt('  调研客户  ', 1), '调研客户');
  assert.equal(messagePrompt('', 0), '');
});
test('resend targets the edited persisted message, never a later turn', () => {
  assert.equal(resendMessageId({ id: 'persisted' }), 'persisted');
  assert.equal(resendMessageId({ id: 'local', entryId: 'persisted' }), 'persisted');
});
test('all configured providers accept images and describe analysis-copy semantics', () => {
  for (const providerId of ['google-vertex-ai', 'openai', 'anthropic']) {
    assert.equal(canReadAttachments(providerId), true);
    const warnings = attachmentWarnings(providerId, [{ name: 'image.png', mimeType: 'image/png', file: { size: 50 * 1024 * 1024 } }]).join(' ');
    assert.match(warnings, /缩放.*副本/);
    assert.doesNotMatch(warnings, /10 MiB|20 MiB|不支持|仅传文件信息/);
  }
  assert.deepEqual(attachmentWarnings('gemini', []), []);
});
test('video warnings distinguish Gemini proxy/reference from timestamped image sampling', () => {
  const video = [{ name: 'client.mp4', mimeType: 'video/mp4', file: { size: 450_000_000 } }];
  const gemini = attachmentWarnings('google-vertex-ai', video).join(' ');
  assert.match(gemini, /原生|分析副本/);
  assert.match(gemini, /私有引用/);
  for (const providerId of ['openai', 'anthropic']) {
    const warning = attachmentWarnings(providerId, video).join(' ');
    assert.match(warning, /时间戳.*采样帧/);
    assert.match(warning, /不.*音频/);
    assert.match(warning, /不.*全部帧/);
    assert.doesNotMatch(warning, /10 MiB|20 MiB|不支持/);
  }
});
test('failed uploads recover attachments without duplicate paths or losing new drafts', () => {
  assert.deepEqual(recoverDraft([{ name: 'new', path: 'new' }], [{ name: 'old', path: 'old' }, { name: 'duplicate', path: 'new' }]).map(item => item.path), ['old', 'new']);
});

test('cancel payload retains the dispatched run rather than a newly selected project', () => {
  assert.deepEqual(cancelPayload({ directory: 'project-a', sessionFile: 'session-a.json', runId: 'run-a' }), { directory: 'project-a', sessionFile: 'session-a.json', runId: 'run-a' });
  assert.equal(cancelPayload({ directory: 'project-a', sessionFile: 'session-a.json' }), undefined);
  assert.equal(cancelPayload(undefined), undefined);
});
