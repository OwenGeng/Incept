// Hosted interface boundary; upstream scaffold packages never gain filesystem,
// desktop canvas, or global credential access in a multi-user host.
import { z } from 'zod';
export type ToolCall = { id: string; name: string; args?: Record<string, unknown>; status: 'running'|'success'|'error'|'interrupted'; result?: string };
export type QuestionRequest = { title: string; question: string; options?: string[]; fields?: any[] };
export type QuestionContext = { ask: (...args: any[]) => Promise<any> };
export type CanvasContext = { call?: (...args: any[]) => Promise<any>; [key: string]: any };
export type CanvasToolCall = { name: string; args: any };
export const teamNameSchema = z.string().min(1).max(80);
