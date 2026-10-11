import json
import pytest
from app.video_studio import agent, store
from app.video_studio.models import ProjectCreate, AgentMessage
from app.video_studio.reference_research import validate_reference_report

@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    return store.create_project('isolation@example.com', ProjectCreate(name='Isolation'))

def test_new_proposal_does_not_prompt_for_research_or_search_competitors(project, monkeypatch):
    seen = []
    monkeypatch.setattr(agent, '_call_model', lambda prompt,*a,**k: seen.append(prompt) or json.dumps({'message':'先提供三个创意方向，产品细节待核验。','operations':[]}))
    monkeypatch.setattr(agent, 'execute_research_tool', lambda *a,**k: pytest.fail('No automatic research'))
    conversation, _, text = agent.run_agent(email='isolation@example.com', project_id=project.id,
        prompt='给https://brand.test/客户做CTV方案', conversation_id=None)
    assert conversation.research_question is None
    assert '三个创意方向' in text
    assert 'ctv-reference-research' not in seen[0]

def test_old_attachments_are_not_reanalyzed_and_chat_has_no_research_context(project, monkeypatch):
    seen = []
    monkeypatch.setattr(agent, '_call_model', lambda prompt,*a,**k:seen.append(prompt) or json.dumps({'message':'节点用于组织制作流程。','operations':[]}))
    monkeypatch.setattr(agent, '_asset_parts', lambda email,pid,paths,**k: (pytest.fail('Old media was analyzed') if paths else ([],[])))
    conversation, _, _ = agent.run_agent(email='isolation@example.com', project_id=project.id, prompt='说明节点作用',conversation_id=None)
    conversation.messages.insert(0, AgentMessage(id='old',role='user',content='旧客户无毒产品调研',attachments=[{'path':'old.png'}]))
    conversation.research_history = [{'name':'web_search','result':{'url':'https://old.test'}}]
    store.save_conversation('isolation@example.com', project.id, conversation)
    agent.run_agent(email='isolation@example.com',project_id=project.id,prompt='解释节点作用',conversation_id=conversation.id)
    assert '旧客户无毒' not in seen[-1]
    assert 'https://old.test' not in seen[-1]

def test_greeting_never_runs_media_research_or_production_model(project, monkeypatch):
    monkeypatch.setattr(agent,'_call_model',lambda *a,**k:pytest.fail('Greeting entered production pipeline'))
    _, _, text = agent.run_agent(email='isolation@example.com',project_id=project.id,prompt='你好呀',conversation_id=None)
    assert '你好' in text

def test_unknown_reference_is_removed_without_losing_proposal():
    result={'message':'三个创意方向', 'research':{'status':'complete'}, 'references':{'status':'partial','samples':[
        {'url':'https://youtube.com/watch?v=fake','observation_level':'link','format':'demo'}], 'limitations':[]}}
    validate_reference_report(result,[],mode='light',language='zh-CN')
    assert result['references']['samples'] == []
    assert '三个创意方向' in result['message']
    assert result['research']['status']=='needs_input'

def test_unverified_research_preserves_directions_but_not_verified_claims():
    result = {'message':'这个产品无毒。建议做安装演示。', 'research':{'status':'complete',
        'sources':['https://unobserved.test'], 'findings':['这个产品无毒。'], 'recommendations':['安装演示']}}
    agent._validate_research_result(result, email='unused',project_id='unused',needs_proposal=True,evidence=[])
    assert result['research']['status'] == 'needs_input'
    assert result['research']['sources'] == []
    assert result['research']['findings'] == []
    assert '待核验' in result['message']
    assert '安装演示' in result['message']

def test_malformed_reference_report_keeps_preliminary_answer():
    result = {'message':'安装演示方向', 'references':[]}
    validate_reference_report(result, [], mode='light',language='en')
    assert result['references']['status'] == 'blocked'
    assert '安装演示' in result['message']
