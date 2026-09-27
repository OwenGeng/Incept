<template>
  <div ref="background" class="cinemaBackground" aria-hidden="true">
    <div class="ambientWash" />
    <div ref="primaryGlow" class="filmGlow filmGlowPrimary" />
    <div ref="secondaryGlow" class="filmGlow filmGlowSecondary" />
    <div class="filmStrip">
      <span v-for="index in 15" :key="index" />
    </div>
    <div ref="viewfinder" class="viewfinder">
      <i v-for="index in 4" :key="index" />
    </div>
    <div class="grain" />
    <div ref="pointerLight" class="pointerLight" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

const background = ref<HTMLDivElement>();
const primaryGlow = ref<HTMLDivElement>();
const secondaryGlow = ref<HTMLDivElement>();
const viewfinder = ref<HTMLDivElement>();
const pointerLight = ref<HTMLDivElement>();
let events: AbortController | undefined;
let pointerFrame = 0;

onMounted(() => {
  const layer = background.value!;
  const surface = layer?.parentElement;
  if (!surface) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  events = new AbortController();
  const options = { passive: true, signal: events.signal };

  function resetPointer() {
    cancelAnimationFrame(pointerFrame);
    primaryGlow.value?.style.removeProperty("transform");
    secondaryGlow.value?.style.removeProperty("transform");
    viewfinder.value?.style.removeProperty("transform");
    pointerLight.value?.style.setProperty("opacity", "0");
  }

  function updateMotionState() {
    layer.style.setProperty("--motion-state", document.hidden || !document.hasFocus() ? "paused" : "running");
    resetPointer();
  }

  surface.addEventListener(
    "pointermove",
    event => {
      if (event.pointerType === "touch" || reducedMotion.matches) return;
      cancelAnimationFrame(pointerFrame);
      pointerFrame = requestAnimationFrame(() => {
        const bounds = layer.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return;
        const x = event.clientX - bounds.left;
        const y = event.clientY - bounds.top;
        const driftX = (x / bounds.width - 0.5) * 18;
        const driftY = (y / bounds.height - 0.5) * 12;
        primaryGlow.value?.style.setProperty("transform", `translate3d(${driftX}px, ${driftY}px, 0) rotate(-14deg)`);
        secondaryGlow.value?.style.setProperty("transform", `translate3d(${-driftX * 0.7}px, ${-driftY * 0.7}px, 0) rotate(18deg)`);
        viewfinder.value?.style.setProperty("transform", `translate3d(${-driftX * 0.45}px, ${-driftY * 0.45}px, 0)`);
        pointerLight.value?.style.setProperty("--pointer-x", `${x}px`);
        pointerLight.value?.style.setProperty("--pointer-y", `${y}px`);
        pointerLight.value?.style.setProperty("opacity", "1");
      });
    },
    options,
  );

  surface.addEventListener("pointerleave", resetPointer, options);
  window.addEventListener("blur", updateMotionState, options);
  window.addEventListener("focus", updateMotionState, options);
  document.addEventListener("visibilitychange", updateMotionState, options);
  reducedMotion.addEventListener("change", resetPointer, options);
  updateMotionState();
});

onBeforeUnmount(() => {
  cancelAnimationFrame(pointerFrame);
  events?.abort();
});
</script>

<style lang="scss" scoped>
.cinemaBackground {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  background: linear-gradient(180deg, color-mix(in srgb, var(--el-bg-color) 90%, #f8f4ed) 0%, var(--el-bg-color) 58%, color-mix(in srgb, var(--el-bg-color) 92%, #f0ede5) 100%);

  .ambientWash,
  .filmGlow,
  .filmStrip,
  .viewfinder,
  .grain,
  .pointerLight { position: absolute; }

  .ambientWash {
    inset: -16%;
    background:
      radial-gradient(ellipse 42% 34% at 22% 18%, color-mix(in srgb, var(--el-color-primary) 16%, transparent), transparent 72%),
      radial-gradient(ellipse 30% 30% at 82% 26%, color-mix(in srgb, #f5c96f 18%, transparent), transparent 74%),
      radial-gradient(ellipse 36% 32% at 68% 84%, color-mix(in srgb, var(--el-color-primary) 10%, transparent), transparent 72%);
    animation: washDrift 18s ease-in-out infinite alternate;
    animation-play-state: var(--motion-state, running);
  }

  .filmGlow {
    width: 56vw;
    height: 18vw;
    min-height: 160px;
    border: 1px solid color-mix(in srgb, var(--el-color-primary) 14%, transparent);
    border-radius: 999px;
    opacity: 0.64;
    filter: blur(0.2px);
    transform: rotate(-14deg);
    transition: transform 900ms cubic-bezier(0.16, 1, 0.3, 1);

    &::after {
      position: absolute;
      inset: 20% 7%;
      border-radius: inherit;
      background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--el-color-primary) 13%, transparent), transparent);
      content: "";
      filter: blur(18px);
    }
  }

  .filmGlowPrimary { top: 4%; right: -18%; }

  .filmGlowSecondary {
    bottom: 8%;
    left: -22%;
    border-color: color-mix(in srgb, #d6a956 16%, transparent);
    transform: rotate(18deg);
  }

  .filmStrip {
    top: 42%;
    right: -72px;
    display: grid;
    grid-template-columns: repeat(15, 42px);
    gap: 10px;
    padding: 8px 16px;
    border-block: 1px solid color-mix(in srgb, var(--el-text-color-primary) 8%, transparent);
    opacity: 0.34;
    transform: rotate(-9deg) translateX(4%);
    animation: filmDrift 22s ease-in-out infinite alternate;
    animation-play-state: var(--motion-state, running);

    span {
      width: 42px;
      height: 22px;
      border-radius: 4px;
      background: color-mix(in srgb, var(--el-text-color-primary) 5%, transparent);
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--el-text-color-primary) 7%, transparent);
    }
  }

  .viewfinder {
    top: 118px;
    left: clamp(24px, 5vw, 78px);
    width: min(34vw, 460px);
    aspect-ratio: 16 / 10;
    opacity: 0.2;
    transition: transform 1100ms cubic-bezier(0.16, 1, 0.3, 1);

    i {
      position: absolute;
      width: 34px;
      height: 34px;
      border-color: var(--el-color-primary);
      border-style: solid;

      &:nth-child(1) { top: 0; left: 0; border-width: 1px 0 0 1px; }
      &:nth-child(2) { top: 0; right: 0; border-width: 1px 1px 0 0; }
      &:nth-child(3) { right: 0; bottom: 0; border-width: 0 1px 1px 0; }
      &:nth-child(4) { bottom: 0; left: 0; border-width: 0 0 1px 1px; }
    }
  }

  .grain {
    inset: 0;
    opacity: 0.16;
    background-image:
      radial-gradient(circle at 20% 30%, var(--el-text-color-primary) 0 0.45px, transparent 0.6px),
      radial-gradient(circle at 70% 60%, var(--el-text-color-primary) 0 0.4px, transparent 0.55px);
    background-size: 9px 9px, 13px 13px;
    mask-image: linear-gradient(to bottom, #000, transparent 68%);
  }

  .pointerLight {
    inset: 0;
    background: radial-gradient(260px circle at var(--pointer-x, 50%) var(--pointer-y, 20%), color-mix(in srgb, #f5c96f 14%, transparent), transparent 72%);
    opacity: 0;
    transition: opacity 300ms ease;
  }

  @media (max-width: 820px) {
    .filmStrip { top: 36%; opacity: 0.22; }
    .viewfinder { width: 58vw; opacity: 0.14; }
    .filmGlow { width: 82vw; }
  }

  @media (prefers-reduced-motion: reduce) {
    .ambientWash,
    .filmStrip { animation: none; }

    .filmGlow,
    .viewfinder { transform: none; transition: none; }

    .pointerLight { display: none; }
  }
}

@keyframes washDrift {
  from { transform: translate3d(-1.5%, -1%, 0) scale(1); }
  to { transform: translate3d(1.5%, 1.2%, 0) scale(1.04); }
}

@keyframes filmDrift {
  from { transform: rotate(-9deg) translate3d(4%, 0, 0); }
  to { transform: rotate(-9deg) translate3d(-3%, 8px, 0); }
}
</style>
