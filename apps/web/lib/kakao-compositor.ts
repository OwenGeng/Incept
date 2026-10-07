"use client";

// Kakao Bizboard, 960x300 specification (effective Oct 2026). The backend
// (apps/api/app/routers/kakao.py) renders the image; this module measures and
// validates copy with the same Pretendard font so the UI can explain errors
// before a request is sent. Limits mirror the backend layout table.

export const KAKAO_BIZBOARD_SIZE = "960x300";

export type KakaoTemplateId =
  | "APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL"
  | "APP_DOWNLOAD_TWO_LINE_COPY_THUMBNAIL"
  | "TWO_LINE_COPY_THUMBNAIL"
  | "APP_DOWNLOAD_ONE_LINE_COPY_OBJECT";

export const KAKAO_TEMPLATES: { id: KakaoTemplateId; label: string; appCopy: boolean; subCopy: boolean; object: boolean }[] = [
  { id: "APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL", label: "App Promo · Main copy", appCopy: true, subCopy: false, object: false },
  { id: "APP_DOWNLOAD_TWO_LINE_COPY_THUMBNAIL", label: "App Promo · Main + Sub copy", appCopy: true, subCopy: true, object: false },
  { id: "TWO_LINE_COPY_THUMBNAIL", label: "Sales / Traffic · Main + Sub copy", appCopy: false, subCopy: true, object: false },
  { id: "APP_DOWNLOAD_ONE_LINE_COPY_OBJECT", label: "App Promo · Main copy (Object)", appCopy: true, subCopy: false, object: true },
];

export const KAKAO_DEFAULT_TEMPLATE: KakaoTemplateId = "APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL";
export const KAKAO_DEFAULT_APP_COPY = "APP_NAME 앱에서 확인";
export const KAKAO_DEFAULT_MAIN_COPY = "APP_NAME 출시";
export const KAKAO_GACHA_INFO = "확률형 아이템 포함";

const TEXT_RIGHT = 569;
const COPY_X = 43;
const APP_COPY_X = 91;
const INFO_X = 45;
const MIN_COPY_WIDTH = 240;
const ARROW_GAP_AND_WIDTH = 9 + 10;
const APP_TERMS = ["앱", "app", "App", "APP"];
const BANNED = /\^\^|:D|ð|☞|☑|♨|[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
const PLACEHOLDER = /APP_NAME/i; // pre-filled defaults must be replaced before submitting
const FONT_FAMILY = "Pretendard";
const FONT_BASE = "/Pretendard";

export function kakaoTemplate(id: KakaoTemplateId) {
  return KAKAO_TEMPLATES.find((template) => template.id === id) ?? KAKAO_TEMPLATES[0];
}

let fontsLoaded: Promise<void> | null = null;

export function loadKakaoFonts(): Promise<void> {
  fontsLoaded ??= (async () => {
    const faces = (["Regular", "Bold"] as const).map(
      (weight) =>
        new FontFace(FONT_FAMILY, `url(${FONT_BASE}/Pretendard-${weight}.otf) format("opentype")`, {
          weight: weight === "Bold" ? "700" : "400",
        }),
    );
    await Promise.all(faces.map((face) => face.load()));
    faces.forEach((face) => document.fonts.add(face));
  })().catch((error) => {
    console.warn("Failed to load Pretendard; Kakao width checks may differ from the rendered image.", error);
  });
  return fontsLoaded;
}

function normalize(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

export function buildKakaoAppCopy(appName: string) {
  const name = normalize(appName);
  return name ? `${name} 앱에서 확인` : KAKAO_DEFAULT_APP_COPY;
}

export function buildKakaoDefaultMainCopy(appName: string) {
  const name = normalize(appName);
  return name ? `${name} 출시` : KAKAO_DEFAULT_MAIN_COPY;
}

export function buildKakaoAdditionalInfo(additionalInfo: string, gacha: boolean) {
  const info = normalize(additionalInfo);
  if (gacha && !info.includes(KAKAO_GACHA_INFO)) return info ? `${KAKAO_GACHA_INFO} · ${info}` : KAKAO_GACHA_INFO;
  return info;
}

export interface KakaoCompositeParams {
  template: KakaoTemplateId;
  thumbnailUrl: string;
  appIconUrl: string | null;
  appCopy: string;
  mainCopy: string;
  subCopy: string;
  additionalInfo: string;
  gacha: boolean;
}

export interface KakaoBizboardValidationResult {
  errors: string[];
  mainCopyWidthPx: number;
  mainCopyMaxWidthPx: number;
}

export async function validateKakaoBizboardInputs(p: KakaoCompositeParams): Promise<KakaoBizboardValidationResult> {
  await loadKakaoFonts();
  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) throw new Error("Could not create canvas context");
  const measure = (text: string, size: number, bold = false) => {
    ctx.font = `${bold ? 700 : 400} ${size}px ${FONT_FAMILY}, sans-serif`;
    return text ? ctx.measureText(text).width : 0;
  };

  const template = kakaoTemplate(p.template);
  const main = normalize(p.mainCopy);
  const sub = normalize(p.subCopy);
  const app = normalize(p.appCopy);
  const info = buildKakaoAdditionalInfo(p.additionalInfo, p.gacha);
  const maxWidth = TEXT_RIGHT - COPY_X;
  const errors: string[] = [];

  if (!p.thumbnailUrl) {
    errors.push(template.object ? "An object image is required." : "A cleaned thumbnail image is required.");
  } else if (template.object && !(await hasTransparency(p.thumbnailUrl))) {
    errors.push("Object image needs a transparent background. Remove the background or upload a transparent PNG.");
  }

  const mainWidth = measure(main, 46, true);
  if (!main) errors.push("Main copy is required.");
  else if (mainWidth > maxWidth) errors.push(`Main copy is too long (${Math.round(mainWidth)}px, max ${maxWidth}px).`);

  if (template.subCopy) {
    const subWidth = measure(sub, 38);
    if (!sub) errors.push("Sub copy is required for this template.");
    else if (subWidth > maxWidth) errors.push(`Sub copy is too long (${Math.round(subWidth)}px, max ${maxWidth}px).`);
    if (main && sub && main === sub) errors.push("Main copy and sub copy cannot be the same.");
    if (main && sub && Math.max(mainWidth, subWidth) < MIN_COPY_WIDTH) {
      errors.push(`Main copy or sub copy must be at least ${MIN_COPY_WIDTH}px wide.`);
    }
  } else if (main && mainWidth < MIN_COPY_WIDTH) {
    errors.push(`Main copy is too short (${Math.round(mainWidth)}px, min ${MIN_COPY_WIDTH}px).`);
  }

  if (template.appCopy) {
    if (!p.appIconUrl) errors.push("App icon is required for this template.");
    if (!app) errors.push("App download copy is required for this template.");
    else if (!APP_TERMS.some((term) => app.includes(term))) errors.push('App download copy must include "앱" or "App".');
    else if (APP_COPY_X + measure(app, 29) + ARROW_GAP_AND_WIDTH > TEXT_RIGHT) {
      errors.push("App download copy is too long for the fixed Bizboard slot.");
    }
  }

  if (info && INFO_X + measure(info, 22) > TEXT_RIGHT) errors.push("Additional info is too long for the fixed Bizboard slot.");

  const fields: [string, string][] = [["Main copy", main], ["Sub copy", sub], ["App download copy", app], ["Additional info", info]];
  for (const [label, text] of fields) {
    if (text && BANNED.test(text)) errors.push(`${label} contains emoji or special characters Kakao does not allow.`);
    if (text && PLACEHOLDER.test(text)) errors.push(`${label} still contains the APP_NAME placeholder. Replace it with the real app name.`);
  }

  return { errors, mainCopyWidthPx: mainWidth, mainCopyMaxWidthPx: maxWidth };
}

async function hasTransparency(url: string): Promise<boolean> {
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.src = url;
  try {
    await img.decode();
  } catch {
    return true; // Let the backend decide when the image cannot be inspected here.
  }
  const canvas = document.createElement("canvas");
  canvas.width = Math.min(img.naturalWidth, 256);
  canvas.height = Math.max(1, Math.round((canvas.width * img.naturalHeight) / img.naturalWidth));
  const ctx = canvas.getContext("2d");
  if (!ctx) return true;
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  try {
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
    for (let i = 3; i < data.length; i += 4) if (data[i] < 250) return true;
    return false;
  } catch {
    return true; // Cross-origin pixels are unreadable; the backend check still applies.
  }
}

async function toBackendUrl(url: string | null): Promise<string | null> {
  if (!url?.startsWith("blob:")) return url;
  const blob = await fetch(url).then((r) => r.blob());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

export async function composeKakaoBizboard(p: KakaoCompositeParams): Promise<Blob> {
  const validation = await validateKakaoBizboardInputs(p);
  if (validation.errors.length) throw new Error(validation.errors[0]);

  const template = kakaoTemplate(p.template);
  const [thumbnailUrl, appIconUrl] = await Promise.all([
    toBackendUrl(p.thumbnailUrl),
    template.appCopy ? toBackendUrl(p.appIconUrl) : Promise.resolve(null),
  ]);
  const res = await fetch("/api/incept/api/v1/kakao/compose-bizboard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      template: p.template,
      thumbnailUrl,
      appIconUrl,
      appCopy: template.appCopy ? p.appCopy : "",
      mainCopy: p.mainCopy,
      subCopy: template.subCopy ? p.subCopy : "",
      additionalInfo: p.additionalInfo,
      gacha: p.gacha,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = Array.isArray(body?.detail) ? body.detail[0] : body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Kakao compose failed (${res.status})`);
  }
  return res.blob();
}
