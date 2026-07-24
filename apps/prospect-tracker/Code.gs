// ── Config ────────────────────────────────────────────────────────────────────
const CONFIG = {
  SHEET_ID: '1rvCbRwiso69lAHZh4ns_rzjlBRFteJRYtmIAri3zplQ',
  BQ_PROJECT: 'ads-bpd-guard-sandbox',
  BQ_DATASET: 'supply_smb',
  MAIN_SHEET: 'demand & supply co-win list',
  AGENCY_SHEET: 'Agency List',
  EXCLUDE_PLATFORMS: ['MADHOUSE', 'BLUVISION'],
};

// Column indices (0-based) — matches current sheet layout as of the "Gatherone Sales"
// column insertion (2026-07). If columns are added/removed/reordered again, update
// this map to match the sheet's actual header row before using the tool.
// LAUNCH_STATUS / LAUNCH_CHECKED_AT need their header columns ("Launch Status",
// "Launch Checked At") added to the sheet before running checkLaunchStatus().
const C = {
  COMPANY: 0, PUBLISHER: 1, CHINA_ENTITY: 2, BACKGROUND: 3,
  BASE: 4, TEAM_ROUTING: 5, STAGE: 6, SALES_GM: 7,
  GATHERONE: 8, GATHERONE_SALES: 9, MOLOCO_HIST: 10, STATUS: 11,
  ROUTING_NOTE: 12, AGENCY_NOTE: 13, DEMAND_PRI: 14,
  SUPPLY_PRI: 15, WEBSITE: 16, BUNDLE: 17,
  UPDATED_BY: 18, UPDATED_AT: 19,
  LAUNCH_STATUS: 20, LAUNCH_CHECKED_AT: 21,
};

// ── Entry point ────────────────────────────────────────────────────────────────
function doGet() {
  return HtmlService.createTemplateFromFile('index')
    .evaluate()
    .setTitle('Supply SMB · Prospect Tracker')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// ── Data reads ────────────────────────────────────────────────────────────────
function getCompanies() {
  const sheet = SpreadsheetApp.openById(CONFIG.SHEET_ID)
    .getSheetByName(CONFIG.MAIN_SHEET);
  if (!sheet) return [];
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];

  return data.slice(1)
    .filter(r => r[C.COMPANY])
    .map((r, i) => ({
      rowIndex:       i + 2,
      company_name:   String(r[C.COMPANY]   || ''),
      publisher_name: String(r[C.PUBLISHER] || ''),
      china_entity:   String(r[C.CHINA_ENTITY] || ''),
      background:     String(r[C.BACKGROUND]   || ''),
      base:           String(r[C.BASE]         || ''),
      team_routing:   String(r[C.TEAM_ROUTING] || ''),
      stage:          String(r[C.STAGE]        || 'New').trim(),
      sales_gm:       String(r[C.SALES_GM]     || ''),
      is_gatherone:   _cleanGatherone(r[C.GATHERONE]),
      gatherone_sales: String(r[C.GATHERONE_SALES] || ''),
      moloco_history: String(r[C.MOLOCO_HIST]  || ''),
      status:         String(r[C.STATUS]       || 'Identified').trim(),
      routing_note:   String(r[C.ROUTING_NOTE] || ''),
      agency_note:    String(r[C.AGENCY_NOTE]  || ''),
      demand_priority: String(r[C.DEMAND_PRI]  || ''),
      supply_priority: String(r[C.SUPPLY_PRI]  || ''),
      website:        String(r[C.WEBSITE]      || ''),
      bundle:         String(r[C.BUNDLE]       || ''),
      updated_by:     String(r[C.UPDATED_BY]   || ''),
      updated_at:     r[C.UPDATED_AT] instanceof Date
        ? r[C.UPDATED_AT].toISOString().split('T')[0] : '',
      launch_status:      String(r[C.LAUNCH_STATUS] || ''),
      launch_checked_at:  r[C.LAUNCH_CHECKED_AT] instanceof Date
        ? r[C.LAUNCH_CHECKED_AT].toISOString().split('T')[0] : '',
    }));
}

function _cleanGatherone(val) {
  const s = String(val || '');
  if (s.toLowerCase() === 'yes') return 'Yes';
  if (s.toLowerCase() === 'no')  return 'No';
  if (s.startsWith('='))         return 'No'; // formula not yet manually set
  return 'No';
}

// ── Data writes ───────────────────────────────────────────────────────────────
function saveAnnotation(rowIndex, data) {
  const sheet = SpreadsheetApp.openById(CONFIG.SHEET_ID)
    .getSheetByName(CONFIG.MAIN_SHEET);
  const email = Session.getActiveUser().getEmail() || 'unknown';
  const now = new Date();

  const updates = [
    [C.STAGE + 1,       data.stage],
    [C.SALES_GM + 1,    data.sales_gm],
    [C.GATHERONE + 1,   data.is_gatherone],
    [C.STATUS + 1,      data.status],
    [C.AGENCY_NOTE + 1, data.agency_note],
    [C.UPDATED_BY + 1,  email],
    [C.UPDATED_AT + 1,  now],
  ];
  updates.forEach(([col, val]) => sheet.getRange(rowIndex, col).setValue(val));

  return { success: true, updated_by: email, updated_at: now.toISOString().split('T')[0] };
}

// ── Agency list export ────────────────────────────────────────────────────────
// SAFETY GUARD (2026-07): the "Agency List" tab was manually redesigned with extra
// columns (Onboarding Bonus, GatherOne销售, 是否有增加Bundle, 备注拓展情况) that this
// function does not know how to preserve. Overwriting it would destroy that manual
// work, so this function now refuses to run until it's rebuilt to merge instead of
// clear+replace. Re-enable only after confirming the intended column layout.
function generateAgencyList() {
  return {
    error: 'Agency List tab was manually redesigned with extra columns — export disabled ' +
           'to avoid wiping that data. Ask for the export logic to be rebuilt to match the ' +
           'new layout before re-enabling.',
    count: 0,
  };
}

function generateAgencyList_DISABLED_seeGuardAbove(ORIGINAL_ARGS_UNUSED) {
  const ss = SpreadsheetApp.openById(CONFIG.SHEET_ID);
  const mainSheet   = ss.getSheetByName(CONFIG.MAIN_SHEET);
  let agencySheet   = ss.getSheetByName(CONFIG.AGENCY_SHEET);
  if (!agencySheet) agencySheet = ss.insertSheet(CONFIG.AGENCY_SHEET);

  const data = mainSheet.getDataRange().getValues().slice(1);

  const filtered = data.filter(r => {
    if (!r[C.COMPANY]) return false;
    const isYes     = String(r[C.GATHERONE]).toLowerCase() === 'yes';
    const hist      = String(r[C.MOLOCO_HIST] || '').toUpperCase();
    const notExcl   = !CONFIG.EXCLUDE_PLATFORMS.some(p => hist.includes(p));
    const notBoard  = r[C.STATUS] !== 'Onboarded';
    return isYes && notExcl && notBoard;
  });

  const headers = [
    'Company Name', 'Publisher', 'China Entity', 'Base',
    'Team', 'Stage Type', 'Sales/GM', 'Demand Priority',
    'Website', 'Bundle',
  ];
  const rows = filtered.map(r => [
    r[C.COMPANY], r[C.PUBLISHER], r[C.CHINA_ENTITY], r[C.BASE],
    r[C.TEAM_ROUTING], r[C.STAGE], r[C.SALES_GM], r[C.DEMAND_PRI],
    r[C.WEBSITE], r[C.BUNDLE],
  ]);

  agencySheet.clearContents();
  agencySheet.getRange(1, 1, 1, headers.length)
    .setValues([headers])
    .setFontWeight('bold')
    .setBackground('#1B2B4B')
    .setFontColor('#FFFFFF');
  if (rows.length > 0) {
    agencySheet.getRange(2, 1, rows.length, headers.length).setValues(rows);
  }
  agencySheet.autoResizeColumns(1, headers.length);

  return { count: rows.length };
}

// ── BQ sync (pull new companies) ──────────────────────────────────────────────
// Requires BigQuery Advanced Service enabled in Apps Script:
//   Extensions → Apps Script → Services → BigQuery API
function syncFromBQ() {
  const sql = `
    SELECT
      company_name, publisher_name,
      chinese_entity, company_background,
      hq_country, team_routing,
      best_priority,
      CASE WHEN any_moloco_supply THEN 'SMB' ELSE '' END AS supply_priority,
      website, app_bundles,
      CASE WHEN moloco_platform_id IS NOT NULL THEN moloco_platform_id ELSE '' END AS moloco_platform_id
    FROM \`${CONFIG.BQ_PROJECT}.${CONFIG.BQ_DATASET}.cold_prospect_company\`
    WHERE company_name IS NOT NULL
    ORDER BY total_downloads DESC
    LIMIT 500
  `;

  let result;
  try {
    result = BigQuery.Jobs.query(
      { query: sql, useLegacySql: false, timeoutMs: 30000 },
      CONFIG.BQ_PROJECT
    );
  } catch (e) {
    return { error: 'BigQuery call failed: ' + e.message, added: 0 };
  }

  if (!result.rows) return { added: 0, skipped: 0 };

  const sheet = SpreadsheetApp.openById(CONFIG.SHEET_ID)
    .getSheetByName(CONFIG.MAIN_SHEET);
  const lastRow = sheet.getLastRow();
  const existingSet = new Set(
    lastRow > 1
      ? sheet.getRange(2, C.COMPANY + 1, lastRow - 1, 1)
          .getValues().flat().filter(Boolean).map(String)
      : []
  );

  const newRows = [];
  result.rows.forEach(({ f }) => {
    const v = f.map(x => x.v ?? '');
    const name = v[0];
    if (!name || existingSet.has(name)) return;
    newRows.push([
      name,          // COMPANY
      v[1],          // PUBLISHER
      v[2] || '',    // CHINA_ENTITY
      v[3] || '',    // BACKGROUND
      v[4] || '',    // BASE (hq_country)
      v[5] || '',    // TEAM_ROUTING
      'New',         // STAGE (default)
      '',            // SALES_GM (human fills)
      'No',          // GATHERONE (human fills)
      '',            // GATHERONE_SALES (human fills)
      v[10] || '',   // MOLOCO_HIST (platform_id)
      'Identified',  // STATUS (default)
      '',            // ROUTING_NOTE
      '',            // AGENCY_NOTE
      v[6] || '',    // DEMAND_PRI (best_priority)
      v[7] || '',    // SUPPLY_PRI
      v[8] || '',    // WEBSITE
      v[9] || '',    // BUNDLE (app_bundles)
    ]);
    existingSet.add(name);
  });

  if (newRows.length > 0) {
    sheet.getRange(sheet.getLastRow() + 1, 1, newRows.length, newRows[0].length)
      .setValues(newRows);
  }

  return { added: newRows.length, skipped: result.rows.length - newRows.length };
}

// ── Launch check (weekly) ──────────────────────────────────────────────────────
// For every row's bundle(s), check fact_dsp_core for gross spend in the last 7
// days. Any spend on any of the row's bundles → "Launched"; none → "Not Onboard".
function checkLaunchStatus() {
  const sheet = SpreadsheetApp.openById(CONFIG.SHEET_ID)
    .getSheetByName(CONFIG.MAIN_SHEET);
  const data = sheet.getDataRange().getValues();
  if (data.length < 2) return { checked: 0, launched: 0 };

  const rowBundles = [];   // [{ rowIndex, bundles: [...] }]
  const allBundles = new Set();

  data.slice(1).forEach((r, i) => {
    if (!r[C.COMPANY]) return;
    const bundles = String(r[C.BUNDLE] || '')
      .split(',')
      .map(b => b.trim())
      .filter(Boolean);
    if (!bundles.length) return;
    rowBundles.push({ rowIndex: i + 2, bundles });
    bundles.forEach(b => allBundles.add(b));
  });

  if (!allBundles.size) return { checked: 0, launched: 0 };

  let spendMap;
  try {
    spendMap = _queryFactDspCoreSpend(Array.from(allBundles));
  } catch (e) {
    return { error: 'BigQuery call failed: ' + e.message, checked: 0, launched: 0 };
  }

  const now = new Date();
  let launchedCount = 0;

  rowBundles.forEach(({ rowIndex, bundles }) => {
    const isLaunched = bundles.some(b => spendMap.has(b));
    if (isLaunched) launchedCount++;
    sheet.getRange(rowIndex, C.LAUNCH_STATUS + 1).setValue(isLaunched ? 'Launched' : 'Not Onboard');
    sheet.getRange(rowIndex, C.LAUNCH_CHECKED_AT + 1).setValue(now);
  });

  return { checked: rowBundles.length, launched: launchedCount };
}

// Batched to stay well under BigQuery's query text size limits.
function _queryFactDspCoreSpend(bundles) {
  const spendMap = new Map();
  const BATCH = 300;

  for (let i = 0; i < bundles.length; i += BATCH) {
    const batch = bundles.slice(i, i + BATCH);
    const inList = batch.map(b => `'${b.replace(/'/g, "\\'")}'`).join(',');
    const sql = `
      SELECT
        product.app_market_bundle AS bundle,
        SUM(gross_spend_usd) AS gross_spend_usd_7d
      FROM \`ads-bpd-guard-china.athena.fact_dsp_core\`
      WHERE date_utc >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        AND product.app_market_bundle IN (${inList})
      GROUP BY 1
      HAVING gross_spend_usd_7d > 0
    `;
    const result = BigQuery.Jobs.query(
      { query: sql, useLegacySql: false, timeoutMs: 30000 },
      CONFIG.BQ_PROJECT
    );
    (result.rows || []).forEach(({ f }) => {
      const bundle = f[0].v;
      if (bundle) spendMap.set(bundle, parseFloat(f[1].v) || 0);
    });
  }

  return spendMap;
}

// Run once from the Apps Script editor (select this function → Run) to install
// the weekly trigger. Re-running is safe — it clears any prior trigger first.
function installWeeklyLaunchCheckTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'checkLaunchStatus')
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('checkLaunchStatus')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(6)
    .create();

  log_('Weekly launch-check trigger installed: every Monday ~06:00');
}

function log_(msg) {
  Logger.log(msg);
}
