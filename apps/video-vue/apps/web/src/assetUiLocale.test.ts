import assert from 'node:assert/strict';
import test from 'node:test';
import { assetUiEnglish } from './assetUiLocale.ts';
import { attachmentWarnings } from './components/agent/conversationInput.ts';

test('website asset controls, upload help and safety notices have English copy', () => {
  for (const source of ['客户网站素材', '客户网站素材 · 图片 / 视频 / Logo',
    '导入选中素材', '交给Agent', '授权待确认', '导入后可预览',
    '松开添加图片或视频 · 不会自动发送', '每条消息最多添加 20 个附件',
    '已添加到当前Agent输入框；不会自动发送。', '视频不能超过 450 MB；其他工作区文件不能超过 500 MiB。']) {
    const result = assetUiEnglish(source);
    assert.notEqual(result, source);
    assert.doesNotMatch(result, /[\p{Script=Han}]/u);
  }
});
test('dynamic upload and discovery messages retain filenames, counts and HTTP codes', () => {
  assert.equal(assetUiEnglish('客户图.pdf：只支持图片和视频文件'), '客户图.pdf: Only image and video files are supported');
  assert.equal(assetUiEnglish('检查了3个页面，发现目录共12项。'), 'Inspected 3 pages; 12 assets in the catalog.');
  assert.equal(assetUiEnglish('素材返回HTTP 403；未跟随重定向或绕过访问限制'), 'Asset returned HTTP 403; redirects and access restrictions were not bypassed');
  assert.match(assetUiEnglish('客户.mp4：视频不能为空且不能超过 450 MB（450,000,000 字节） 上传限额'), /^客户.mp4: Video/);
  assert.equal(assetUiEnglish('客户网站素材.pdf：只支持图片和视频文件'), '客户网站素材.pdf: Only image and video files are supported');
  assert.equal(assetUiEnglish('客户网站素材：未通过CTV交付技术检查（源素材可继续用于剪辑）。交付格式必须为MP4；视频超过450MB'), '客户网站素材: Failed CTV delivery technical checks (source material can still be edited). Delivery format must be MP4; Video exceeds 450MB');
});
test('CTV results translate system text without rewriting customer content', () => {
  assert.equal(assetUiEnglish('交付格式必须为MP4'), 'Delivery format must be MP4');
  assert.equal(assetUiEnglish('客户网站素材 2026 原始名称'), '客户网站素材 2026 原始名称');
  assert.equal(assetUiEnglish('保护客户的车内饰'), '保护客户的车内饰');
});

test('combined media warnings and multiple upload errors are fully localized', () => {
  for (const provider of ['google-vertex-ai', 'openai', 'anthropic', 'unknown']) {
    const warnings = attachmentWarnings(provider, [{name:'图.png',mimeType:'image/png'}, {name:'片.mp4',mimeType:'video/mp4'}]);
    assert.doesNotMatch(assetUiEnglish(warnings.join(' ')), /[\p{Script=Han}]/u);
  }
  assert.equal(assetUiEnglish('a.pdf：只支持图片和视频文件；b.pdf：只支持图片和视频文件'),
    'a.pdf: Only image and video files are supported; b.pdf: Only image and video files are supported');
});
