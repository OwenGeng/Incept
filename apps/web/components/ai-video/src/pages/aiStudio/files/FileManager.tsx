import { type ChangeEvent, useEffect, useMemo, useRef, useState } from 'react'
import { App as AntApp, Button, Empty, Input, Result, Select, Space, Tag } from 'antd'
import { DownloadOutlined, FileImageOutlined, ReloadOutlined, UploadOutlined, VideoCameraOutlined } from '@ant-design/icons'
import { OpenAPI, StudioFilesService, type FileRead } from '../../../services/generated'
import { useAppStore } from '../../../store/useAppStore'

/**
 * Browse real Studio files using the generated API contract.
 *
 * The former page called the removed mock endpoint and displayed a
 * card inside another card. This keeps filtering and downloads while making
 * the grid a single, scannable surface.
 */
const FileManager = () => {
  const { message } = AntApp.useApp()
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const [files, setFiles] = useState<FileRead[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [search, setSearch] = useState('')
  const [tagFilter, setTagFilter] = useState<string | undefined>()
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([])
  const [uploading, setUploading] = useState(false)
  const uploadInputRef = useRef<HTMLInputElement>(null)

  /** Load the Studio file catalog and preserve an actionable error state. */
  const loadFiles = async (query = search) => {
    setLoading(true)
    setError(false)
    try {
      const response = await StudioFilesService.listFilesApiApiV1StudioFilesGet({
        q: query.trim() || null,
        page: 1,
        pageSize: 100,
      })
      setFiles(response.data?.items ?? [])
    } catch {
      setFiles([])
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadFiles('')
    // The initial catalog should load once; searches are explicit user actions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const availableTags = useMemo(
    () => [...new Set(files.flatMap((file) => file.tags ?? []))].sort((left, right) => left.localeCompare(right)),
    [files],
  )
  const visibleFiles = useMemo(
    () => (tagFilter ? files.filter((file) => file.tags?.includes(tagFilter)) : files),
    [files, tagFilter],
  )

  /** Build a download URL with the same generated-client base as every Studio call. */
  const getDownloadUrl = (fileId: string) => `${OpenAPI.BASE.replace(/\/$/, '')}/api/v1/studio/files/${encodeURIComponent(fileId)}/download`

  const toggleSelection = (fileId: string) => {
    setSelectedFileIds((current) => current.includes(fileId) ? current.filter((id) => id !== fileId) : [...current, fileId])
  }

  const downloadSelected = () => {
    selectedFileIds.forEach((fileId) => window.open(getDownloadUrl(fileId), '_blank', 'noopener,noreferrer'))
  }

  /** Upload one supported asset through the generated API client and refresh the catalog. */
  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0]
    event.target.value = ''
    if (!selectedFile) return

    const allowedExtensions = /\.(jpe?g|png|webp|gif|mp4|mov|mkv|avi|webm)$/i
    if (!allowedExtensions.test(selectedFile.name)) {
      message.error(copy('Choose an image or video file.', '请选择图片或视频文件。'))
      return
    }

    setUploading(true)
    try {
      await StudioFilesService.uploadFileApiApiV1StudioFilesUploadPost({
        // The generated OpenAPI schema represents binary multipart fields as
        // strings, while its runtime client correctly sends a browser File.
        formData: { file: selectedFile as unknown as string },
      })
      message.success(copy('Upload complete', '上传完成'))
      await loadFiles()
    } catch {
      message.error(copy('Upload failed. Check storage configuration and try again.', '上传失败，请检查存储配置后重试。'))
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="file-manager" aria-label={copy('Files', '文件')}>
      <header className="file-manager-toolbar">
        <input
          ref={uploadInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif,video/mp4,video/quicktime,video/x-matroska,video/x-msvideo,video/webm"
          className="sr-only"
          onChange={handleUpload}
        />
        <Button type="primary" icon={<UploadOutlined />} loading={uploading} onClick={() => uploadInputRef.current?.click()}>
          {copy('Upload files', '上传素材')}
        </Button>
        <Input.Search
          allowClear
          value={search}
          placeholder={copy('Search file names', '搜索文件名')}
          onChange={(event) => setSearch(event.target.value)}
          onSearch={(value) => void loadFiles(value)}
        />
        <Select
          allowClear
          value={tagFilter}
          placeholder={copy('Filter by tag', '按标签筛选')}
          options={availableTags.map((tag) => ({ value: tag, label: tag }))}
          onChange={setTagFilter}
        />
        <Button icon={<DownloadOutlined />} disabled={selectedFileIds.length === 0} onClick={downloadSelected}>
          {copy(`Download selected${selectedFileIds.length ? ` (${selectedFileIds.length})` : ''}`, `下载所选${selectedFileIds.length ? ` (${selectedFileIds.length})` : ''}`)}
        </Button>
      </header>

      {error ? (
        <Result
          status="error"
          title={copy('Files could not be loaded', '无法加载文件')}
          subTitle={copy('Check the connection, then try again.', '请检查连接后重试。')}
          extra={<Button icon={<ReloadOutlined />} onClick={() => void loadFiles()}>{copy('Try again', '重试')}</Button>}
        />
      ) : visibleFiles.length === 0 && !loading ? (
        <Empty description={copy('No files found', '没有找到文件')} />
      ) : (
        <div className="file-manager-grid" aria-busy={loading}>
          {visibleFiles.map((file) => {
            const selected = selectedFileIds.includes(file.id)
            return (
              <article key={file.id} className={`file-manager-item ${selected ? 'is-selected' : ''}`}>
                <button
                  type="button"
                  className="file-manager-preview"
                  aria-pressed={selected}
                  aria-label={copy(`Select ${file.name}`, `选择 ${file.name}`)}
                  onClick={() => toggleSelection(file.id)}
                >
                  {file.type === 'video' ? <VideoCameraOutlined /> : <FileImageOutlined />}
                </button>
                <div className="file-manager-copy">
                  <strong title={file.name}>{file.name}</strong>
                  <Space wrap size={[4, 4]}>
                    {(file.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                  </Space>
                </div>
                <a className="file-manager-download" href={getDownloadUrl(file.id)} target="_blank" rel="noreferrer">
                  <DownloadOutlined />
                  <span>{copy('Download', '下载')}</span>
                </a>
              </article>
            )
          })}
        </div>
      )}
    </section>
  )
}

export default FileManager
