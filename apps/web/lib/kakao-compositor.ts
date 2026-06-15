// Kakao Bizboard template compositor — produces 1029×258 transparent PNG

const W = 1029;
const H = 258;
const SAFE_L = 48;
const SAFE_R = 48;
const THUMB_X = W - SAFE_R - 315;
const THUMB_Y = 36;
const THUMB_W = 315;
const THUMB_H = 186;
const THUMB_GAP = 24;
const LEFT_ZONE_W = THUMB_X - SAFE_L - THUMB_GAP;
const MAIN_COPY_MIN_W = 290;
const MAIN_COPY_MAX_W = 585;
const MAIN_COPY_Y = 167;
const APP_ICON_SZ = 38;
const APP_ICON_X = SAFE_L;
const APP_ICON_Y = 88;
const APP_DL_X = APP_ICON_X + APP_ICON_SZ + 8;
const APP_DL_Y = APP_ICON_Y + 28;
const AD_PILL_X = SAFE_L;
const AD_PILL_Y = 208;
const AD_COPY_X = AD_PILL_X + 34;
const AD_COPY_Y = AD_PILL_Y + 15;

let fontsLoaded = false;

export async function loadSpoqaFonts(): Promise<void> {
  if (fontsLoaded) return;
  try {
    const BASE =
      "https://cdn.jsdelivr.net/gh/spoqa/spoqa-han-sans@latest/fonts/SpoqaHanSansNeo";
    const regular = new FontFace(
      "SpoqaHanSansNeo",
      `url(${BASE}/SpoqaHanSansNeo-Regular.woff2)`,
    );
    const bold = new FontFace(
      "SpoqaHanSansNeo",
      `url(${BASE}/SpoqaHanSansNeo-Bold.woff2)`,
      { weight: "700" },
    );
    await Promise.all([regular.load(), bold.load()]);
    document.fonts.add(regular);
    document.fonts.add(bold);
    fontsLoaded = true;
  } catch {
    // Falls back to system Korean font — text still renders
  }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
    img.src = url;
  });
}

function centerCropParams(
  srcW: number, srcH: number,
  dstW: number, dstH: number,
) {
  const srcR = srcW / srcH;
  const dstR = dstW / dstH;
  if (srcR > dstR) {
    const sw = srcH * dstR;
    return { sx: (srcW - sw) / 2, sy: 0, sw, sh: srcH };
  }
  const sh = srcW / dstR;
  return { sx: 0, sy: (srcH - sh) / 2, sw: srcW, sh };
}

export interface KakaoCompositeParams {
  thumbnailUrl: string;
  appIconUrl: string | null;
  mainCopy: string;
  appDownloadCopy: string;
  dspName: string;
  gacha: boolean;
}

export interface KakaoBizboardValidationResult {
  errors: string[];
  mainCopyWidthPx: number;
  mainCopyMinWidthPx: number;
  mainCopyMaxWidthPx: number;
}

function makeMeasureContext(): CanvasRenderingContext2D {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not create canvas context");
  return ctx;
}

function fontStack() {
  return "SpoqaHanSansNeo, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif";
}

function normalizeCopy(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

function hasEmoji(value: string) {
  return /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(value);
}

function buildAdDisclosure(dspName: string, gacha: boolean) {
  const normalized = normalizeCopy(dspName) || "Moloco";
  return gacha
    ? `${normalized} 광고 · 확률형 아이템 포함`
    : `${normalized} 광고입니다.`;
}

export async function validateKakaoBizboardInputs(
  p: KakaoCompositeParams,
): Promise<KakaoBizboardValidationResult> {
  await loadSpoqaFonts();
  const ctx = makeMeasureContext();
  const FONT = fontStack();
  const errors: string[] = [];
  const mainCopy = normalizeCopy(p.mainCopy);
  const appDownloadCopy = normalizeCopy(p.appDownloadCopy);
  const dspName = normalizeCopy(p.dspName);

  if (!p.thumbnailUrl) errors.push("A cleaned thumbnail image is required.");
  if (!p.appIconUrl) errors.push("A 38x38 app icon is required.");
  if (!mainCopy) errors.push("Main copy is required.");
  if (!appDownloadCopy) errors.push("App download copy is required.");
  if (!dspName) errors.push("DSP name is required.");

  if (mainCopy) {
    ctx.font = `700 48px ${FONT}`;
    const mainCopyWidthPx = ctx.measureText(mainCopy).width;
    if (mainCopyWidthPx < MAIN_COPY_MIN_W) {
      errors.push(`Main copy is too short. It must be at least ${MAIN_COPY_MIN_W}px wide at 48pt.`);
    }
    if (mainCopyWidthPx > MAIN_COPY_MAX_W) {
      errors.push(`Main copy is too long. It must not exceed ${MAIN_COPY_MAX_W}px wide at 48pt.`);
    }
    if (mainCopyWidthPx > LEFT_ZONE_W) {
      errors.push("Main copy overlaps the Bizboard thumbnail zone.");
    }
  }

  if (appDownloadCopy) {
    if (!appDownloadCopy.includes("앱")) {
      errors.push('App download copy must include the word "앱".');
    }
    if (!appDownloadCopy.trim().endsWith(">")) {
      errors.push('App download copy must end with the ">" icon.');
    }
    if (hasEmoji(appDownloadCopy)) {
      errors.push("App download copy cannot include emoji.");
    }
    ctx.font = `26px ${FONT}`;
    if (ctx.measureText(appDownloadCopy).width > LEFT_ZONE_W - APP_ICON_SZ - 8) {
      errors.push("App download copy is too long for the fixed Bizboard slot.");
    }
  }

  if (dspName) {
    if (hasEmoji(dspName)) {
      errors.push("DSP name cannot include emoji.");
    }
    ctx.font = `22px ${FONT}`;
    if (ctx.measureText(buildAdDisclosure(dspName, p.gacha)).width > LEFT_ZONE_W - 34) {
      errors.push("DSP disclosure text is too long for the fixed Bizboard slot.");
    }
  }

  return {
    errors,
    mainCopyWidthPx: mainCopy
      ? (() => {
          ctx.font = `700 48px ${FONT}`;
          return ctx.measureText(mainCopy).width;
        })()
      : 0,
    mainCopyMinWidthPx: MAIN_COPY_MIN_W,
    mainCopyMaxWidthPx: MAIN_COPY_MAX_W,
  };
}

export async function composeKakaoBizboard(p: KakaoCompositeParams): Promise<Blob> {
  const validation = await validateKakaoBizboardInputs(p);
  if (validation.errors.length) {
    throw new Error(validation.errors[0]);
  }
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;

  const FONT = fontStack();
  const mainCopy = normalizeCopy(p.mainCopy);
  const appDownloadCopy = normalizeCopy(p.appDownloadCopy);
  const disclosure = buildAdDisclosure(p.dspName, p.gacha);

  // Thumbnail (center-cropped, right side)
  const thumb = await loadImage(p.thumbnailUrl);
  const { sx, sy, sw, sh } = centerCropParams(
    thumb.naturalWidth, thumb.naturalHeight, THUMB_W, THUMB_H,
  );
  ctx.save();
  ctx.beginPath();
  ctx.rect(THUMB_X, THUMB_Y, THUMB_W, THUMB_H);
  ctx.clip();
  ctx.drawImage(thumb, sx, sy, sw, sh, THUMB_X, THUMB_Y, THUMB_W, THUMB_H);
  ctx.restore();

  // App icon (rounded)
  if (p.appIconUrl) {
    const icon = await loadImage(p.appIconUrl);
    ctx.save();
    ctx.beginPath();
    ctx.roundRect(APP_ICON_X, APP_ICON_Y, APP_ICON_SZ, APP_ICON_SZ, 8);
    ctx.clip();
    ctx.drawImage(icon, APP_ICON_X, APP_ICON_Y, APP_ICON_SZ, APP_ICON_SZ);
    ctx.restore();
  }

  // App download copy (inline with icon)
  ctx.font = `26px ${FONT}`;
  ctx.fillStyle = "#777777";
  ctx.fillText(appDownloadCopy, APP_DL_X, APP_DL_Y);

  // Main copy (bold)
  ctx.font = `700 48px ${FONT}`;
  ctx.fillStyle = "#4C4C4C";
  ctx.fillText(mainCopy, SAFE_L, MAIN_COPY_Y);

  // AD pill
  ctx.fillStyle = "#AAAAAA";
  ctx.beginPath();
  ctx.roundRect(AD_PILL_X, AD_PILL_Y, 28, 20, 4);
  ctx.fill();
  ctx.font = `700 11px ${FONT}`;
  ctx.fillStyle = "#FFFFFF";
  ctx.textAlign = "center";
  ctx.fillText("AD", AD_PILL_X + 14, AD_PILL_Y + 14);
  ctx.textAlign = "left";

  // AD text
  ctx.font = `22px ${FONT}`;
  ctx.fillStyle = "#777777";
  ctx.fillText(disclosure, AD_COPY_X, AD_COPY_Y);

  return new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      b => (b ? resolve(b) : reject(new Error("canvas.toBlob failed"))),
      "image/png",
    ),
  );
}
