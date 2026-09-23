import { Button, Result } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { Link, useParams } from 'react-router-dom'
import { useAppStore } from '../../../store/useAppStore'

/**
 * Keep the inherited editor route honest until a persisted timeline API exists.
 *
 * The original screen presented trim, effect, and export controls backed only
 * by a removed mock client. Showing an explicit availability state is safer
 * than presenting controls that cannot save or render a project timeline.
 */
const VideoEditor = () => {
  const { projectId } = useParams<{ projectId: string }>()
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const backToProject = projectId ? `/projects/${projectId}?tab=edit` : '/projects'

  return (
    <Result
      status="info"
      title={copy('Video editing is not available yet', '视频剪辑暂不可用')}
      subTitle={copy(
        'The current API does not expose a project timeline, so this workspace cannot safely save edits or export a video.',
        '当前 API 尚未提供项目时间线，因此此工作区无法安全保存编辑或导出视频。',
      )}
      extra={
        <Link to={backToProject}>
          <Button icon={<ArrowLeftOutlined />}>{copy('Back to project', '返回项目')}</Button>
        </Link>
      }
    />
  )
}

export default VideoEditor
