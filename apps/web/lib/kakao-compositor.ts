"use client";

// Kakao Bizboard template compositor - produces a 1029x258 transparent PNG

const W = 1029;
const H = 258;
const SAFE_L = 48;
const SAFE_R = 48;
const THUMB_X = W - SAFE_R - 315;           // 666
const THUMB_Y = 36;
const THUMB_W = 315;
const THUMB_H = 186;
// Absolute right-edge limit shared by title and subtitle (Go: textMaximumBoundary)
const TEXT_BOUNDARY_MAX = 633;
// Coordinates verified against Go backend (kakao_bizboard.go)
const MAIN_COPY_X = 46;
const MAIN_COPY_Y = 148;  // titleTextProps.YPos=100 + size=48
// Go: textMinimumBoundary=340, titleTextProps.XPos=46 → min width = 340-46 = 294
const MAIN_COPY_MIN_W = 340 - MAIN_COPY_X;
// Go: textMaximumBoundary=633, titleTextProps.XPos=46 → max width = 633-46 = 587
const MAIN_COPY_MAX_W = TEXT_BOUNDARY_MAX - MAIN_COPY_X;
const APP_ICON_SZ = 38;
const APP_ICON_X = SAFE_L;
const APP_ICON_Y = 50;
const SUBTITLE_X = 93;           // subtitleTextProps.XPos
const SUBTITLE_Y = 79;           // subtitleTextProps.YPos=53 + size=26
const SUBTITLE_ARROW_X_PAD = 3;  // leftPaddingForSubtitleEndingText
const SUBTITLE_ARROW_Y = 75;     // subtitleTextProps.YPos=53 + yPosAdjustmentForSubtitleEndingText=22
const SUBTITLE_ARROW_SIZE = 15.6; // defaultSubtitleEndingTextProps.Size
const NOTICE_X = 102;    // noticeTextProps.XPos
const NOTICE_Y = 195;    // noticeTextProps.YPos=171 + size=24
const TEMPLATE_URL = "/kakao-bizboard-template.png";

// App terms Kakao accepts in subtitle (Go: appTerms slice)
const SUBTITLE_APP_TERMS = ["앱", "app", "App", "APP"] as const;

export const KAKAO_SUBTITLE_SUFFIX = "앱에서 확인";
// Period required per Go reference: noticeTextForNoUseGatchaContents = "Moloco 광고입니다."
export const KAKAO_DEFAULT_DISCLOSURE = "Moloco 광고입니다.";
export const KAKAO_GACHA_DISCLOSURE = "Moloco 광고 · 확률형 아이템 포함";
export const KAKAO_DEFAULT_SUBTITLE = "APP_NAME 앱에서 확인";
export const KAKAO_DEFAULT_MAIN_COPY = "APP_NAME 출시";

let fontsLoaded = false;

const SPOQA_FONT_BASE = "/SpoqaHanSansNeo_all/SpoqaHanSansNeo_OTF_subset";

export async function loadSpoqaFonts(): Promise<void> {
  if (fontsLoaded) return;
  try {
    const regular = new FontFace(
      "SpoqaHanSansNeo",
      `url(${SPOQA_FONT_BASE}/SpoqaHanSansNeo-Regular.woff2) format("woff2")`,
      { weight: "400", style: "normal" },
    );
    const medium = new FontFace(
      "SpoqaHanSansNeo",
      `url(${SPOQA_FONT_BASE}/SpoqaHanSansNeo-Medium.woff2) format("woff2")`,
      { weight: "500", style: "normal" },
    );
    const bold = new FontFace(
      "SpoqaHanSansNeo",
      `url(${SPOQA_FONT_BASE}/SpoqaHanSansNeo-Bold.woff2) format("woff2")`,
      { weight: "700", style: "normal" },
    );

    await Promise.all([regular.load(), medium.load(), bold.load()]);
    document.fonts.add(regular);
    document.fonts.add(medium);
    document.fonts.add(bold);
    fontsLoaded = true;
  } catch (error) {
    console.warn("Failed to load local Spoqa Han Sans Neo fonts, falling back to system fonts.", error);
    fontsLoaded = true;
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

// Trim transparent border pixels from a cleaned product image so the
// tight object bounding box is used when placing it in the thumbnail slot.
async function trimTransparentBorders(img: HTMLImageElement): Promise<HTMLCanvasElement> {
  const temp = document.createElement("canvas");
  temp.width = img.naturalWidth;
  temp.height = img.naturalHeight;
  const tc = temp.getContext("2d");
  if (!tc) return temp;
  tc.drawImage(img, 0, 0);

  const { data } = tc.getImageData(0, 0, temp.width, temp.height);
  let x0 = temp.width, x1 = 0, y0 = temp.height, y1 = 0;
  for (let y = 0; y < temp.height; y++) {
    for (let x = 0; x < temp.width; x++) {
      if (data[(y * temp.width + x) * 4 + 3] > 10) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  if (x1 <= x0 || y1 <= y0) return temp;

  const out = document.createElement("canvas");
  out.width = x1 - x0 + 1;
  out.height = y1 - y0 + 1;
  const oc = out.getContext("2d");
  if (!oc) return temp;
  oc.drawImage(temp, x0, y0, out.width, out.height, 0, 0, out.width, out.height);
  return out;
}

async function loadTemplateMaskData() {
  const template = await loadImage(TEMPLATE_URL);
  const maskCanvas = document.createElement("canvas");
  maskCanvas.width = W;
  maskCanvas.height = H;
  const maskCtx = maskCanvas.getContext("2d");
  if (!maskCtx) {
    throw new Error("Could not create Kakao template mask context");
  }
  maskCtx.drawImage(template, 0, 0, W, H);
  return maskCtx.getImageData(0, 0, W, H);
}

// Cover-fit: scale and center-crop source to fill destination exactly (matches Go drawMainImage).
function coverCropParams(srcW: number, srcH: number, dstW: number, dstH: number) {
  const srcR = srcW / srcH;
  const dstR = dstW / dstH;
  if (srcR > dstR) {
    const sw = Math.round(srcH * dstR);
    return { sx: Math.round((srcW - sw) / 2), sy: 0, sw, sh: srcH };
  }
  const sh = Math.round(srcW / dstR);
  return { sx: 0, sy: Math.round((srcH - sh) / 2), sw: srcW, sh };
}

export interface KakaoCompositeParams {
  thumbnailUrl: string;
  appIconUrl: string | null;
  subtitle: string;
  mainCopy: string;
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

export function buildKakaoSubtitle(appName: string) {
  const normalized = normalizeCopy(appName);
  return normalized ? `${normalized} ${KAKAO_SUBTITLE_SUFFIX}` : KAKAO_DEFAULT_SUBTITLE;
}

export function buildKakaoDefaultMainCopy(appName: string) {
  const normalized = normalizeCopy(appName);
  return normalized ? `${normalized} 출시` : KAKAO_DEFAULT_MAIN_COPY;
}

export function buildKakaoDisclosure(gacha: boolean) {
  return gacha ? KAKAO_GACHA_DISCLOSURE : KAKAO_DEFAULT_DISCLOSURE;
}

// Measure full subtitle width including the  arrow glyph, matching Go's writeSubtitle return value.
function measureSubtitleWidth(ctx: CanvasRenderingContext2D, subtitle: string, font: string): number {
  const bodyText = subtitle.trim() + " ";
  ctx.font = `26px ${font}`;
  const bodyWidth = ctx.measureText(bodyText).width;
  ctx.font = `${SUBTITLE_ARROW_SIZE}px ${font}`;
  const arrowWidth = ctx.measureText("").width;
  return bodyWidth + SUBTITLE_ARROW_X_PAD + arrowWidth;
}

export async function validateKakaoBizboardInputs(
  p: KakaoCompositeParams,
): Promise<KakaoBizboardValidationResult> {
  await loadSpoqaFonts();
  const ctx = makeMeasureContext();
  const font = fontStack();
  const errors: string[] = [];
  const subtitle = normalizeCopy(p.subtitle);
  const mainCopy = normalizeCopy(p.mainCopy);

  if (!p.thumbnailUrl) errors.push("A cleaned thumbnail image is required.");
  if (!subtitle) errors.push("Subtitle is required.");
  if (!mainCopy) errors.push("Main copy is required.");

  if (subtitle) {
    // Go: validate subtitle contains any of appTerms = ["앱", "app", "App", "APP"]
    if (!SUBTITLE_APP_TERMS.some((t) => subtitle.includes(t))) {
      errors.push('Subtitle must include "앱" (or "app"/"App"/"APP").');
    }
    if (hasEmoji(subtitle)) {
      errors.push("Subtitle cannot include emoji.");
    }
    // Go: subtitleLength + subtitleTextProps.XPos >= textMaximumBoundary
    const subtitleRightPos = SUBTITLE_X + measureSubtitleWidth(ctx, subtitle, font);
    if (subtitleRightPos >= TEXT_BOUNDARY_MAX) {
      errors.push("Subtitle is too long for the fixed Bizboard slot.");
    }
  }

  if (mainCopy) {
    ctx.font = `700 48px ${font}`;
    const mainCopyWidthPx = ctx.measureText(mainCopy).width;
    // Go: titleRightPos <= textMinimumBoundary (294 + 46 = 340)
    if (mainCopyWidthPx <= MAIN_COPY_MIN_W) {
      errors.push(
        `Main copy is too short. It must be wider than ${MAIN_COPY_MIN_W}px at 48pt.`,
      );
    }
    // Go: titleRightPos >= textMaximumBoundary (587 + 46 = 633)
    if (mainCopyWidthPx >= MAIN_COPY_MAX_W) {
      errors.push(
        `Main copy is too long. It must be narrower than ${MAIN_COPY_MAX_W}px at 48pt.`,
      );
    }
  }

  return {
    errors,
    mainCopyWidthPx: mainCopy
      ? (() => {
          ctx.font = `700 48px ${font}`;
          return ctx.measureText(mainCopy).width;
        })()
      : 0,
    mainCopyMinWidthPx: MAIN_COPY_MIN_W,
    mainCopyMaxWidthPx: MAIN_COPY_MAX_W,
  };
}

export async function composeKakaoBizboardCanvas(
  p: KakaoCompositeParams,
): Promise<Blob> {
  const validation = await validateKakaoBizboardInputs(p);
  if (validation.errors.length) {
    throw new Error(validation.errors[0]);
  }

  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not create canvas context");

  const font = fontStack();
  const subtitle = normalizeCopy(p.subtitle);
  const mainCopy = normalizeCopy(p.mainCopy);
  const disclosure = buildKakaoDisclosure(p.gacha);
  const templateMask = await loadTemplateMaskData();

  // Base template: match the company Kakao Bizboard shell exactly.
  try {
    const template = await loadImage(TEMPLATE_URL);
    ctx.drawImage(template, 0, 0, W, H);
  } catch (error) {
    console.warn("Failed to load Kakao Bizboard template, falling back to transparent canvas.", error);
  }

  // Thumbnail: company Go implementation uses the template alpha mask, not a simple rounded clip.
  const thumb = await loadImage(p.thumbnailUrl);
  const { sx, sy, sw, sh } = coverCropParams(thumb.naturalWidth, thumb.naturalHeight, THUMB_W, THUMB_H);
  const thumbCanvas = document.createElement("canvas");
  thumbCanvas.width = THUMB_W;
  thumbCanvas.height = THUMB_H;
  const thumbCtx = thumbCanvas.getContext("2d");
  if (!thumbCtx) {
    throw new Error("Could not create Kakao thumbnail context");
  }
  thumbCtx.drawImage(thumb, sx, sy, sw, sh, 0, 0, THUMB_W, THUMB_H);
  const thumbData = thumbCtx.getImageData(0, 0, THUMB_W, THUMB_H);
  const thumbPixels = thumbData.data;
  const outData = ctx.getImageData(THUMB_X, THUMB_Y, THUMB_W, THUMB_H);
  const outPixels = outData.data;
  const maskPixels = templateMask.data;

  for (let y = 0; y < THUMB_H; y += 1) {
    for (let x = 0; x < THUMB_W; x += 1) {
      const localIndex = (y * THUMB_W + x) * 4;
      const globalIndex = ((THUMB_Y + y) * W + (THUMB_X + x)) * 4;
      const alpha = maskPixels[globalIndex + 3] / 255;

      outPixels[localIndex] = Math.round(thumbPixels[localIndex] * alpha);
      outPixels[localIndex + 1] = Math.round(thumbPixels[localIndex + 1] * alpha);
      outPixels[localIndex + 2] = Math.round(thumbPixels[localIndex + 2] * alpha);
      outPixels[localIndex + 3] = Math.round(255 * alpha);
    }
  }

  ctx.putImageData(outData, THUMB_X, THUMB_Y);

  if (p.appIconUrl) {
    const icon = await loadImage(p.appIconUrl);
    ctx.drawImage(icon, APP_ICON_X, APP_ICON_Y, APP_ICON_SZ, APP_ICON_SZ);
  }

  // Font: Metrics kerning (= fontKerning "normal") and no custom letter spacing,
  // as required by Kakao bizboard font style guide.
  ctx.fontKerning = "normal";
  ctx.letterSpacing = "0px";
  ctx.fillStyle = "#777777";

  // Subtitle body — strip trailing ">" which the user typed as a placeholder for .
  // Go: strings.Trim(subtitle, " ") + " " drawn at subtitleTextProps, then  drawn separately.
  const subtitleBody = subtitle.trim() + " ";
  ctx.font = `26px ${font}`;
  ctx.fillText(subtitleBody, SUBTITLE_X, SUBTITLE_Y);

  // Subtitle arrow glyph: Spoqa Han Sans Neo PUA  (custom chevron).
  // Go: size=15.6, x = subtitleTextProps.XPos + subtitleTextWidth + leftPaddingForSubtitleEndingText(3)
  //     y = subtitleTextProps.YPos(53) + yPosAdjustmentForSubtitleEndingText(22) = 75
  const subtitleBodyWidth = ctx.measureText(subtitleBody).width;
  ctx.font = `${SUBTITLE_ARROW_SIZE}px ${font}`;
  ctx.fillText("", SUBTITLE_X + subtitleBodyWidth + SUBTITLE_ARROW_X_PAD, SUBTITLE_ARROW_Y);

  ctx.font = `700 48px ${font}`;
  ctx.fillStyle = "#4C4C4C";
  ctx.fillText(mainCopy, MAIN_COPY_X, MAIN_COPY_Y);

  ctx.font = `24px ${font}`;
  ctx.fillStyle = "#777777";
  ctx.fillText(disclosure, NOTICE_X, NOTICE_Y);

  return new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("canvas.toBlob failed"))),
      "image/png",
    ),
  );
}

async function resolveUrlForBackend(url: string | null): Promise<string | null> {
  if (!url) return null;
  if (!url.startsWith("blob:")) return url;
  const blob = await fetch(url).then((r) => r.blob());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function composeKakaoBizboardViaAPI(p: KakaoCompositeParams): Promise<Blob> {
  const [thumbnailUrl, appIconUrl] = await Promise.all([
    resolveUrlForBackend(p.thumbnailUrl),
    resolveUrlForBackend(p.appIconUrl),
  ]);
  const res = await fetch("/api/incept/api/v1/kakao/compose-bizboard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      thumbnailUrl,
      appIconUrl,
      subtitle: p.subtitle,
      mainCopy: p.mainCopy,
      gacha: p.gacha,
    }),
  });
  if (!res.ok) {
    throw new Error(`Kakao compose API error: ${res.status} ${await res.text()}`);
  }
  return res.blob();
}

export async function composeKakaoBizboard(
  p: KakaoCompositeParams,
): Promise<Blob> {
  const validation = await validateKakaoBizboardInputs(p);
  if (validation.errors.length) {
    throw new Error(validation.errors[0]);
  }
  return composeKakaoBizboardViaAPI(p);
}
