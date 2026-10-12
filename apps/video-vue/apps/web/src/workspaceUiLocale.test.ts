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
test('document download and tab closing controls translate full labels', () => {
  assert.equal(phrases.get('下载副本'), 'Download a copy');
  assert.equal(phrases.get('编辑图片'), 'Edit image');
  const close = dynamicUiTranslations.reduce((value, [pattern, replacement]) => value.replace(pattern, replacement), '关闭 客户 brief.md');
  assert.equal(close, 'Close 客户 brief.md');
});
test('dynamic node port descriptions translate chrome and retain the type signature', () => {
  const translate = (text: string) => dynamicUiTranslations.reduce((value, [pattern, replacement]) => value.replace(pattern, replacement), text);
  assert.equal(translate('图片、文本输入 · IMAGE / STRING'), 'Image and text input · IMAGE / STRING');
  assert.equal(translate('图片输出 · IMAGE'), 'Image output · IMAGE');
  assert.equal(translate('图片、视频、音频、文本输入 · IMAGE / VIDEO / AUDIO / STRING'), 'Image, video, audio, and text input · IMAGE / VIDEO / AUDIO / STRING');
  assert.equal(translate('视频、图片、文本输入 · VIDEO / IMAGE / STRING'), 'Video, image, and text input · VIDEO / IMAGE / STRING');
  assert.equal(translate('文本、图片、视频输入 · STRING / IMAGE / VIDEO'), 'Text, image, and video input · STRING / IMAGE / VIDEO');
  assert.equal(translate('视频输出 · VIDEO'), 'Video output · VIDEO');
  assert.equal(translate('音频输出 · AUDIO'), 'Audio output · AUDIO');
  assert.equal(translate('文本输出 · STRING'), 'Text output · STRING');
  assert.equal(translate('客户自定义端口 · CUSTOM'), '客户自定义端口 · CUSTOM');
});
