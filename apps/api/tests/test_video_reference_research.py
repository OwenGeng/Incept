import pytest

from app.video_studio import agent, store
from app.video_studio.models import ProjectCreate, AgentConversation, AgentMessage
from app.video_studio.agent_turns import prepare_turn, TurnControl


@pytest.fixture
def pending(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    project = store.create_project('choice@example.com', ProjectCreate(name='Consent'))
    # Compatibility for already-saved questions; new turns no longer create them.
    conversation = store.save_conversation('choice@example.com', project.id, AgentConversation(
        id='a'*32, name='Legacy consent', run_status='completed',
        messages=[AgentMessage(id='b'*32, role='user', content='给https://3wliners.com/客户做CTV方案')],
        research_question={'id':'c'*32, 'status':'pending', 'prompt':'给https://3wliners.com/客户做CTV方案'}))
    return project, conversation


def test_legacy_question_survives_reload(pending):
    project, conversation = pending
    saved = store.get_conversation('choice@example.com', project.id, conversation.id)
    assert saved.research_question['status'] == 'pending'
    assert saved.run_status == 'completed'


def test_answer_and_resume_are_idempotent_and_bound_to_question(pending):
    from app.video_studio.reference_research import answer_research_question
    project, conversation = pending
    qid = conversation.research_question['id']
    args = dict(email='choice@example.com', project_id=project.id, conversation_id=conversation.id, question_id=qid, choice='light')
    answer = answer_research_question(**args)
    assert answer_research_question(**args) == answer
    with pytest.raises(ValueError):
        answer_research_question(**{**args, 'choice': 'deep'})
    resumed = prepare_turn(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
        prompt='Continue', research_question_id=qid)
    assert resumed.research_question['resume_run_id'] == resumed.run_id
    TurnControl('choice@example.com', project.id, resumed).finish('completed')
    with pytest.raises(ValueError):
        prepare_turn(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
            prompt='Continue', research_question_id=qid)


def test_answer_cannot_cross_project_or_use_stale_id(pending):
    from app.video_studio.reference_research import answer_research_question
    project, conversation = pending
    other = store.create_project('choice@example.com', ProjectCreate(name='Other'))
    with pytest.raises(FileNotFoundError):
        answer_research_question(email='choice@example.com', project_id=other.id, conversation_id=conversation.id,
            question_id=conversation.research_question['id'], choice='light')
    with pytest.raises(ValueError):
        answer_research_question(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
            question_id='0'*32, choice='light')


def test_skip_is_off_and_new_message_invalidates_old_question(pending):
    from app.video_studio.reference_research import answer_research_question
    project, conversation = pending
    args = dict(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
                question_id=conversation.research_question['id'], choice='off', skipped=True)
    assert answer_research_question(**args)['choice'] == 'off'
    new = prepare_turn(email='choice@example.com', project_id=project.id, conversation_id=conversation.id, prompt='新客户任务')
    assert new.research_question is None
    assert new.research_decisions[-1]['choice'] == 'off'
    with pytest.raises(ValueError):
        answer_research_question(**args)


def test_declining_research_blocks_model_attempts_and_regular_followup_reuses_scope(pending, monkeypatch):
    import json
    from app.video_studio.reference_research import answer_research_question
    project, conversation = pending
    qid = conversation.research_question['id']
    answer_research_question(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
        question_id=qid, choice='off', notes='Use first-party sources only')
    prepared = prepare_turn(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
        prompt='Continue', research_question_id=qid)
    calls = []
    monkeypatch.setattr(agent, 'execute_research_tool', lambda name, *a, **k: calls.append(name) or {'error':'Website unavailable'})
    replies = iter([
        {'tool_calls':[{'name':'web_search','arguments':{'query':'competitors'}}]},
        {'tool_calls':[{'name':'web_fetch','arguments':{'url':'https://competitor.test'}}]},
        {'message':'客户网站不可用，请提供产品资料。','research':{'status':'blocked','questions':['请提供产品资料。']}}])
    monkeypatch.setattr(agent, '_call_model', lambda *a, **k:json.dumps(next(replies)))
    conversation, _, _ = agent.run_agent(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
        prompt=prepared.messages[-1].content, prepared_conversation=prepared)
    assert calls == []
    monkeypatch.setattr(agent, '_call_model', lambda *a, **k:json.dumps({'message':'客户网站不可用，请提供产品资料。',
        'research':{'status':'blocked','questions':['请提供产品资料。']}}))
    followup, _, _ = agent.run_agent(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
        prompt='继续完善这个客户方案')
    assert followup.research_question is None
    assert followup.research_decisions[-1]['notes'] == 'Use first-party sources only'
    new_client, _, _ = agent.run_agent(email='choice@example.com', project_id=project.id, conversation_id=conversation.id,
        prompt='给https://another.test/新客户出CTV方案')
    assert new_client.research_question is None


def test_new_ctv_proposal_requires_explicit_reference_skill():
    _, skills, explicit = agent._select_skills('给https://3wliners.com/客户做CTV，提供方案', store._BUILTIN_SKILLS)
    assert not explicit
    assert 'ctv-reference-research' not in {skill.id for skill in skills}
    _, skills, explicit = agent._select_skills('/skill:ctv-reference-research 研究视频参考', store._BUILTIN_SKILLS)
    assert explicit and 'ctv-reference-research' in {skill.id for skill in skills}


def test_brand_proposal_without_url_triggers_research():
    assert not agent._research_intent('给3W客户做CTV视频，提供创意方案')


@pytest.mark.parametrize('prompt', ['https://3wliners.com/ 快速出方案，不用调研',
                                    'https://3wliners.com/ Give a quick proposal without research'])
def test_explicit_skip_does_not_select_reference_research(prompt):
    assert 'ctv-reference-research' not in {s.id for s in agent._automatic_research_skills(prompt, store._BUILTIN_SKILLS)}


def test_approved_direction_does_not_restart_reference_research():
    skills = agent._automatic_research_skills('继续完善方案', store._BUILTIN_SKILLS, approved_direction=True)
    assert 'ctv-reference-research' not in {s.id for s in skills}


def test_unobserved_reference_cannot_claim_visual_analysis():
    from app.video_studio.reference_research import validate_reference_report
    result = {'message': '方案', 'research': {'status': 'complete'}, 'references': {
        'status': 'partial', 'limitations': ['Only one sample'], 'samples': [
            {'url': 'https://www.youtube.com/watch?v=test', 'format': 'demo', 'observation_level': 'visual'}]}}
    receipts = [('web_search', {'sources': [{'url': 'https://www.youtube.com/watch?v=test'}]})]
    validate_reference_report(result, receipts, mode='light', language='en')
    assert result['references']['samples'][0]['observation_level'] == 'link'
    assert result['research']['status'] == 'needs_input'


def test_complete_reference_audit_requires_real_samples_and_format_coverage():
    from app.video_studio.reference_research import validate_reference_report
    result = {'message': '方案', 'research': {'status': 'complete'}, 'references': {
        'status': 'complete', 'limitations': [], 'samples': []}}
    validate_reference_report(result, [], mode='light', language='en')
    assert result['references']['status'] == 'blocked'
    assert '方案' in result['message']


def test_missing_reference_work_is_visible_not_silently_complete():
    from app.video_studio.reference_research import validate_reference_report
    result = {'message': '初步方案', 'research': {'status': 'complete'}}
    validate_reference_report(result, [], mode='light', language='zh')
    assert result['references']['status'] == 'blocked'
    assert result['research']['status'] == 'needs_input'
    assert '参考' in result['message']


def test_transcript_is_not_visual_and_sources_must_be_observed():
    from app.video_studio.reference_research import validate_reference_report
    url = 'https://www.youtube.com/watch?v=test'
    result = {'message': 'Draft', 'research': {'status': 'complete'}, 'references': {
        'status': 'partial', 'limitations': ['Frames unavailable'], 'samples': [
            {'url': url, 'format': 'demo', 'observation_level': 'transcript', 'notes': 'Spoken wording only'}]}}
    validate_reference_report(result, [('video_transcript_fetch', {'url': url, 'content': 'Hello'})], mode='light', language='en')
    assert url in result['message']
    assert result['research']['status'] == 'needs_input'
    result['references']['samples'][0]['url'] = 'https://www.youtube.com/watch?v=invented'
    validate_reference_report(result, [], mode='light', language='en')
    assert result['references']['samples'] == []
    assert 'invented' not in result['message']
