from __future__ import annotations

import json
import httpx
import pytest

from app.video_studio import website_assets as media, research_tools, store, agent
from app.video_studio.creative_specs import moloco_ctv_profile, check_moloco_ctv_metadata
from app.video_studio.models import ProjectCreate, CanvasDocument, AgentConversation


def public_dns(host, port, **kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_STUDIO_DATA_DIR", str(tmp_path))
    return store.create_project("media@example.com", ProjectCreate(name="Website assets"))


HTML = '''<html><head><title>Client Store</title><meta name="description" content="Product description">
<link rel="icon" href="/favicon.ico"></head><body><img src="/logo.png" alt="Brand logo">
<img src="/low.jpg" srcset="/small.jpg 100w, /large.jpg 1000w" alt="Product A">
<video poster="/poster.jpg"><source src="/demo.mp4"></video>
<a href="/collections/best-sellers">Best sellers</a><a href="https://other.test/best-sellers">External</a>
<script type="application/ld+json">{"@type":"Product","name":"Model Y Juniper","description":"Fits specified years only","image":"/sku.jpg","video":{"@type":"VideoObject","contentUrl":"/sku.mp4"}}</script></body></html>'''


def discover(project, handler):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return media.discover_website_assets("media@example.com", project.id, "https://client.test/", client=client, resolver=public_dns)


def test_discover_public_media_and_observed_bestseller_products(project):
    requested = []
    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/collections/best-sellers":
            content = '<a href="/products/model-y">Model Y</a>'
        elif request.url.path == "/products/model-y":
            content = '<script type="application/ld+json">{"@type":"Product","name":"Model Y","image":"/best.jpg"}</script>'
        else: content = HTML
        return httpx.Response(200, headers={"content-type": "text/html"}, text=content)
    result = discover(project, handler)
    by_url = {a["source_url"]: a for a in result["assets"]}
    assert by_url["https://client.test/logo.png"]["kind"] == "logo"
    assert by_url["https://client.test/favicon.ico"]["kind"] == "icon"
    assert "https://client.test/large.jpg" in by_url
    assert "https://client.test/low.jpg" not in by_url
    assert by_url["https://client.test/sku.jpg"]["name"] == "Model Y Juniper"
    assert by_url["https://client.test/sku.mp4"]["product_url"] == "https://client.test/"
    assert by_url["https://client.test/best.jpg"]["bestseller_evidence"]
    assert not by_url["https://client.test/sku.jpg"]["bestseller_evidence"]
    assert all(a["rights_status"] == "unverified" and a["status"] == "discovered" for a in result["assets"])
    assert len(requested) == 3 and all("other.test" not in url for url in requested)


def test_large_product_page_retains_gallery_and_lazy_direct_video(project):
    html = ('<html><title>Bronco</title>' + '<!--' + 'x' * 2_100_000 + '-->'
        + '<video aria-label="Bronco demonstration" data-poster-src="//client.test/bronco.mp4#t=2"></video>'
        + '<script type="application/ld+json">' + json.dumps({
            '@type':'Product', 'name':'Bronco mats', 'url':'/products/bronco',
            'image':[f'/bronco-{i}.jpg' for i in range(24)]}) + '</script></html>')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, headers={'content-type':'text/html'}, text=html))) as client:
        result = media.discover_website_assets('media@example.com', project.id,
            'https://client.test/products/bronco', client=client, resolver=public_dns)
    product_images = [item for item in result['assets'] if item['kind'] == 'image' and item['product_url']]
    assert len(product_images) == 24
    assert any(item['source_url'] == 'https://client.test/bronco.mp4' and item['kind'] == 'video' for item in result['assets'])


def test_structured_gallery_is_not_starved_by_navigation_images(project):
    html = ''.join(f'<img src="/navigation-{i}.jpg">' for i in range(220))
    html += '<script type="application/ld+json">' + json.dumps({
        '@type':'Product','name':'Requested SKU','url':'/products/sku','image':['/gallery.jpg']}) + '</script>'
    result = discover(project, lambda r: httpx.Response(200, headers={'content-type':'text/html'}, text=html))
    assert any(item['source_url'].endswith('/gallery.jpg') and item['product_url'] for item in result['assets'])


def test_bestseller_traversal_reads_more_than_four_pages_without_inventing_products(project):
    requested = []
    def handler(request):
        requested.append(request.url.path)
        if request.url.path == '/': html = '<a href="/collections/best-sellers">Best sellers</a>'
        elif request.url.path == '/collections/best-sellers': html = ''.join(f'<a href="/products/sku-{i}">SKU {i}</a>' for i in range(6))
        else: html = f'<img src="{request.url.path}.jpg">'
        return httpx.Response(200, headers={'content-type':'text/html'}, text=html)
    result = discover(project, handler)
    assert result['pages_inspected'] == 8
    assert all(f'/products/sku-{i}' in requested for i in range(6))


def test_product_seed_does_not_collect_unrelated_navigation_skus(project):
    requested = []
    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(200, headers={'content-type':'text/html'}, text='<img src="/selected.jpg"><a href="/products/other">Other</a><a href="/collections/best-sellers">Best sellers</a>')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        media.discover_website_assets('media@example.com', project.id, 'https://client.test/products/selected', client=client, resolver=public_dns)
    assert requested == ['/products/selected']


def test_dom_product_gallery_has_sku_scope_but_recommendations_do_not():
    parser = media.MediaParser('https://client.test/products/bronco')
    parser.feed('<img src="/navigation.jpg"><product-gallery><div><img src="/detail.jpg" alt="Detail">'
        '<video><source src="/installation.mp4"></video></div></product-gallery><img src="/other-car.jpg">')
    parser.structured_media()
    by_url = {item['source_url']:item for item in parser.media}
    assert by_url['https://client.test/detail.jpg']['product_url'] == parser.url
    assert by_url['https://client.test/installation.mp4']['product_url'] == parser.url
    assert not by_url['https://client.test/other-car.jpg'].get('product_url')


def test_oversize_page_is_still_bounded(project):
    with pytest.raises(research_tools.ResearchToolError, match='采集限制'):
        discover(project, lambda r: httpx.Response(200, headers={'content-type':'text/html'}, content=b'x' * 8_000_001))


@pytest.mark.parametrize("url", ["https://127.0.0.1/a", "https://metadata.google.internal/a", "https://user:pass@public.test/a", "http://public.test/a", "https://public.test:8443/a"])
def test_discovery_rejects_unsafe_targets(project, url):
    with pytest.raises(research_tools.ResearchToolError):
        media.discover_website_assets("media@example.com", project.id, url, resolver=public_dns)


def test_mixed_dns_and_rebinding_are_rejected_and_connection_is_pinned(monkeypatch):
    with pytest.raises(research_tools.ResearchToolError):
        media._pinned_target("https://public.test/a", lambda *a, **kw: public_dns(*a, **kw) + [(2, 1, 6, "", ("10.0.0.1", 0))])
    monkeypatch.setattr(media, "_pinned_target", lambda url: (url, "93.184.216.34", "public.test"))
    calls = []
    def handle(self, request):
        calls.append(request)
        return httpx.Response(200)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    with media.PublicMediaTransport() as transport:
        transport.handle_request(httpx.Request("GET", "https://public.test/a"))
    assert calls[0].url.host == "93.184.216.34"
    assert calls[0].headers["host"] == "public.test"
    assert calls[0].extensions["sni_hostname"] == "public.test"


def test_import_is_idempotent_has_sources_and_local_preview_path(project):
    result = discover(project, lambda r: httpx.Response(200, headers={"content-type": "text/html"}, text='<img src="/photo.png" alt="Car mat">'))
    ids = [result["assets"][0]["id"]]
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG\r\n\x1a\ncontent")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = media.import_website_assets("media@example.com", project.id, ids, client=client, resolver=public_dns)
        again = media.import_website_assets("media@example.com", project.id, ids, client=client, resolver=public_dns)
    asset = first["assets"][0]
    assert first["imported_count"] == again["imported_count"] == 1
    assert len(calls) == 1
    assert asset["workspace_path"] == f'library/website/{ids[0]}.png'
    assert store.safe_asset_path(store.assets_root("media@example.com", project.id), asset["workspace_path"]).read_bytes().startswith(b"\x89PNG")
    assert asset["source_url"] == "https://client.test/photo.png" and asset["rights_status"] == "unverified"
    with pytest.raises(FileNotFoundError): media.list_website_assets("another@example.com", project.id)


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"location": "http://127.0.0.1/"}), httpx.Response(200, content=b"<html>not an image</html>"), httpx.Response(200, content=b"<svg><script/></svg>"), httpx.Response(200, headers={"content-length": "999999999"}, content=b"x")])
def test_import_failure_never_saves_invalid_partial_or_redirected_files(project, response):
    result = discover(project, lambda r: httpx.Response(200, headers={"content-type": "text/html"}, text='<img src="/bad.jpg">'))
    with httpx.Client(transport=httpx.MockTransport(lambda r: response)) as client:
        imported = media.import_website_assets("media@example.com", project.id, [result["assets"][0]["id"]], client=client, resolver=public_dns)
    assert imported["failed_count"] == 1 and imported["imported_count"] == 0
    root = store.assets_root("media@example.com", project.id)
    assert not list(root.glob("library/website/*"))


def test_tools_require_both_web_access_and_workspace_storage():
    assert not any(t["name"].startswith("website_assets_") for t in research_tools.available_research_tools({"tool-web-fetch"}))
    assert {"website_assets_discover", "website_assets_import", "list_website_assets"} <= {t["name"] for t in research_tools.available_research_tools({"tool-web-fetch", "tool-workspace"})}


def test_icon_titles_do_not_pollute_product_name_and_jsonld_product_link_is_preserved():
    parser = media.MediaParser("https://client.test/")
    parser.feed('<title>Client Store</title><svg><title>Visa</title></svg><script type="application/ld+json">{"@type":"Product","url":"/products/model-y","name":"Model Y","description":"&lt;p&gt;Fits selected years&lt;/p&gt;","image":"/sku.jpg"}</script>')
    parser.structured_media()
    assert parser.title == "Client Store"
    assert parser.media[0]["product_url"] == "https://client.test/products/model-y"


def test_unknown_asset_ids_cannot_be_downloaded(project):
    with pytest.raises(research_tools.ResearchToolError, match="当前项目"):
        media.import_website_assets("media@example.com", project.id, ["a" * 32])


def test_agent_specs_and_latest_request_survive_large_tool_history():
    latest = "方向1，30秒；帮我拉取best seller图片，不要重做方案"
    prompt = agent._agent_prompt(user_prompt=latest, canvas=CanvasDocument(), conversation=AgentConversation(id="audit", name="Audit"), language="zh-CN", custom_system_prompt="", agent_id="default", skills=[], asset_manifest=[], allowed_node_types={"text"}, allow_canvas_edits=True, research_tools=[], tool_history=[{"content": "long webpage" * 5000}])
    assert latest in prompt[:12_000]
    assert "450 MB" in prompt[:12_000] and "<=50 MB" not in prompt
    profile = moloco_ctv_profile()
    assert profile["duration_seconds"]["recommended"] == [15, 30, 60]
    assert profile["max_file_bytes"] == 450_000_000
    assert profile["approval_status"] == "customer_configuration_confirmed"


def test_agent_vertex_wire_preserves_long_context(monkeypatch):
    from types import SimpleNamespace
    from app.incept import vertex_generation
    captured = {}
    def generate(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text='{"message":"ok","operations":[],"tool_calls":[]}')]))])
    monkeypatch.setattr(vertex_generation.genai, "Client", lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    prompt = "latest user request\n" + "long evidence" * 5000 + "\nconversation memory"
    agent._call_model(prompt, [], provider_id="google-vertex-ai", model_id="gemini-3.8-flash")
    assert captured["contents"][0].parts[0].text == prompt


def test_agent_asset_intake_runs_tools_without_proposal_gate(project, monkeypatch):
    prompts, calls = [], []
    replies = iter([
        {"message": "正在发现", "operations": [], "tool_calls": [{"name": "website_assets_discover", "arguments": {"url": "https://client.test"}}]},
        {"message": "正在导入", "operations": [], "tool_calls": [{"name": "website_assets_import", "arguments": {"asset_ids": ["a" * 32]}}]},
        {"message": "已导入1张图片；画布 → 素材库 → 客户网站素材，授权待确认。", "operations": [], "tool_calls": []},
    ])
    def model(prompt, parts, **kwargs):
        prompts.append(prompt)
        return json.dumps(next(replies), ensure_ascii=False)
    def tool(name, arguments, **kwargs):
        calls.append(name)
        return {"assets": [{"id": "a" * 32, "path": "website/a.png"}], "imported_count": 1}
    monkeypatch.setattr(agent, "_call_model", model)
    monkeypatch.setattr(agent, "execute_research_tool", tool)
    _, _, message = agent.run_agent(email="media@example.com", project_id=project.id, prompt="帮我调研并拉取客户图片 https://client.test", conversation_id=None)
    assert calls == ["website_assets_discover", "website_assets_import"]
    assert "已导入1张" in message
    assert all("This is a research request" not in prompt for prompt in prompts)
    assert all('"id": "storyboard"' not in prompt for prompt in prompts)


def test_large_catalog_keeps_structured_selection_ids_in_agent_context():
    assets = [{'id':f'{i:032x}', 'kind':'image','name':'Product gallery',
        'product_url':'https://client.test/products/sku','source_url':f'https://client.test/{i}.jpg',
        'description':'large description' * 1000,'status':'discovered'} for i in range(100)]
    entry = agent._tool_history_entry({'id':'discover','name':'website_assets_discover','arguments':{}}, {'assets':assets})
    assert isinstance(entry['result'], dict)
    assert entry['result']['assets'][0]['id'] == assets[0]['id']
    assert len(json.dumps(entry['result'], ensure_ascii=False)) <= agent.MAX_TOOL_RESULT_CHARS
    assert entry['result']['asset_count'] == 100


def test_agent_does_not_stop_at_branding_when_product_gallery_is_available(project, monkeypatch):
    logo = {'id':'a'*32, 'kind':'logo', 'status':'imported'}
    photo = {'id':'b'*32, 'kind':'image', 'product_url':'https://client.test/products/sku', 'status':'discovered'}
    replies = iter([
        {'message':'发现素材','tool_calls':[{'name':'website_assets_discover','arguments':{'url':'https://client.test'}}]},
        {'message':'导入Logo','tool_calls':[{'name':'website_assets_import','arguments':{'asset_ids':['a'*32]}}]},
        {'message':'已导入1个素材，制作素材齐了。','operations':[]},
        {'message':'补充商品图','tool_calls':[{'name':'website_assets_import','arguments':{'asset_ids':['b'*32]}}]},
        {'message':'已导入2个素材；商品图已补充，尚需视频源片。','operations':[]},
    ])
    imports=[]
    monkeypatch.setattr(agent,'_call_model',lambda *a,**kw:json.dumps(next(replies),ensure_ascii=False))
    def tool(name,args,**kw):
        if name == 'website_assets_discover': return {'assets':[logo,photo]}
        imports.extend(args['asset_ids'])
        return {'assets':[dict(logo if args['asset_ids'][0]=='a'*32 else photo,status='imported')], 'imported_count':1}
    monkeypatch.setattr(agent,'execute_research_tool',tool)
    agent.run_agent(email='media@example.com',project_id=project.id,prompt='帮我导入客户商品图片 https://client.test',conversation_id=None)
    assert imports == ['a'*32,'b'*32]


def test_no_canvas_edits_preserves_concurrent_user_changes(project, monkeypatch):
    from app.video_studio.models import VideoNode, Position
    def model(prompt, parts, **kwargs):
        canvas = store.get_project("media@example.com", project.id).canvas
        canvas.nodes.append(VideoNode(id="new-user-node", type="text", position=Position(x=1, y=2), data={"text": "preserve me"}))
        store.save_canvas("media@example.com", project.id, canvas)
        return '{"message":"可以采集公开素材。","operations":[],"tool_calls":[]}'
    monkeypatch.setattr(agent, "_call_model", model)
    agent.run_agent(email="media@example.com", project_id=project.id, prompt="请说明客户图片如何处理", conversation_id=None)
    assert store.get_project("media@example.com", project.id).canvas.nodes[0].id == "new-user-node"


def test_chat_only_stream_does_not_replace_canvas(project, monkeypatch, tmp_path):
    from test_video_legacy_api import client, headers
    from app.video_studio import pi_agent
    from test_video_pi_agent import reply
    api = client(tmp_path, monkeypatch)
    monkeypatch.setattr(pi_agent, 'model_response', lambda p, **kw: reply(p, '可以采集公开素材。'))
    response = api.post("/video-legacy/api/agent", headers=headers("media@example.com"), json={"directory": project.id, "prompt": "能抓取客户图片吗"})
    assert "canvasCall" not in response.text and '"type": "done"' in response.text


def test_compatibility_routes_and_readback(project, monkeypatch, tmp_path):
    from test_video_legacy_api import client, headers
    api = client(tmp_path, monkeypatch)
    specs = api.get("/video-legacy/api/assets/creative-profile", headers=headers("media@example.com"))
    assert specs.status_code == 200 and specs.json()["data"]["format"] == "mp4"
    assert api.get("/video-legacy/api/assets/website", params={"directory": project.id}, headers=headers("another@example.com")).status_code == 404


@pytest.mark.parametrize("width,height,fps,duration,size,is_mp4,passes", [
    (1920, 1080, "30/1", "30", 1_000_000, True, True),
    (1280, 720, "24000/1001", "15", 1_000_000, True, False),
    (1280, 720, "24/1", "60", 450_000_000, True, True),
    (1920, 1080, "30/1", "30", 450_000_001, True, False),
    (1080, 1920, "30/1", "30", 1_000_000, True, False),
    (1920, 1080, "0/0", "30", 1_000_000, True, False),
    (1920, 1080, "30/1", "181", 1_000_000, True, False),
    (1920, 1080, "30/1", "NaN", 1_000_000, True, False),
    (1920, 1080, "30/1", "30", 1_000_000, False, False),
])
def test_ctv_technical_validation_never_grants_exchange_approval(width, height, fps, duration, size, is_mp4, passes):
    result = check_moloco_ctv_metadata({"streams": [{"codec_type": "video", "width": width, "height": height, "avg_frame_rate": fps}], "format": {"duration": duration}}, size=size, is_mp4=is_mp4)
    assert result["technical_checks_passed"] is passes
    assert result["approved_for_delivery"] is False
    assert isinstance(result['warnings'], list)
