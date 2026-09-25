import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Col, Empty, Form, Input, List, Modal, Row, Select, Space, Spin, Tag, Upload } from 'antd'
import { CheckOutlined, PlusOutlined, SafetyCertificateOutlined, UploadOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../../store/useAppStore'
import { buildFileDownloadUrl } from '../../../assets/utils'
import {
  addProductAsset,
  createProduct,
  listProducts,
  selectProductAsset,
  updateProduct,
  uploadProductFile,
  type Product,
  type ProductAsset,
} from '../../../../../services/products'

type ProductFormValue = {
  name: string
  description?: string
  claimLines?: string
  prohibited_changes?: string[]
}

function claimsFromText(value?: string): Array<Record<string, string>> {
  return String(value ?? '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
    .map((text) => ({ text }))
}

function claimsToText(product?: Product | null): string {
  return (product?.claims ?? [])
    .map((claim) => String(claim.text ?? claim.claim ?? ''))
    .filter(Boolean)
    .join('\n')
}

export function ProductsTab() {
  const { message } = AntApp.useApp()
  const { projectId } = useParams<{ projectId: string }>()
  const language = useAppStore((state) => state.language)
  const copy = useCallback((en: string, zh: string) => (language === 'zh-CN' ? zh : en), [language])
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)
  const [form] = Form.useForm<ProductFormValue>()

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      setProducts(await listProducts(projectId))
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not load products.', '无法加载商品。'))
    } finally {
      setLoading(false)
    }
  }, [copy, message, projectId])

  useEffect(() => { void load() }, [load])

  const openEditor = (product?: Product) => {
    setEditing(product ?? null)
    form.setFieldsValue({
      name: product?.name ?? '',
      description: product?.description ?? '',
      claimLines: claimsToText(product),
      prohibited_changes: product?.prohibited_changes ?? [],
    })
    setEditorOpen(true)
  }

  const saveProduct = async () => {
    if (!projectId) return
    const values = await form.validateFields()
    setSaving(true)
    try {
      const body = {
        name: values.name.trim(),
        description: values.description?.trim() ?? '',
        claims: claimsFromText(values.claimLines),
        prohibited_changes: values.prohibited_changes ?? [],
      }
      if (editing) await updateProduct(projectId, editing.id, body)
      else await createProduct(projectId, body)
      setEditorOpen(false)
      message.success(copy('Product saved.', '商品已保存。'))
      await load()
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    } finally {
      setSaving(false)
    }
  }

  const attachFile = async (product: Product, file: File, role: 'truth_anchor' | 'standardized') => {
    if (!projectId) return
    const anchor = product.assets.find((asset) => asset.role === 'truth_anchor')
    if (role === 'standardized' && !anchor) {
      message.warning(copy('Upload a truth anchor first.', '请先上传商品原始真值素材。'))
      return
    }
    setSaving(true)
    try {
      const fileId = await uploadProductFile(projectId, file)
      await addProductAsset(projectId, product.id, {
        file_id: fileId,
        role,
        source_asset_id: role === 'standardized' ? anchor?.id : null,
        metadata: { source: role === 'truth_anchor' ? 'customer_upload' : 'standardized_upload' },
      })
      message.success(copy('Product asset added.', '商品素材已添加。'))
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not add product asset.', '无法添加商品素材。'))
    } finally {
      setSaving(false)
    }
  }

  const selectAsset = async (product: Product, asset: ProductAsset) => {
    if (!projectId) return
    setSaving(true)
    try {
      await selectProductAsset(projectId, product.id, asset.id)
      message.success(copy('Production asset selected.', '已选为制作使用素材。'))
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not select asset.', '无法选用素材。'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4 overflow-auto pb-8">
      <Card
        title={copy('Products & truth assets', '商品与真值素材')}
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor()}>{copy('Add product', '添加商品')}</Button>}
      >
        <Alert
          type="info"
          showIcon
          message={copy('Truth anchors are immutable source evidence.', '原始真值素材是不可修改的商品依据。')}
          description={copy(
            'Standardized crops or cleaned packshots keep lineage to the original. Generation never silently replaces the selected production asset.',
            '裁切、清理后的标准化商品图会保留到原图的来源链；任何生成结果都不会静默替换已选素材。',
          )}
        />
      </Card>

      <Spin spinning={loading || saving}>
        {products.length === 0 && !loading ? (
          <Card><Empty description={copy('No products yet.', '还没有商品。')}><Button type="primary" onClick={() => openEditor()}>{copy('Create first product', '创建第一个商品')}</Button></Empty></Card>
        ) : (
          <Row gutter={[16, 16]}>
            {products.map((product) => {
              const anchor = product.assets.find((asset) => asset.role === 'truth_anchor')
              return (
                <Col xs={24} xl={12} key={product.id}>
                  <Card
                    title={product.name}
                    extra={<Button type="link" onClick={() => openEditor(product)}>{copy('Edit facts', '编辑事实')}</Button>}
                  >
                    <p className="text-sm text-slate-600">{product.description || copy('No product description.', '暂无商品说明。')}</p>
                    <Space wrap className="mt-2">
                      {product.prohibited_changes.map((item) => <Tag color="red" key={item}>{copy('Do not change', '禁止修改')} · {item}</Tag>)}
                    </Space>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Upload showUploadList={false} accept="image/*,video/*" beforeUpload={(file) => { void attachFile(product, file, 'truth_anchor'); return false }}>
                        <Button icon={<SafetyCertificateOutlined />}>{copy('Upload truth anchor', '上传原始真值素材')}</Button>
                      </Upload>
                      <Upload showUploadList={false} accept="image/*" disabled={!anchor} beforeUpload={(file) => { void attachFile(product, file, 'standardized'); return false }}>
                        <Button icon={<UploadOutlined />} disabled={!anchor}>{copy('Upload standardized candidate', '上传标准化候选')}</Button>
                      </Upload>
                    </div>
                    <List
                      className="mt-4"
                      locale={{ emptyText: copy('No product assets.', '暂无商品素材。') }}
                      dataSource={product.assets}
                      renderItem={(asset) => {
                        const selected = product.selected_asset_id === asset.id
                        return (
                          <List.Item
                            actions={[
                              <a key="preview" href={buildFileDownloadUrl(asset.file_id)} target="_blank" rel="noreferrer">{copy('Preview', '预览')}</a>,
                              <Button key="select" size="small" type={selected ? 'primary' : 'default'} icon={selected ? <CheckOutlined /> : undefined} onClick={() => void selectAsset(product, asset)}>
                                {selected ? copy('Selected', '已选用') : copy('Use in production', '用于制作')}
                              </Button>,
                            ]}
                          >
                            <List.Item.Meta
                              title={<Space wrap><span>{asset.role === 'truth_anchor' ? copy('Original truth anchor', '原始真值素材') : copy('Standardized candidate', '标准化候选')}</span><Tag color={asset.role === 'truth_anchor' ? 'gold' : 'blue'}>{asset.role}</Tag>{selected ? <Tag color="success">selected</Tag> : null}</Space>}
                              description={asset.role === 'standardized' ? `${copy('Derived from', '来源')} ${asset.source_asset_id}` : copy('Customer/source supplied; kept immutable.', '客户/来源方提供；保持不可变。')}
                            />
                          </List.Item>
                        )
                      }}
                    />
                  </Card>
                </Col>
              )
            })}
          </Row>
        )}
      </Spin>

      <Modal
        title={editing ? copy('Edit product facts', '编辑商品事实') : copy('Add product', '添加商品')}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={() => void saveProduct()}
        confirmLoading={saving}
        okText={copy('Save', '保存')}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={copy('Product name', '商品名称')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={copy('Verified description', '已核实商品说明')}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="claimLines" label={copy('Approved claims (one per line)', '允许使用的卖点（每行一条）')}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="prohibited_changes" label={copy('Never change', '禁止修改')}><Select mode="tags" tokenSeparators={[',', '，', '\n']} placeholder={copy('Logo, package shape, label…', 'Logo、包装形状、标签……')} /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
