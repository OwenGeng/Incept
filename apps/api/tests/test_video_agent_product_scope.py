"""Research replies must not transfer one SKU's evidence to another SKU."""
import hashlib
import json

import pytest

from app.video_studio import agent, research_tools, store
from app.video_studio.models import ProjectCreate


@pytest.fixture
def existing_product(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    email = 'sku@example.com'
    project = store.create_project(email, ProjectCreate(name='SKU scope'))
    old_url, old_claim = 'https://brand.test/products/old', 'Old SKU is red.'
    snapshot = research_tools._persist_source_snapshot(email, project.id,
        {'url':old_url, 'content':old_claim}, source_type='webpage', provider='test')
    research_tools.record_claim_evidence(email, project.id, claim=old_claim, source_url=old_url,
        content_sha256=snapshot['content_sha256'], excerpt=old_claim, confidence_status='supported')
    return email, project


def test_new_sku_still_allows_recording_its_own_evidence(existing_product, monkeypatch):
    email, project = existing_product
    url, claim = 'https://brand.test/products/new', 'New SKU is blue.'
    original = agent.execute_research_tool
    def execute(name, arguments, **kwargs):
        if name == 'web_fetch':
            return research_tools._persist_source_snapshot(email, project.id,
                {'url':url, 'content':claim}, source_type='webpage', provider='test')
        return original(name, arguments, **kwargs)
    def model(prompt, parts, **kwargs):
        if 'record_claim_evidence' in kwargs.get('tool_names', []):
            return json.dumps({'tool_calls':[{'name':'record_claim_evidence', 'arguments':{
                'claim':claim, 'source_url':url, 'content_sha256':hashlib.sha256(claim.encode()).hexdigest(),
                'excerpt':claim, 'confidence_status':'supported'}}]})
        return json.dumps({'message':f'{claim} {url}', 'operations':[], 'research':{
            'status':'complete', 'sources':[url], 'findings':[claim]}})
    monkeypatch.setattr(agent, 'execute_research_tool', execute)
    monkeypatch.setattr(agent, '_call_model', model)
    _, _, delivered = agent.run_agent(email=email, project_id=project.id,
        prompt=f'调研新产品 {url}', conversation_id=None)
    assert claim in delivered
    assert 'Old SKU' not in delivered


def test_blocked_new_sku_does_not_append_unrelated_old_sku_facts(existing_product, monkeypatch):
    email, project = existing_product
    monkeypatch.setattr(agent, 'execute_research_tool', lambda *args, **kwargs: (_ for _ in ()).throw(
        research_tools.ResearchToolError('Website returned HTTP 403')))
    monkeypatch.setattr(agent, '_call_model', lambda *args, **kwargs: json.dumps({
        'message':'新产品网站返回403，无法核验，请提供客户产品资料。', 'operations':[],
        'research':{'status':'blocked', 'questions':['请提供客户产品资料。']}}))
    _, _, delivered = agent.run_agent(email=email, project_id=project.id,
        prompt='调研新产品 https://brand.test/products/new', conversation_id=None)
    assert 'Old SKU' not in delivered
    assert '/products/old' not in delivered
