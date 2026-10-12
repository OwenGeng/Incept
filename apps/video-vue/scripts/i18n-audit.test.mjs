import assert from 'node:assert/strict';
import test from 'node:test';
import { withoutInlineTranslations, untranslatedStaticText } from './i18n-audit.mjs';

test('a translated substring cannot hide an untranslated static control', () => {
  assert.deepEqual(untranslatedStaticText('<button>下载副本</button>', ['下载']), ['下载副本']);
  assert.deepEqual(untranslatedStaticText('<button>下载副本</button>', ['下载副本']), []);
  assert.deepEqual(untranslatedStaticText('<span>{{ document.name }}</span>', []), []);
});

test('explicit inline pairs are translated but adjacent untranslated copy remains', () => {
  assert.equal(withoutInlineTranslations("<p>{{ t('竞品调研选择', 'Reference research choice') }}</p>"), '<p>{{  }}</p>');
  assert.match(withoutInlineTranslations("{{ t('确认', 'Confirm') }} 仍未翻译"), /仍未翻译/u);
});

test('empty or Chinese fallbacks and data-no-translate do not bypass the audit', () => {
  for (const line of ["{{ t('确认', '') }}", "{{ t('确认', '确认') }}", '<p data-no-translate>确认</p>']) {
    assert.match(withoutInlineTranslations(line), /确认/u);
  }
});
