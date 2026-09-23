export type GamingPlayableTemplate = "merge" | "match" | "sort";
export type PlayablePlanningModel = "gemini-3.8-flash" | "gemini-3.1-pro-preview";

export interface PlayableSchema {
  schemaVersion: 1;
  /** The renderer used for the saved source contract, not a delivery approval. */
  runtime: "web-v1" | "phaser-preview-v1";
  metadata: { title: string; ctaLabel: string; orientation: "portrait" | "landscape"; brief?: string; planningModel?: PlayablePlanningModel };
  assets: { backgroundDataUri?: string; referenceAssetIds?: string[]; referenceNames?: string[] };
  gameplay: {
    template: GamingPlayableTemplate;
    accentColor: string;
    targetValue: number;
    tutorialText: string;
  };
}

export interface PlayablePreflight {
  byteSize: number;
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export type PlayableTemplateVisibility = "private" | "workspace" | "community";

export interface PlayableProjectRecord {
  project_id: string;
  workspace_id: string;
  owner_user_id: string;
  title: string;
  schema: PlayableSchema;
  source_template_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlayableTemplateRecord {
  template_id: string;
  workspace_id: string;
  owner_user_id: string;
  owner_name: string;
  title: string;
  description: string;
  visibility: PlayableTemplateVisibility;
  category: string;
  version: number;
  schema: PlayableSchema;
  asset_policy: "slots_only";
  favorite_count: number;
  fork_count: number;
  is_favorited: boolean;
  created_at: string;
  updated_at: string;
}

const PLAYABLE_API_BASE = "/api/incept";

async function playableApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${PLAYABLE_API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const body = await response.json().catch(() => null) as { detail?: string } | T | null;
  if (!response.ok) {
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : "GamingPlayable request failed.");
  }
  return body as T;
}

export function savePlayableProject(input: {
  workspaceId: string;
  projectId?: string | null;
  title: string;
  schema: PlayableSchema;
  sourceTemplateId?: string | null;
}) {
  return playableApi<PlayableProjectRecord>("/playable-projects", {
    method: "POST",
    body: JSON.stringify({
      workspace_id: input.workspaceId,
      project_id: input.projectId || null,
      title: input.title,
      schema: input.schema,
      source_template_id: input.sourceTemplateId || null,
    }),
  });
}

export function listPlayableProjects(workspaceId: string) {
  return playableApi<PlayableProjectRecord[]>(`/playable-projects?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function getPlayableProject(projectId: string) {
  return playableApi<PlayableProjectRecord>(`/playable-projects/${encodeURIComponent(projectId)}`);
}

export function listPlayableTemplates(workspaceId: string) {
  return playableApi<PlayableTemplateRecord[]>(`/playable-templates?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function createPlayableTemplate(input: {
  workspaceId: string;
  title: string;
  description: string;
  visibility: Exclude<PlayableTemplateVisibility, "community">;
  category: string;
  schema: PlayableSchema;
}) {
  return playableApi<PlayableTemplateRecord>("/playable-templates", {
    method: "POST",
    body: JSON.stringify({
      workspace_id: input.workspaceId,
      title: input.title,
      description: input.description,
      visibility: input.visibility,
      category: input.category,
      schema: input.schema,
    }),
  });
}

export function togglePlayableTemplateFavorite(templateId: string) {
  return playableApi<PlayableTemplateRecord>(`/playable-templates/${encodeURIComponent(templateId)}/favorite`, { method: "POST" });
}

export function forkPlayableTemplate(templateId: string, title?: string) {
  return playableApi<PlayableProjectRecord>(`/playable-templates/${encodeURIComponent(templateId)}/fork`, {
    method: "POST",
    body: JSON.stringify({ title: title || null }),
  });
}

export const PLAYABLE_TEMPLATES: Array<{
  id: GamingPlayableTemplate;
  name: string;
  description: string;
  accent: string;
  defaultInstruction: string;
}> = [
  { id: "merge", name: "Merge Garden", description: "Combine matching pieces until you reach the reward tile.", accent: "#138a72", defaultInstruction: "Tap two matching pieces to merge them" },
  { id: "match", name: "Match & Bloom", description: "Find every pair to clear the board and reveal the reward.", accent: "#6f4df6", defaultInstruction: "Find every matching pair" },
  { id: "sort", name: "Color Sort", description: "Pair each color correctly to complete the quick challenge.", accent: "#e14b78", defaultInstruction: "Match the colors to clear the board" },
];

const escapeHtml = (value: string) => value.replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character] || character);

/**
 * Browser-side first gate. The API repeats these checks before a final
 * production export; keeping this here gives the creator immediate feedback.
 */
export function preflightPlayable(html: string): PlayablePreflight {
  const lowered = html.toLowerCase();
  const errors: string[] = [];
  const warnings: string[] = [];
  const byteSize = new Blob([html], { type: "text/html" }).size;
  if (byteSize >= 5 * 1024 * 1024) errors.push("The final HTML exceeds Moloco's 5 MB limit.");
  if (lowered.includes("xmlhttprequest")) errors.push("XMLHttpRequest is not allowed.");
  if (lowered.includes("mraid.js")) errors.push("mraid.js is not allowed.");
  if (/\bfetch\s*\(/.test(lowered) || lowered.includes("websocket")) errors.push("Network APIs are not allowed in a standalone playable.");
  if (!/fbplayablead\.onctaclick\s*\(\s*\)/.test(lowered)) errors.push("CTA must call FbPlayableAd.onCTAClick() without parameters.");
  if (!/<meta\s+name=["']viewport["']/.test(lowered)) errors.push("A responsive viewport meta tag is required.");
  if (/<(?:script|img|audio|video|link)[^>]+(?:src|href)=["'](?:https?:)?\/\//.test(lowered)) errors.push("External asset URLs are not allowed.");
  if (!lowered.includes("data:")) warnings.push("No embedded artwork is present; this is a code-only playable.");
  return { byteSize, valid: errors.length === 0, errors, warnings };
}

export function buildStandalonePlayable(schema: PlayableSchema): string {
  const template = PLAYABLE_TEMPLATES.find((item) => item.id === schema.gameplay.template) || PLAYABLE_TEMPLATES[0];
  const title = escapeHtml(schema.metadata.title || "Game Quest");
  const cta = escapeHtml(schema.metadata.ctaLabel || "Play now");
  const instruction = escapeHtml(schema.gameplay.tutorialText || template.defaultInstruction);
  const accent = schema.gameplay.accentColor || template.accent;
  const goal = Math.max(4, Math.min(64, Math.round(schema.gameplay.targetValue || 16)));
  const backgroundStyle = schema.assets.backgroundDataUri
    ? `background-image:linear-gradient(180deg,rgba(255,255,255,.12),rgba(7,30,24,.66)),url('${schema.assets.backgroundDataUri}');background-size:cover;background-position:center;`
    : "";
  const icons = schema.gameplay.template === "sort" ? ["🟣", "🟢", "🟠", "🔵"] : schema.gameplay.template === "match" ? ["🌷", "🌼", "🍓", "🪻"] : ["🌱", "🌼", "🌻", "🌳"];
  // Store the editable source contract in the delivery file. This gives a
  // future importer a safe, versioned recovery point without a second sidecar.
  const schemaJson = JSON.stringify(schema).replace(/</g, "\\u003c");

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>${title}</title><script type="application/json" id="linglong-playable-schema">${schemaJson}</script><style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html,body{margin:0;width:100%;height:100%;overflow:hidden;font-family:Arial,sans-serif;background:#102a22;color:#fff}body{display:grid;place-items:center}.game{position:relative;width:min(100vw,56.25vh);height:min(177.78vw,100vh);min-width:320px;max-width:540px;overflow:hidden;background:linear-gradient(160deg,#0f766e,#d9f99d);${backgroundStyle}}@media (orientation:landscape){.game{width:min(100vw,177.78vh);height:min(56.25vw,100vh);min-width:0;max-width:none}}.shade{position:absolute;inset:0;background:linear-gradient(180deg,#06291c20,#06291cdc)}.safe{position:relative;height:100%;padding:max(16px,env(safe-area-inset-top)) 18px max(18px,env(safe-area-inset-bottom));display:flex;flex-direction:column}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;font-weight:800}.brand{max-width:58%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:18px}.pill{border-radius:999px;background:#ffffffdc;color:#17362b;padding:7px 10px;font-size:11px}.instruction{margin:12px 0;border-radius:16px;background:#ffffffdc;color:#17362b;padding:11px;text-align:center;font-size:14px;font-weight:800}.board{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:auto 0 18px}.tile{aspect-ratio:1;border:0;border-radius:19px;background:#fff;color:#14362a;box-shadow:0 7px 0 #00000025,0 12px 22px #00000024;font-size:clamp(25px,8vw,43px);font-weight:900;cursor:pointer;transition:transform .13s ease,outline .13s ease}.tile:active{transform:scale(.93)}.tile.selected{outline:4px solid ${accent};transform:translateY(-3px)}.tile.done{opacity:.2;transform:scale(.8);pointer-events:none}.footer{margin-top:auto}.cta{width:100%;border:0;border-radius:18px;background:${accent};padding:16px;color:#fff;font-size:17px;font-weight:900;box-shadow:0 8px 20px #00000048;cursor:pointer}.hint{margin:10px 0 0;text-align:center;font-size:11px;color:#ffffffcc}.result{position:absolute;inset:0;display:none;place-items:center;padding:28px;text-align:center;background:#06291cec}.result.show{display:grid}.result-card{max-width:290px;border-radius:28px;background:#fff;color:#17362b;padding:28px 22px;box-shadow:0 18px 48px #0000004d}.result h1{margin:0;font-size:30px}.result p{line-height:1.45;color:#496050}.next{border:0;border-radius:14px;background:${accent};padding:13px 20px;color:#fff;font-weight:900;cursor:pointer}</style></head>
<body><main class="game" role="application" aria-label="${title}"><div class="shade"></div><div class="safe"><div class="top"><div class="brand">${title}</div><div class="pill">Level <span id="level">1</span> · <span id="moves">0</span> moves</div></div><div class="instruction">${instruction}</div><div class="board" id="board"></div><div class="footer"><button class="cta" id="cta" type="button">${cta}</button><p class="hint">Interactive demo · no network requests</p></div></div><section class="result" id="result" aria-live="polite"><div class="result-card"><h1>Nice move!</h1><p>You unlocked the reward. Keep playing, or get the full game now.</p><button class="next" id="next" type="button">Next level</button></div></section></main><script>
window.FbPlayableAd=window.FbPlayableAd||{onCTAClick:function(){}};(function(){var mode=${JSON.stringify(schema.gameplay.template)},goal=${goal},icons=${JSON.stringify(icons)},board=document.getElementById('board'),level=1,moves=0,selected=null,cleared=0,values=[];function shuffle(a){for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),x=a[i];a[i]=a[j];a[j]=x}return a}function render(){selected=null;cleared=0;moves=0;document.getElementById('moves').textContent=moves;document.getElementById('level').textContent=level;board.innerHTML='';values=[];for(var i=0;i<8;i++)values.push(i%4);shuffle(values);values.forEach(function(value){var tile=document.createElement('button');tile.type='button';tile.className='tile';tile.dataset.value=String(value);tile.textContent=mode==='merge'?String(Math.pow(2,value+1)):icons[value];tile.addEventListener('click',function(){if(tile.classList.contains('done')||selected===tile)return;moves++;document.getElementById('moves').textContent=moves;if(!selected){selected=tile;tile.classList.add('selected');return}var match=selected.dataset.value===tile.dataset.value;if(match){selected.classList.remove('selected');selected.classList.add('done');tile.classList.add('done');cleared+=2;selected=null;if(mode==='merge'&&Number(tile.textContent)<goal){tile.classList.remove('done');tile.textContent=String(Number(tile.textContent)*2);tile.dataset.value=String(Number(tile.dataset.value)+1);cleared=Math.max(0,cleared-2)}if(cleared>=8||mode==='merge'&&Array.prototype.some.call(board.children,function(node){return Number(node.textContent)>=goal})){window.setTimeout(function(){document.getElementById('result').classList.add('show')},250)}}else{selected.classList.remove('selected');selected=null}});board.appendChild(tile)})}document.getElementById('next').addEventListener('click',function(){level++;document.getElementById('result').classList.remove('show');render()});document.getElementById('cta').addEventListener('click',function(){window.FbPlayableAd.onCTAClick()});render()})();
</script></body></html>`;
}
