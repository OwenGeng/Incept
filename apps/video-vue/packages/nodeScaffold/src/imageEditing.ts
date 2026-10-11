export const MAX_IMAGE_PIXELS = 16_000_000;

export function stagedImageRecovery(stagedIds: readonly string[], paidRequestStarted: boolean) {
  const directories = stagedIds.map(id => `assets/${id}`);
  return {
    cleanup: paidRequestStarted ? [] : directories,
    warning: paidRequestStarted && directories.length
      ? `请求可能已开始生成。已保留素材目录 ${directories.join("、")}，请先检查素材再决定是否重试，避免重复计费。`
      : "",
  };
}

// 在浏览器解码前检查压缩图片的尺寸，避免小文件解压成巨大位图。
export function validateEncodedImage(data: ArrayBuffer, mimeType: string) {
  const bytes = new Uint8Array(data), view = new DataView(data);
  let width = 0, height = 0;
  const ascii = (offset: number, count: number) => String.fromCharCode(...bytes.slice(offset, offset + count));
  if (mimeType === "image/png" && bytes.length >= 24 && bytes[0] === 137 && ascii(1, 3) === "PNG" && ascii(12, 4) === "IHDR") {
    width = view.getUint32(16); height = view.getUint32(20);
  } else if (mimeType === "image/jpeg" && bytes[0] === 255 && bytes[1] === 216) {
    let offset = 2;
    while (offset + 4 <= bytes.length) {
      if (bytes[offset++] !== 255) break;
      while (bytes[offset] === 255) offset++;
      const marker = bytes[offset++]!;
      if (marker === 217 || marker === 218) break;
      if (marker === 1 || (marker >= 208 && marker <= 215)) continue;
      if (offset + 2 > bytes.length) break;
      const length = view.getUint16(offset);
      if (length < 2 || offset + length > bytes.length) break;
      if ([192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207].includes(marker) && length >= 7) {
        height = view.getUint16(offset + 3); width = view.getUint16(offset + 5); break;
      }
      offset += length;
    }
  } else if (mimeType === "image/webp" && ascii(0, 4) === "RIFF" && ascii(8, 4) === "WEBP") {
    for (let offset = 12; offset + 8 <= bytes.length;) {
      const type = ascii(offset, 4), length = view.getUint32(offset + 4, true), body = offset + 8;
      if (body + length > bytes.length) break;
      if (type === "VP8X" && length >= 10) {
        width = 1 + bytes[body + 4]! + (bytes[body + 5]! << 8) + (bytes[body + 6]! << 16);
        height = 1 + bytes[body + 7]! + (bytes[body + 8]! << 8) + (bytes[body + 9]! << 16); break;
      }
      if (type === "VP8L" && length >= 5 && bytes[body] === 47) {
        const bits = view.getUint32(body + 1, true); width = (bits & 16383) + 1; height = ((bits >>> 14) & 16383) + 1; break;
      }
      if (type === "VP8 " && length >= 10 && bytes[body + 3] === 157 && bytes[body + 4] === 1 && bytes[body + 5] === 42) {
        width = view.getUint16(body + 6, true) & 16383; height = view.getUint16(body + 8, true) & 16383; break;
      }
      offset = body + length + length % 2;
    }
  }
  if (!width || !height) throw new Error("无法安全读取图片尺寸，请使用有效的 PNG、JPEG 或 WebP 图片");
  validateImageDimensions(width, height);
  return { width, height };
}

export function validateImageDimensions(width: number, height: number) {
  if (![width, height].every(value => Number.isSafeInteger(value) && value > 0 && value <= 8192)
    || width * height > MAX_IMAGE_PIXELS) throw new Error("图片尺寸须在 8192 边长、1600 万像素以内");
}

export function gridTiles(width: number, height: number, rows: number, columns: number) {
  validateImageDimensions(width, height);
  if (![rows, columns].every(value => Number.isInteger(value) && value >= 1 && value <= 8)
    || rows > height || columns > width) throw new Error("宫格行列须为 1–8，且不能超过图片像素尺寸");
  return Array.from({ length: rows * columns }, (_, index) => {
    const row = Math.floor(index / columns), column = index % columns;
    const x = Math.floor(column * width / columns), y = Math.floor(row * height / rows);
    return { x, y, width: Math.floor((column + 1) * width / columns) - x,
      height: Math.floor((row + 1) * height / rows) - y, row, column };
  });
}

export function canvasPoint(clientX: number, clientY: number, bounds: Pick<DOMRect, "left" | "top" | "width" | "height">, width: number, height: number) {
  if (!bounds.width || !bounds.height) throw new Error("图片编辑区域尚未就绪");
  return { x: Math.max(0, Math.min(width, (clientX - bounds.left) * width / bounds.width)),
    y: Math.max(0, Math.min(height, (clientY - bounds.top) * height / bounds.height)) };
}

export function pushEdit<T>(history: readonly T[], cursor: number, edit: T, limit = 16) {
  const next = [...history.slice(0, cursor), edit].slice(-limit);
  return { history: next, cursor: next.length };
}
