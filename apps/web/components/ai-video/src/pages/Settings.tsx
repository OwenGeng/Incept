import { Card, Form, Input, Select, Button, message } from 'antd'
import { useAppStore } from '../store/useAppStore'
import { useTranslation } from 'react-i18next'

const Settings: React.FC = () => {
  const { t } = useTranslation(['settings', 'common'])
  const user = useAppStore((state) => state.user)
  const setUser = useAppStore((state) => state.setUser)

  const [form] = Form.useForm()

  const handleFinish = (values: { name: string; role: string }) => {
    setUser({ name: values.name, role: values.role })
    message.success(t('updated'))
  }

  return (
    <Card title={<h1 className="settings-page-title">{t('title')}</h1>}>
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          name: user.name,
          role: user.role,
        }}
        onFinish={handleFinish}
      >
        <Form.Item
          label={t('nickname')}
          name="name"
          rules={[{ required: true, message: t('validation.nicknameRequired') }]}
        >
          <Input placeholder={t('nickname')} />
        </Form.Item>

        <Form.Item
          label={t('role')}
          name="role"
          rules={[{ required: true, message: t('validation.roleRequired') }]}
        >
          <Select
            options={[
              { label: t('roleOptions.admin'), value: t('roleOptions.admin') },
              {
                label: t('roleOptions.operator'),
                value: t('roleOptions.operator'),
              },
              { label: t('roleOptions.guest'), value: t('roleOptions.guest') },
            ]}
          />
        </Form.Item>

        <Form.Item>
          <Button type="primary" htmlType="submit">
            {t('common:save')}
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )
}

export default Settings
