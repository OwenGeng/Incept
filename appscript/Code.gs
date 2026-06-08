// ============================================================
// Supply SMB Cross-Sell Project — AppScript WebApp
// Code.gs (server-side)
// ============================================================

const SHEET_ID = '1HdI1IxlqndKNKftGWFRM7d3qeaPGUOMWXeBBsiSBJss';
const TAB_APP     = 'App Level';
const TAB_COMPANY = 'Company Level';
const TAB_CONFIG  = 'Config';
const TAB_HISTORY = 'History';
const TAB_REPORTS = 'AI Reports';

// ── Entry point ──────────────────────────────────────────────
function doGet(e) {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Supply SMB Cross-Sell Project')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function getSpreadsheet() {
  return SpreadsheetApp.openById(SHEET_ID);
}

// ── App Level data ───────────────────────────────────────────
function getAppData() {
  const sheet = getSpreadsheet().getSheetByName(TAB_APP);
  if (!sheet) return { headers: [], rows: [] };
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return { headers: data[0] || [], rows: [] };
  const headers = data[0].map(String);
  const rows = data.slice(1).map(row =>
    headers.reduce((obj, h, i) => { obj[h] = row[i]; return obj; }, {})
  );
  return { headers, rows };
}

// ── Config ───────────────────────────────────────────────────
function getConfig() {
  const ss = getSpreadsheet();
  let sheet = ss.getSheetByName(TAB_CONFIG);
  if (!sheet) {
    sheet = ss.insertSheet(TAB_CONFIG);
    _writeDefaultConfig(sheet);
  }
  const data = sheet.getDataRange().getValues();
  const config = {};
  data.slice(1).forEach(row => { if (row[0]) config[String(row[0])] = row[1]; });
  return config;
}

function saveConfig(configObj) {
  const ss = getSpreadsheet();
  let sheet = ss.getSheetByName(TAB_CONFIG);
  if (!sheet) sheet = ss.insertSheet(TAB_CONFIG);
  sheet.clearContents();
  const rows = [['key', 'value', 'description']];
  const desc = {
    dl_threshold: 'Min monthly downloads to qualify',
    p1_mc: 'P1: Moloco media cost > $ / month',
    p1_dl: 'P1: Downloads >= per month',
    p1_mom: 'P1: MoM growth > (0.1=10%)',
    p2_mc: 'P2: Moloco media cost > $ / month',
    p2_dl: 'P2: Downloads >= per month',
    p2_mom: 'P2: MoM > (-0.1=-10%)',
  };
  Object.entries(configObj).forEach(([k, v]) => rows.push([k, v, desc[k] || '']));
  sheet.getRange(1, 1, rows.length, 3).setValues(rows);
  sheet.getRange(1, 1, 1, 3).setFontWeight('bold');
  return { ok: true };
}

function _writeDefaultConfig(sheet) {
  const d = [
    ['key',          'value',   'description'],
    ['dl_threshold', 20000,    'Min monthly downloads to qualify'],
    ['p1_mc',        2000,     'P1: Moloco media cost > $ / month'],
    ['p1_dl',        100000,   'P1: Downloads >= per month'],
    ['p1_mom',       0.1,      'P1: MoM growth > (0.1=10%)'],
    ['p2_mc',        100,      'P2: Moloco media cost > $ / month (lowered for gaming)'],
    ['p2_dl',        50000,    'P2: Downloads >= per month'],
    ['p2_mom',       -0.1,     'P2: MoM > (-0.1=-10%)'],
  ];
  sheet.getRange(1, 1, d.length, 3).setValues(d);
  sheet.getRange(1, 1, 1, 3).setFontWeight('bold');
}

// ── History ──────────────────────────────────────────────────
function getHistory() {
  const sheet = getSpreadsheet().getSheetByName(TAB_HISTORY);
  if (!sheet) return [];
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  const headers = data[0].map(String);
  return data.slice(1).map(row =>
    headers.reduce((obj, h, i) => { obj[h] = row[i]; return obj; }, {})
  );
}

function saveWeeklySnapshot() {
  const ss = getSpreadsheet();
  let sheet = ss.getSheetByName(TAB_HISTORY);
  if (!sheet) {
    sheet = ss.insertSheet(TAB_HISTORY);
    sheet.appendRow(['date','p1_cos','p2_cos','p3_cos','p4_cos',
                     'p1_apps','p2_apps','p3_apps','p4_apps',
                     'total_cos','total_apps','p1_companies_list','p2_companies_list']);
    sheet.getRange(1,1,1,13).setFontWeight('bold');
  }
  const { rows } = getAppData();
  const cfg = getConfig();
  const counts = {p1:0,p2:0,p3:0,p4:0};
  const coSets = {p1:new Set(),p2:new Set(),p3:new Set(),p4:new Set()};
  rows.forEach(app => {
    const t = _classifyApp(app, cfg);
    counts[t]++;
    if (app.company_name) coSets[t].add(app.company_name);
  });
  const today = new Date().toLocaleDateString('en-US');
  sheet.appendRow([
    today,
    coSets.p1.size, coSets.p2.size, coSets.p3.size, coSets.p4.size,
    counts.p1, counts.p2, counts.p3, counts.p4,
    new Set(rows.map(r=>r.company_name).filter(Boolean)).size,
    rows.length,
    [...coSets.p1].join(' | '),
    [...coSets.p2].join(' | ')
  ]);
  return 'Snapshot saved: ' + today;
}

// ── Get stored AI report ─────────────────────────────────────
function getLatestAIReport() {
  const ss = getSpreadsheet();
  const sheet = ss.getSheetByName(TAB_REPORTS);
  if (!sheet || sheet.getLastRow() < 2) return null;
  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(lastRow, 1, 1, 3).getValues()[0];
  return { date: data[0], report: data[1], lang: data[2] };
}

// ── Generate AI report via Gemini ────────────────────────────
function generateAndSaveReport() {
  const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY');
  if (!apiKey) return { error: 'GEMINI_API_KEY not set. See setup instructions.' };

  // Gather report data
  const { rows } = getAppData();
  const cfg = getConfig();
  const history = getHistory();

  const cos = {p1:new Set(),p2:new Set(),p3:new Set(),p4:new Set()};
  const appCounts = {p1:0,p2:0,p3:0,p4:0};
  let totalMC = 0, mcCount = 0;
  const genreCount = {};

  rows.forEach(app => {
    const t = _classifyApp(app, cfg);
    appCounts[t]++;
    if (app.company_name) cos[t].add(app.company_name);
    const mc = _parseMC(app.moloco_media_cost_usd_30d);
    if (mc > 0 && (t==='p1'||t==='p2')) { totalMC += mc; mcCount++; }
    if ((t==='p1'||t==='p2') && app.genre) genreCount[app.genre] = (genreCount[app.genre]||0)+1;
  });

  const topGenre = Object.entries(genreCount).sort((a,b)=>b[1]-a[1]).slice(0,3).map(e=>e[0]).join(', ');
  const avgMC = mcCount > 0 ? Math.round(totalMC/mcCount) : 0;

  // Compare with last week
  let newCos = [], droppedCos = [];
  if (history.length >= 1) {
    const lastWeek = history[history.length-1];
    const lastP12 = new Set([
      ...(lastWeek.p1_companies_list||'').split(' | '),
      ...(lastWeek.p2_companies_list||'').split(' | ')
    ].filter(Boolean));
    const thisP12 = new Set([...cos.p1, ...cos.p2]);
    newCos = [...thisP12].filter(c => !lastP12.has(c)).slice(0,3);
    droppedCos = [...lastP12].filter(c => !thisP12.has(c)).slice(0,3);
  }

  const topCompany = [...cos.p1,...cos.p2]
    .map(name => ({ name, mc: _parseMC((rows.find(r=>r.company_name===name)||{}).moloco_media_cost_usd_30d) }))
    .sort((a,b)=>b.mc-a.mc)[0] || { name:'N/A', mc:0 };

  // Build prompt
  const prompt = `You are a business analyst writing a brief weekly summary for Moloco's sales team.
The audience is NON-TECHNICAL sales managers and agency partners who want to know what to focus on this week.

This week's data:
- Total qualifying companies: ${new Set(rows.map(r=>r.company_name)).size}
- P1 companies (highest priority, direct NBS contact): ${cos.p1.size} companies, ${appCounts.p1} apps
- P2 companies (NBS + Agency): ${cos.p2.size} companies, ${appCounts.p2} apps
- P1+P2 active follow-up total: ${cos.p1.size + cos.p2.size} companies
- New companies entered P1+P2 this week: ${newCos.length > 0 ? newCos.join(', ') : 'None'}
- Companies dropped from P1+P2: ${droppedCos.length > 0 ? droppedCos.join(', ') : 'None'}
- Average Moloco monthly spend on P1+P2 companies: $${avgMC.toLocaleString()}
- Top genres: ${topGenre}
- Top company by Moloco spend: ${topCompany.name} ($${Math.round(topCompany.mc).toLocaleString()}/month)

Key context: Moloco's DSP already PAYS these companies monthly to run ads in their apps. They just don't have an official SDK deal yet. The pitch is "we already buy your ad space, let's make it official."

Write exactly 3 sentences in plain English (no technical terms, no bullet points):
1. What the overall situation looks like this week
2. What's notable or changed vs last week
3. What the team should focus on`;

  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`;
    const payload = {
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0.3, maxOutputTokens: 300 }
    };
    const resp = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
    const json = JSON.parse(resp.getContentText());
    const text = json.candidates?.[0]?.content?.parts?.[0]?.text || 'Unable to generate report.';

    // Save to Reports sheet
    const ss = getSpreadsheet();
    let repSheet = ss.getSheetByName(TAB_REPORTS);
    if (!repSheet) {
      repSheet = ss.insertSheet(TAB_REPORTS);
      repSheet.appendRow(['date','report','generated_at']);
      repSheet.getRange(1,1,1,3).setFontWeight('bold');
    }
    const today = new Date().toLocaleDateString('en-US');
    repSheet.appendRow([today, text, new Date().toISOString()]);
    return { ok: true, report: text, date: today };
  } catch(e) {
    return { error: e.message };
  }
}

// ── Setup Gemini API key ─────────────────────────────────────
function setGeminiApiKey(key) {
  PropertiesService.getScriptProperties().setProperty('GEMINI_API_KEY', key);
  return 'API key saved.';
}

// ── Company Level data ───────────────────────────────────────
function getCompanyData() {
  const sheet = getSpreadsheet().getSheetByName(TAB_COMPANY);
  if (!sheet) return { headers: [], rows: [] };
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return { headers: data[0] || [], rows: [] };
  const headers = data[0].map(String);
  const rows = data.slice(1).map(row =>
    headers.reduce((obj, h, i) => { obj[h] = row[i]; return obj; }, {})
  );
  return { headers, rows };
}

// ── Metadata ─────────────────────────────────────────────────
function getMeta() {
  const ss = getSpreadsheet();
  const appSheet = ss.getSheetByName(TAB_APP);
  const coSheet  = ss.getSheetByName(TAB_COMPANY);
  // Use DriveApp to get last modified time — Sheet has no getLastUpdated()
  let lastRefresh = 'Unknown';
  try {
    lastRefresh = DriveApp.getFileById(SHEET_ID).getLastUpdated().toLocaleString('en-US');
  } catch(e) { /* ignore permission errors */ }
  return {
    lastRefresh,
    appRows:  appSheet ? Math.max(0, appSheet.getLastRow() - 1) : 0,
    coRows:   coSheet  ? Math.max(0, coSheet.getLastRow() - 1) : 0,
    sheetUrl: `https://docs.google.com/spreadsheets/d/${SHEET_ID}`
  };
}

// ── Weekly trigger ───────────────────────────────────────────
function setupWeeklyTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => ['saveWeeklySnapshot','generateAndSaveReport'].includes(t.getHandlerFunction()))
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('saveWeeklySnapshot').timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(9).create();
  ScriptApp.newTrigger('generateAndSaveReport').timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(9).create();
  return 'Triggers set: every Monday 9am';
}

// ── Server-side helpers ──────────────────────────────────────
function _parseMC(val) {
  if (!val && val !== 0) return 0;
  const s = String(val).replace(/[$,\s]/g,'');
  if (s.endsWith('k')||s.endsWith('K')) return parseFloat(s)*1000;
  if (s.endsWith('m')||s.endsWith('M')) return parseFloat(s)*1000000;
  return parseFloat(s)||0;
}

function _classifyApp(app, cfg) {
  const hq = String(app.final_hq_country||'').toUpperCase();
  const isCHN = ['CHN','CHINA','CN'].includes(hq);
  const sv = String(app.is_moloco_supply_visible).toUpperCase()==='TRUE';
  const mc = _parseMC(app.moloco_media_cost_usd_30d);
  const dl = parseInt(app.downloads_latest_month)||0;
  const dp = parseInt(app.downloads_prior_month)||0;
  const mom = dp>0?(dl-dp)/dp:(dl>0?1.0:0);
  const dlT = parseFloat(cfg.dl_threshold)||20000;
  if (dl<dlT) return 'p4';
  if (isCHN&&sv&&mc>(cfg.p1_mc||2000)&&dl>=(cfg.p1_dl||100000)&&mom>(cfg.p1_mom||0.1)) return 'p1';
  if (isCHN&&sv&&mc>(cfg.p2_mc||100)&&dl>=(cfg.p2_dl||50000)&&mom>(cfg.p2_mom||-0.1)) return 'p2';
  if (sv&&mc>0) return 'p3';
  return 'p4';
}
