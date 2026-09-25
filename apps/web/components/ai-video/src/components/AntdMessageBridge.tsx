import { useEffect } from 'react'
import { App as AntApp } from 'antd'
import { setAiVideoMessageApi } from './aiVideoMessage'

export function AntdMessageBridge() {
  const { message } = AntApp.useApp()

  useEffect(() => {
    setAiVideoMessageApi(message)
    return () => setAiVideoMessageApi(null)
  }, [message])

  return null
}
