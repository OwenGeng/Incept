import { useEffect, useState } from 'react'
import { Alert, App as AntApp, Card, Form, Select, InputNumber, Button } from 'antd'
import { LlmService } from '../../../services/generated/services/LlmService'
import type { ModelRead, ModelSettingsRead } from '../../../services/generated'
import { useAppStore } from '../../../store/useAppStore'

export default function SettingsTab() {
  const { message } = AntApp.useApp()
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const [settings, setSettings] = useState<ModelSettingsRead | null>(null)
  const [models, setModels] = useState<ModelRead[]>([])
  const [loading, setLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [settRes, modelsRes] = await Promise.all([
        LlmService.getModelSettingsApiV1LlmModelSettingsGet(),
        LlmService.listModelsApiV1LlmModelsGet({ page: 1, pageSize: 100 }),
      ])
      setSettings(settRes.data ?? null)
      setModels(modelsRes.data?.items ?? [])
    } catch {
      message.error(copy('Could not load settings', '加载失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    if (settings) {
      form.setFieldsValue({
        default_text_model_id: settings.default_text_model_id,
        default_image_model_id: settings.default_image_model_id,
        default_video_model_id: settings.default_video_model_id,
        default_speech_model_id: settings.default_speech_model_id,
        default_music_model_id: settings.default_music_model_id,
        api_timeout: settings.api_timeout,
        log_level: settings.log_level,
      })
    }
  }, [settings, form])

  const handleSaveSettings = async () => {
    try {
      const values = await form.validateFields()
      setSettingsSaving(true)
      await LlmService.updateModelSettingsApiV1LlmModelSettingsPut({
        requestBody: {
          default_text_model_id: values.default_text_model_id,
          default_image_model_id: values.default_image_model_id,
          default_video_model_id: values.default_video_model_id,
          default_speech_model_id: values.default_speech_model_id,
          default_music_model_id: values.default_music_model_id,
          api_timeout: values.api_timeout,
          log_level: values.log_level,
        },
      })
      message.success(copy('Settings saved', '设置已保存'))
      void load()
    } catch {
      message.error(copy('Could not save settings', '保存失败'))
    } finally {
      setSettingsSaving(false)
    }
  }

  const textModels = models.filter((m) => m.category === 'text')
  const imageModels = models.filter((m) => m.category === 'image')
  const videoModels = models.filter((m) => m.category === 'video')
  const speechModels = models.filter((m) => m.category === 'speech')
  const musicModels = models.filter((m) => m.category === 'music')

  return (
    <div className="flex-1 overflow-auto p-6 bg-gray-50">
      <Card title={copy('Global default models and parameters', '全局默认模型与参数')} className="max-w-2xl" loading={loading}>
        <Alert
          type="info"
          showIcon
          className="mb-4"
          message={copy('Default models are managed here. The model list does not provide a “set as default” action.', '默认模型仅在本页面统一维护，模型列表页不再提供“设为默认”操作。')}
        />
        <Form form={form} layout="vertical" onFinish={handleSaveSettings}>
          <Form.Item name="default_text_model_id" label={copy('Default text-generation model', '默认文本生成模型')}>
            <Select
              allowClear
              placeholder={copy('Select a model', '选择模型')}
              options={textModels.map((m) => ({ label: m.name, value: m.id }))}
            />
          </Form.Item>
          <Form.Item name="default_image_model_id" label={copy('Default image-generation model', '默认图片生成模型')}>
            <Select
              allowClear
              placeholder={copy('Select a model', '选择模型')}
              options={imageModels.map((m) => ({ label: m.name, value: m.id }))}
            />
          </Form.Item>
          <Form.Item name="default_video_model_id" label={copy('Default video-generation model', '默认视频生成模型')}>
            <Select
              allowClear
              placeholder={copy('Select a model', '选择模型')}
              options={videoModels.map((m) => ({ label: m.name, value: m.id }))}
            />
          </Form.Item>
          <Form.Item name="default_speech_model_id" label={copy('Default voice-generation model', '默认配音模型')}>
            <Select
              allowClear
              placeholder={copy('Select a model', '选择模型')}
              options={speechModels.map((m) => ({ label: m.name, value: m.id }))}
            />
          </Form.Item>
          <Form.Item name="default_music_model_id" label={copy('Default background-music model', '默认背景音乐模型')}>
            <Select
              allowClear
              placeholder={copy('Select a model', '选择模型')}
              options={musicModels.map((m) => ({ label: m.name, value: m.id }))}
            />
          </Form.Item>
          <Form.Item name="api_timeout" label={copy('API timeout (seconds)', 'API 超时（秒）')}>
            <InputNumber min={5} max={300} className="w-full" />
          </Form.Item>
          <Form.Item name="log_level" label={copy('Log level', '日志级别')}>
            <Select
              options={[
                { label: 'Debug', value: 'debug' },
                { label: 'Info', value: 'info' },
                { label: 'Warn', value: 'warn' },
                { label: 'Error', value: 'error' },
              ]}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={settingsSaving}>
            {copy('Save settings', '保存设置')}
          </Button>
        </Form>
      </Card>
    </div>
  )
}
