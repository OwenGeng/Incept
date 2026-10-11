// Translate system status only. Never rewrite model reasoning or customer content.
export function progressText(value: string, language: string) {
  if (!language.startsWith('en')) return value;
  const fixed: Record<string,string> = {
    '正在准备请求…':'Preparing request…',
    '仍在处理中，可点击停止；已发出的模型请求无法撤回。':'Still processing. You can stop; requests already sent to the model cannot be recalled.',
    '正在验证并准备客户素材；原文件保持不变。':'Validating and preparing client assets; original files remain unchanged.',
    '正在读取客户网站，核实产品信息…':'Reading the client website and checking product information…',
    '正在查找 YouTube 商品演示与竞品参考；随后核验来源并标注可观察范围。':'Finding YouTube product demos and competitor references; sources and observation limits will be checked next.',
  };
  return fixed[value] ?? value
    .replace(/^正在分析本轮请求（第 (\d+) 轮）…$/, 'Analyzing your request (round $1)…')
    .replace(/^正在准备附件：/, 'Preparing attachment: ')
    .replace(/^正在执行 (.+)…$/, 'Running $1…');
}
