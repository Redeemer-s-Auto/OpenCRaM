/**
 * Garden-local emoji rendering support probe.
 *
 * Plane's upstream is-emoji-supported dependency performs repeated getImageData()
 * reads from a 2D canvas. Chrome warns when that context is not created with
 * willReadFrequently, so keep the same color-glyph detection strategy while
 * explicitly opting the canvas into readback-heavy use.
 */

const supportCache = new Map<string, boolean>();
let supportContext: CanvasRenderingContext2D | null | undefined;

const CELL_WIDTH = 32;
const CELL_HEIGHT = 24;

function getSupportContext(): CanvasRenderingContext2D | null {
  if (supportContext !== undefined) return supportContext;
  if (typeof document === "undefined") {
    supportContext = null;
    return supportContext;
  }

  const canvas = document.createElement("canvas");
  canvas.width = CELL_WIDTH * 2;
  canvas.height = CELL_HEIGHT;
  supportContext = canvas.getContext("2d", { willReadFrequently: true });

  if (supportContext) {
    supportContext.font = "16px Arial, sans-serif";
    supportContext.textBaseline = "top";
  }

  return supportContext;
}

export function isEmojiSupported(unicode: string): boolean {
  const cached = supportCache.get(unicode);
  if (cached !== undefined) return cached;

  const ctx = getSupportContext();
  if (!ctx) {
    supportCache.set(unicode, false);
    return false;
  }

  ctx.clearRect(0, 0, CELL_WIDTH * 2, CELL_HEIGHT);
  ctx.fillStyle = "#ff0000";
  ctx.fillText(unicode, 0, 0);
  ctx.fillStyle = "#0000ff";
  ctx.fillText(unicode, CELL_WIDTH, 0);

  const left = ctx.getImageData(0, 0, CELL_WIDTH, CELL_HEIGHT).data;
  let firstVisiblePixel = -1;
  for (let offset = 0; offset < left.length; offset += 4) {
    if (left[offset + 3] !== 0) {
      firstVisiblePixel = offset;
      break;
    }
  }

  let supported = false;
  if (firstVisiblePixel >= 0) {
    const pixelIndex = firstVisiblePixel / 4;
    const x = CELL_WIDTH + (pixelIndex % CELL_WIDTH);
    const y = Math.floor(pixelIndex / CELL_WIDTH);
    const right = ctx.getImageData(x, y, 1, 1).data;

    // Color emoji ignore fillStyle, while fallback/monochrome glyphs inherit it.
    supported = left[firstVisiblePixel] === right[0] && left[firstVisiblePixel + 2] === right[2];
  }

  supportCache.set(unicode, supported);
  return supported;
}

export default isEmojiSupported;
