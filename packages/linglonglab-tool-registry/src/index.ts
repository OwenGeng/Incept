import type { ToolDefinition } from "@linglonglab/shared";

export const toolRegistry: ToolDefinition[] = [
  {
    id: "openai-image-2",
    name: "OpenAI Image 2",
    category: "image_generation",
    status: "enabled",
    provider: "openai",
    owner: "Creative Studio",
    description: "Primary quality benchmark for high-fidelity creative image generation."
  },
  {
    id: "gemini-image",
    name: "Gemini Image",
    category: "image_generation",
    status: "enabled",
    provider: "gemini",
    owner: "Creative Studio",
    description: "Fast multimodal image generation and iteration candidate."
  },
  {
    id: "veo-video",
    name: "Veo Video",
    category: "video_generation",
    status: "enabled",
    provider: "gemini",
    owner: "Growth AI",
    description: "Vertex AI Veo adapter for image-to-video, storyboard, and extend-video workflows."
  },
  {
    id: "lightweight-gif",
    name: "Lightweight GIF",
    category: "gif_generation",
    status: "mock",
    provider: "mock",
    owner: "Creative Automation",
    description: "Mock adapter for lightweight creative and end-card generation."
  },
  {
    id: "bq-performance",
    name: "BigQuery Performance",
    category: "performance_analysis",
    status: "mock",
    provider: "bigquery",
    owner: "IM GM",
    description: "Mock adapter for joining LinglongLab asset lineage with BigQuery performance data."
  }
];
