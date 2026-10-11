import type {
  CanvasToolCall,
  QuestionRequest,
  ToolCall,
} from "@linglonglab/video-tools-scaffold/runtime";

export type AgentToolCall = ToolCall & {
  question?: QuestionRequest & { callId: string; sessionFile?: string; runId?: string };
  progress?: string;
  argsText?: string;
};

export type AgentStats = {
  tokens: {
    input: number;
    output: number;
    cacheRead: number;
    cacheWrite: number;
    total: number;
  };
  tokensPerSecond?: number;
  cost?: number | null;
  elapsedMs?: number;
  children?: { file?: string; name?: string; status?: string; tokens?: AgentStats["tokens"] | null; cost?: number | null }[] | AgentStats;
  totals?: AgentStats;
  budget?: { used?: number; limit?: number; remaining?: number; maxTokens?: number; maxCost?: number; maxSubAgents?: number };
};

export type AgentContext = {
  tokens: number | null;
  contextWindow: number;
  percent: number | null;
};

export type AgentSubAgent = {
  file: string;
  parentFile: string;
  name: string;
  task: string;
  status:
    | "running"
    | "completed"
    | "error"
    | "limited"
    | "cancelled"
    | "inputRequired";
  result?: string;
  providerId?: string;
  modelId?: string;
  thinkingLevel?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
};

export type AgentEvent = (
  | { type: "researchQuestion"; question: { id: string; status: "pending" | "answered" | "consumed"; prompt: string; message_id: string; choice?: "light" | "deep" | "off"; skipped?: boolean; notes?: string } }
  | {
      type: "text" | "thinking";
      blockId: string;
      delta?: string;
      content?: string;
      done?: boolean;
    }
  | { type: "compaction"; active: boolean }
  | { type: "progress"; content: string }
  | { type: "tool"; blockId: string; tool: AgentToolCall }
  | ({ type: "canvasCall"; callId: string } & CanvasToolCall)
  | ({ type: "question"; callId: string; toolCallId: string; sessionFile?: string; runId?: string } & QuestionRequest)
  | { type: "error"; message: string }
  | { type: "session"; file: string; runId?: string }
  | {
      type: "userMessage";
      id: string;
      content?: string;
      attachments?: { name: string; path: string; mimeType: string }[];
    }
  | { type: "subAgent"; agent: AgentSubAgent }
  | { type: "subAgentEvent"; file: string; event: AgentEvent }
  | {
      type: "report";
      parentFile: string;
      file: string;
      name: string;
      content: string;
      id: string;
    }
  | { type: "accepted"; streamingBehavior?: "steer" | "followUp" }
  | { type: "stats"; stats: AgentStats; contextUsage?: AgentContext }
  | { type: "done" }) & { sequence?: number };
