import { useNavigate, useParams } from 'react-router-dom'
import { PlaceholderTab } from './PlaceholderTab'
import { getProjectEditorPath } from '../routes'
import { useAppStore } from '../../../../../store/useAppStore'

export function EditTab() {
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId: string }>()
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  return (
    <PlaceholderTab
      title={copy('Post-production', '后期剪辑')}
      description={copy('Timeline editing will be available after the project timeline API is introduced.', '项目时间线 API 接入后即可使用剪辑功能。')}
      actionLabel={copy('View availability', '查看可用状态')}
      onAction={() => projectId && navigate(getProjectEditorPath(projectId))}
    />
  )
}
