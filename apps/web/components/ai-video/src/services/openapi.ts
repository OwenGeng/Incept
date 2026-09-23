import { OpenAPI } from './generated'
import { aiVideoApiBase } from '../runtime'

declare global {
  interface Window {
    __ENV?: {
      BACKEND_URL?: string
    }
  }
}

/**
 * 初始化由 OpenAPI 生成的请求客户端。
 *
 * 说明：
 * - 生成接口的路径已包含 `/api/v1/...`，因此 BASE 默认应为空串（同源）或完整后端地址。
 * - Local development and production use `/api/ai-video`, whose Incept API
 *   bridge owns login checks, model credentials, and service routing.
 */
export function initOpenAPI(base: string = '') {
  OpenAPI.BASE = base
}

initOpenAPI(aiVideoApiBase)
