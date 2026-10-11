import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('./researchChoiceCard.vue', import.meta.url), 'utf8');
const handler = source.slice(source.indexOf('async function submit('), source.indexOf('</script>'));
const javascript = ts.transpileModule(handler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;

function fixture(selected = '', request?: () => Promise<unknown>) {
  const calls: Array<Record<string, unknown>> = [], resumed: unknown[][] = [];
  const submitting = { value: false }, error = { value: '' }, choice = { value: selected }, notes = { value: 'US market' };
  const props = { disabled: false, directory: 'project', sessionFile: 'session.jsonl', question: { id: 'question' } };
  const axios = { isAxiosError: () => false, post: async (_url: string, body: Record<string, unknown>) => {
    calls.push(body);
    return request ? await request() : { data: { code: 200, data: { questionId: 'question', prompt: 'original task' } } };
  } };
  const submit = new Function('props', 'choice', 'notes', 'submitting', 'error', 'axios', 't', 'emit', `${javascript}; return submit;`)(
    props, choice, notes, submitting, error, axios, (_zh: string, en: string) => en, (...args: unknown[]) => resumed.push(args),
  );
  return { submit, calls, resumed, submitting, error, choice };
}

test('no selection cannot authorize or resume research', async () => {
  const state = fixture();
  await state.submit(false);
  assert.equal(state.calls.length, 0);
  assert.equal(state.resumed.length, 0);
});

test('skip explicitly submits off, with project/session/question identity', async () => {
  const state = fixture('deep');
  await state.submit(true);
  assert.deepEqual(state.calls[0], { directory:'project', sessionFile:'session.jsonl', callId:'question', choice:'off', skipped:true, notes:'US market' });
  assert.deepEqual(state.resumed, [['resume', 'question', 'original task']]);
});

test('failed confirmation preserves the choice and cannot start research', async () => {
  const state = fixture('light', async () => { throw new Error('test failure'); });
  await state.submit(false);
  assert.equal(state.choice.value, 'light');
  assert.equal(state.resumed.length, 0);
  assert.equal(state.submitting.value, false);
  assert.match(state.error.value, /Could not submit/);
});

test('concurrent submit clicks send one confirmation and one resume', async () => {
  let release!: (value: unknown) => void;
  const promise = new Promise(resolve => { release = resolve; });
  const state = fixture('light', () => promise);
  const first = state.submit(false);
  await state.submit(false);
  assert.equal(state.calls.length, 1);
  release({ data: { code:200, data:{ questionId:'question', prompt:'original task' } } });
  await first;
  assert.equal(state.resumed.length, 1);
});
