type MessageMethod = (content: string) => unknown

export type AiVideoMessageApi = {
  error: MessageMethod
  info: MessageMethod
  success: MessageMethod
  warning: MessageMethod
}

let activeMessageApi: AiVideoMessageApi | null = null

export function setAiVideoMessageApi(next: AiVideoMessageApi | null) {
  activeMessageApi = next
}

function call(level: keyof AiVideoMessageApi, content: string) {
  if (activeMessageApi) {
    activeMessageApi[level](content)
    return
  }
  const logger = level === 'error' ? console.error : level === 'warning' ? console.warn : console.info
  logger(`[AI Video] ${content}`)
}

export const aiVideoMessage: AiVideoMessageApi = {
  error: (content) => call('error', content),
  info: (content) => call('info', content),
  success: (content) => call('success', content),
  warning: (content) => call('warning', content),
}
