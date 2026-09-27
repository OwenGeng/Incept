<template>
  <div ref="background" class="bubbleBackground" aria-hidden="true">
    <div ref="ambientWash" class="ambientWash" />
    <svg ref="flowMap" class="flowMap" viewBox="0 0 1440 900" fill="none" preserveAspectRatio="xMidYMin slice">
      <path ref="pathOne" class="flowPath flowPathPrimary" d="M-70 250C150 95 320 300 590 194C742 135 812 82 960 118" />
      <path ref="pathTwo" class="flowPath flowPathWarm" d="M875 118C1085 64 1165 310 1510 174" />
      <path ref="pathThree" class="flowPath flowPathPrimary" d="M-90 670C220 474 398 776 720 652C930 570 1110 692 1515 532" />
      <circle ref="dotOne" class="travelDot travelDotPrimary" r="4" />
      <circle ref="dotTwo" class="travelDot travelDotWarm" r="3.5" />
      <circle ref="dotThree" class="travelDot travelDotPrimary" r="3" />
    </svg>

    <div ref="bubbleLayer" class="bubbleLayer">
      <span class="flowBubble bubbleIdea">
        <svg viewBox="0 0 28 28">
          <path d="M14 4v4M14 20v4M4 14h4M20 14h4M7.2 7.2l2.9 2.9M17.9 17.9l2.9 2.9M20.8 7.2l-2.9 2.9M10.1 17.9l-2.9 2.9" />
          <circle cx="14" cy="14" r="3.5" />
        </svg>
      </span>
      <span class="flowBubble bubbleScript">
        <svg viewBox="0 0 28 28">
          <path d="M7 8h14M7 14h10M7 20h7" />
        </svg>
      </span>
      <span class="flowBubble bubbleImage">
        <svg viewBox="0 0 28 28">
          <rect x="4.5" y="5.5" width="19" height="17" rx="3" />
          <circle cx="18.5" cy="10" r="2" />
          <path d="m7.5 19 4.7-5 3.5 3.3 2.2-2.1 2.8 3.8" />
        </svg>
      </span>
      <span class="flowBubble bubbleAudio">
        <svg viewBox="0 0 28 28">
          <path d="M5 14h2M9 10v8M13 7v14M17 9v10M21 12v4M24 14h-1" />
        </svg>
      </span>
      <span class="flowBubble bubbleVideo">
        <svg viewBox="0 0 28 28">
          <circle cx="14" cy="14" r="9.5" />
          <path class="playGlyph" d="m12 10 6 4-6 4z" />
        </svg>
      </span>
      <span class="flowBubble bubbleFinish">
        <svg viewBox="0 0 28 28">
          <path d="m8 14 4 4 8-9" />
        </svg>
      </span>
    </div>

    <div ref="pointerLight" class="pointerLight" />
  </div>
</template>

<script setup lang="ts">
import { createTimeline } from "animejs/timeline";
import { createMotionPath } from "animejs/svg";
import { onBeforeUnmount, onMounted, ref } from "vue";

const background = ref<HTMLDivElement>();
const ambientWash = ref<HTMLDivElement>();
const flowMap = ref<SVGSVGElement>();
const bubbleLayer = ref<HTMLDivElement>();
const pointerLight = ref<HTMLDivElement>();
const pathOne = ref<SVGPathElement>();
const pathTwo = ref<SVGPathElement>();
const pathThree = ref<SVGPathElement>();
const dotOne = ref<SVGCircleElement>();
const dotTwo = ref<SVGCircleElement>();
const dotThree = ref<SVGCircleElement>();
let ambientTimeline: ReturnType<typeof createTimeline> | undefined;
let flowTimeline: ReturnType<typeof createTimeline> | undefined;
let visibilityObserver: IntersectionObserver | undefined;
let events: AbortController | undefined;
let pointerFrame = 0;
let visible = true;

onMounted(() => {
  const layer = background.value;
  const surface = layer?.parentElement;
  const bubbles = bubbleLayer.value?.querySelectorAll<HTMLElement>(".flowBubble");
  if (!layer || !surface || !bubbles?.length) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  events = new AbortController();
  const options = { passive: true, signal: events.signal };

  ambientTimeline = createTimeline({ autoplay: false, loop: true, alternate: true, defaults: { ease: "inOut(2)" } })
    .add(ambientWash.value!, { translateX: [0, 14], translateY: [0, 8], scale: [1, 1.025], duration: 11000 }, 0)
    .add(bubbles[0]!, { translateX: [0, 7], translateY: [0, -9], rotate: [-1.5, 1], duration: 7600 }, 0)
    .add(bubbles[1]!, { translateX: [0, -6], translateY: [0, 8], rotate: [1, -1], duration: 9200 }, 0)
    .add(bubbles[2]!, { translateX: [0, -8], translateY: [0, -7], rotate: [1.5, -0.5], duration: 8300 }, 0)
    .add(bubbles[3]!, { translateX: [0, 6], translateY: [0, 10], rotate: [-1, 1.5], duration: 9800 }, 0)
    .add(bubbles[4]!, { translateX: [0, -7], translateY: [0, -8], rotate: [0.5, -1], duration: 8700 }, 0)
    .add(bubbles[5]!, { translateX: [0, 7], translateY: [0, 7], rotate: [-1, 0.5], duration: 10400 }, 0);

  if (pathOne.value && pathTwo.value && pathThree.value && dotOne.value && dotTwo.value && dotThree.value) {
    flowTimeline = createTimeline({ autoplay: false, loop: true, defaults: { ease: "linear" } })
      .add(dotOne.value, { ...createMotionPath(pathOne.value), opacity: [0, 0.85, 0.85, 0], duration: 9000 }, 0)
      .add(dotTwo.value, { ...createMotionPath(pathTwo.value), opacity: [0, 0.76, 0.76, 0], duration: 7600 }, 1200)
      .add(dotThree.value, { ...createMotionPath(pathThree.value), opacity: [0, 0.72, 0.72, 0], duration: 11200 }, 2600);
  }

  function resetPointer() {
    cancelAnimationFrame(pointerFrame);
    bubbleLayer.value?.style.removeProperty("transform");
    flowMap.value?.style.removeProperty("transform");
    pointerLight.value?.style.setProperty("opacity", "0");
  }

  function updateMotionState() {
    const shouldPlay = visible && !document.hidden && !reducedMotion.matches;
    if (shouldPlay) {
      ambientTimeline?.resume();
      flowTimeline?.resume();
    } else {
      ambientTimeline?.pause();
      flowTimeline?.pause();
      resetPointer();
    }
  }

  visibilityObserver = new IntersectionObserver(entries => {
    visible = entries[0]?.isIntersecting ?? true;
    updateMotionState();
  }, { threshold: 0.02 });
  visibilityObserver.observe(layer);

  surface.addEventListener("pointermove", event => {
    if (event.pointerType === "touch" || reducedMotion.matches) return;
    cancelAnimationFrame(pointerFrame);
    pointerFrame = requestAnimationFrame(() => {
      const bounds = layer.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      const driftX = (x / bounds.width - 0.5) * 10;
      const driftY = (y / bounds.height - 0.5) * 7;
      bubbleLayer.value?.style.setProperty("transform", `translate3d(${driftX}px, ${driftY}px, 0)`);
      flowMap.value?.style.setProperty("transform", `translate3d(${-driftX * 0.35}px, ${-driftY * 0.35}px, 0)`);
      pointerLight.value?.style.setProperty("--pointer-x", `${x}px`);
      pointerLight.value?.style.setProperty("--pointer-y", `${y}px`);
      pointerLight.value?.style.setProperty("opacity", "1");
    });
  }, options);

  surface.addEventListener("pointerleave", resetPointer, options);
  document.addEventListener("visibilitychange", updateMotionState, options);
  reducedMotion.addEventListener("change", updateMotionState, options);
  updateMotionState();
});

onBeforeUnmount(() => {
  cancelAnimationFrame(pointerFrame);
  visibilityObserver?.disconnect();
  events?.abort();
  ambientTimeline?.revert();
  flowTimeline?.revert();
});
</script>

<style lang="scss" scoped>
.bubbleBackground {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  background: linear-gradient(180deg, color-mix(in srgb, var(--el-bg-color) 94%, #f6f3ff) 0%, var(--el-bg-color) 62%, color-mix(in srgb, var(--el-bg-color) 95%, #f6f1e7) 100%);

  .ambientWash,
  .flowMap,
  .bubbleLayer,
  .pointerLight { position: absolute; }

  .ambientWash {
    inset: -12%;
    background:
      radial-gradient(ellipse 34% 28% at 16% 18%, color-mix(in srgb, var(--el-color-primary) 12%, transparent), transparent 73%),
      radial-gradient(ellipse 30% 28% at 87% 24%, color-mix(in srgb, #e4b65d 12%, transparent), transparent 74%),
      radial-gradient(ellipse 34% 26% at 72% 77%, color-mix(in srgb, var(--el-color-primary) 8%, transparent), transparent 74%);
    will-change: transform;
  }

  .flowMap {
    inset: 0;
    width: 100%;
    height: 900px;
    overflow: hidden;
    opacity: 0.9;
    transition: transform 1000ms cubic-bezier(0.16, 1, 0.3, 1);
    will-change: transform;

    .flowPath {
      stroke-width: 1.25;
      stroke-linecap: round;
      stroke-dasharray: 2 8;
      vector-effect: non-scaling-stroke;
    }

    .flowPathPrimary { stroke: color-mix(in srgb, var(--el-color-primary) 28%, transparent); }
    .flowPathWarm { stroke: color-mix(in srgb, #d4a74d 31%, transparent); }

    .travelDot {
      opacity: 0;
      filter: drop-shadow(0 0 6px currentColor);
      will-change: transform, opacity;
    }

    .travelDotPrimary { fill: var(--el-color-primary); color: var(--el-color-primary); }
    .travelDotWarm { fill: #d6a64b; color: #d6a64b; }
  }

  .bubbleLayer {
    inset: 0;
    transition: transform 850ms cubic-bezier(0.16, 1, 0.3, 1);
    will-change: transform;
  }

  .flowBubble {
    position: absolute;
    display: grid;
    width: 68px;
    height: 68px;
    border: 1px solid color-mix(in srgb, var(--el-color-primary) 24%, var(--el-border-color));
    border-radius: 50%;
    background: color-mix(in srgb, var(--el-bg-color) 78%, transparent);
    box-shadow: 0 18px 42px -30px color-mix(in srgb, var(--el-color-primary) 42%, transparent), inset 0 0 0 7px color-mix(in srgb, var(--el-color-primary) 3%, transparent);
    color: color-mix(in srgb, var(--el-color-primary) 78%, var(--el-text-color-primary));
    opacity: 0.72;
    place-items: center;
    backdrop-filter: blur(12px);
    will-change: transform;

    svg {
      width: 28px;
      height: 28px;
      overflow: visible;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.35;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .playGlyph { fill: currentColor; stroke: none; }
  }

  .bubbleIdea { top: 145px; left: clamp(24px, 6vw, 96px); }
  .bubbleScript { top: 330px; left: clamp(72px, 13vw, 210px); width: 58px; height: 58px; }
  .bubbleImage { top: 125px; right: clamp(90px, 12vw, 190px); width: 76px; height: 76px; }
  .bubbleAudio { top: 344px; right: clamp(28px, 7vw, 112px); width: 60px; height: 60px; }
  .bubbleVideo { top: 570px; right: clamp(88px, 13vw, 210px); width: 80px; height: 80px; }
  .bubbleFinish { top: 645px; left: clamp(32px, 8vw, 130px); width: 54px; height: 54px; }

  .bubbleAudio,
  .bubbleFinish {
    border-color: color-mix(in srgb, #d0a44d 28%, var(--el-border-color));
    color: color-mix(in srgb, #b98428 82%, var(--el-text-color-primary));
    box-shadow: 0 18px 42px -30px color-mix(in srgb, #d0a44d 45%, transparent), inset 0 0 0 7px color-mix(in srgb, #d0a44d 3%, transparent);
  }

  .pointerLight {
    inset: 0;
    background: radial-gradient(240px circle at var(--pointer-x, 50%) var(--pointer-y, 22%), color-mix(in srgb, var(--el-color-primary) 8%, transparent), transparent 72%);
    opacity: 0;
    transition: opacity 320ms ease;
  }

  @media (max-width: 980px) {
    .flowMap { opacity: 0.68; }
    .flowBubble { opacity: 0.54; }
    .bubbleScript { left: 3vw; }
    .bubbleAudio { right: 3vw; }
  }

  @media (max-width: 700px) {
    .flowMap { height: 760px; opacity: 0.48; }
    .flowBubble { width: 52px; height: 52px; opacity: 0.4; }
    .flowBubble svg { width: 22px; height: 22px; }
    .bubbleIdea { top: 120px; left: -12px; }
    .bubbleScript { display: none; }
    .bubbleImage { top: 108px; right: -10px; }
    .bubbleAudio { top: 410px; right: -15px; }
    .bubbleVideo { top: 540px; right: 12vw; width: 58px; height: 58px; }
    .bubbleFinish { top: 590px; left: -8px; }
  }

  @media (prefers-reduced-motion: reduce) {
    .ambientWash,
    .travelDot { transform: none !important; }

    .travelDot,
    .pointerLight { display: none; }

    .flowMap,
    .bubbleLayer { transition: none; }
  }
}
</style>
