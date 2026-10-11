import assert from 'node:assert/strict';
import test from 'node:test';
import { uiPhraseEntries, dynamicUiTranslations } from './i18nCatalog.ts';

const phrases = new Map<string, string>(uiPhraseEntries);
test('canvas arrangement controls have English equivalents', () => {
  for (const label of ['排列', '水平排列', '垂直排列', '网格排列'])
    assert.ok(phrases.get(label) && !/[\u3400-\u9fff]/u.test(phrases.get(label)!));
});
test('document split and search status fragments have English equivalents', () => {
  for (const label of ['重新载入', '单窗', '左右分屏', '上下分屏', '/ 12 个标签', '已检查', '个文件，', '个文件匹配。', '处）'])
    assert.ok(phrases.get(label) && !/[\u3400-\u9fff]/u.test(phrases.get(label)!));
  const translateDynamic = (text: string) => dynamicUiTranslations.reduce((value, [pattern, replacement]) => value.replace(pattern, replacement), text);
  assert.equal(translateDynamic('已检查 21 个文件，3 个文件匹配。'), 'Inspected 21 files; 3 files matched.');
  assert.equal(translateDynamic('（4 处）'), '(4 matches)');
  assert.equal(translateDynamic('2 / 12 个标签'), '2 / 12 tabs');
});
test('image editing controls have English equivalents', () => {
  for (const label of ['画笔 / 文字标记', '宫格切分', '局部重绘', '绘制工具', '画笔', '橡皮擦', '文字', '矩形', '标记颜色', '画笔大小（像素）', '清空标记'])
    assert.ok(phrases.get(label) && !/[\u3400-\u9fff]/u.test(phrases.get(label)!));
});
