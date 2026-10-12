import pytest

from app.video_studio.pi_tools import CanvasTools, read_skill, node_functions, validate_storyboard
from app.video_studio.models import CanvasDocument, SkillDefinition, VideoNode
from app.video_studio.pi_agent import select_model


def add(tools, kind, x=0):
    return tools.execute('addNode', {'type': kind + 'Node', 'position': {'x': x, 'y': 0}})['node']['id']


def test_canvas_exact_vue_ports_and_atomic_batch_changes():
    tools = CanvasTools(CanvasDocument(), {'text', 'imageGeneration', 'videoGeneration', 'audio'})
    text, image, video = add(tools, 'text'), add(tools, 'imageGeneration'), add(tools, 'videoGeneration')
    snapshot = tools.execute('getCanvas', {})
    image_type = next(kind for kind in snapshot['availableNodeTypes'] if kind['type'] == 'imageGenerationNode')
    assert image_type['inputs'] == ['in']
    tools.execute('nodeTools', {'nodeId': image, 'name': 'node:setPrompt', 'args': {'prompt': 'Product detail\nSame brand'}})
    tools.execute('connectNodes', {'connections': [{'source': text, 'sourceHandle': 'text', 'target': image, 'targetHandle': 'in'}]})
    tools.execute('connectNodes', {'connections': [{'source': image, 'sourceHandle': 'image', 'target': video, 'targetHandle': 'in'}]})
    tools.execute('moveNodes', {'moves': [{'nodeId': text, 'position': {'x': 20, 'y': 30}}]})
    tools.execute('renameNodes', {'renames': [{'nodeId': text, 'label': 'Script'}]})
    assert tools.canvas.nodes[0].position.x == 20
    assert tools.canvas.nodes[0].data['label'] == 'Script'
    assert tools.canvas.nodes[1].data['promptModel'][0] == [{'type': 'Write', 'text': 'Product detail'}]
    original = tools.canvas.model_dump()
    with pytest.raises(ValueError, match='already connected'):
        tools.execute('connectNodes', {'connections': [{'source': text, 'sourceHandle': 'text', 'target': image, 'targetHandle': 'in'}]})
    assert tools.canvas.model_dump() == original
    tools.execute('deleteEdges', {'edgeIds': [tools.canvas.edges[0].id]})
    tools.execute('deleteNodes', {'nodeIds': [video]})
    assert tools.canvas.edges == []
    assert tools.changed


def test_canvas_rejects_invalid_tools_and_never_mutates_failed_batch():
    tools = CanvasTools(CanvasDocument(), {'text', 'image', 'videoGeneration'})
    text, image, video = add(tools, 'text'), add(tools, 'image'), add(tools, 'videoGeneration')
    assert node_functions(VideoNode(id='other', type='image')) == []
    cases = [
        ('addNode', {'type': 'audioNode', 'position': {'x': 0, 'y': 0}}),
        ('nodeTools', {'nodeId': text, 'name': 'node:setText', 'args': {}}),
        ('nodeTools', {'nodeId': text, 'name': 'node:setText', 'args': {'text': 4}}),
        ('nodeTools', {'nodeId': text, 'name': 'node:setText', 'args': {'text': 'x', 'expectedText': 'stale'}}),
        ('nodeTools', {'nodeId': video, 'name': 'node:setPrompt', 'args': {}}),
        ('nodeTools', {'nodeId': image, 'name': 'node:generateImage', 'args': {}}),
        ('deleteNodes', {'nodeIds': [text, 'missing']}),
        ('deleteEdges', {'edgeIds': ['missing']}),
        ('connectNodes', {'connections': [{'source': text, 'sourceHandle': 'invented', 'target': video, 'targetHandle': 'in'}]}),
        ('unknown', {}),
    ]
    original = tools.canvas.model_dump()
    for name, args in cases:
        with pytest.raises(ValueError):
            tools.execute(name, args)
        assert tools.canvas.model_dump() == original


def test_skill_catalog_and_references_are_real_and_path_scoped(monkeypatch):
    monkeypatch.delenv('INCEPT_PROJECT_ROOT', raising=False)
    custom = SkillDefinition(id='manual-research', name='Research', instructions='User-invoked research only.')
    listed = read_skill({'action': 'list'}, [custom])
    assert any(item['name'] == 'workflow' for item in listed['skills'])
    assert listed['skills'][1]['disableModelInvocation']
    creative = SkillDefinition(id='ctv-creative-strategy', name='Creative', builtin=True)
    research = SkillDefinition(id='ctv-reference-research', name='Research', builtin=True)
    kinds = read_skill({'action': 'list'}, [creative, research])['skills']
    assert not kinds[1]['disableModelInvocation']
    assert kinds[2]['disableModelInvocation']
    assert 'PART A' in read_skill({'action': 'read', 'name': 'workflow'}, [])['content']
    assert read_skill({'action': 'read', 'name': 'workflow', 'path': 'references/canvasExecution.md'}, [])['content']
    assert read_skill({'action': 'read', 'name': custom.id}, [custom])['content'] == custom.instructions
    for args in [{'name': 'workflow', 'path': '../../../../../package.json'}, {'name': 'workflow', 'path': '/etc/passwd'}, {'name': 'missing'}, {'name': custom.id, 'path': 'unknown.md'}]:
        with pytest.raises(ValueError):
            read_skill({'action': 'read', **args}, [custom])


@pytest.mark.parametrize('times', [[(0, 5), (6, 30)], [(0, 5), (4, 30)], [(0, 5), (5, 20)], [(0, 5), (5, 5)]])
def test_invalid_structured_timing_returns_local_feedback_without_rejecting_draft(times):
    result = validate_storyboard({'duration': 30, 'shots': [{'start': start, 'end': end} for start, end in times]})
    assert not result['valid'] and result['errors']


def test_exact_timeline_passes_and_model_selection_never_guesses():
    result = validate_storyboard({'duration': 30, 'shots': [{'start': a, 'end': b} for a, b in [(0, 5), (5, 11), (11, 17), (17, 23), (23, 30)]]})
    assert result['valid'] and result['errors'] == []
    with pytest.raises(ValueError, match='not enabled'):
        select_model('invented', 'invented')


@pytest.mark.parametrize('args', [{'duration': 0, 'shots': []}, {'duration': 30, 'shots': [{'start': float('nan'), 'end': 30}]}, {'duration': 30, 'shots': [{'start': 0, 'end': True}]}])
def test_structured_timing_rejects_invalid_numeric_inputs(args):
    with pytest.raises(ValueError):
        validate_storyboard(args)


def test_unrelated_old_timelines_are_not_revalidated_and_external_documents_are_not_overwritten():
    original = CanvasDocument(nodes=[VideoNode(id='old', type='text', data={'textSnapshot': '0–15s old campaign'})])
    modified = original.model_copy(deep=True)
    modified.nodes.append(VideoNode(id='new', type='text', data={'textSnapshot': '0–5s hook; 5–30s CTA'}))
    assert modified.nodes[0].data == original.nodes[0].data
    file_node = VideoNode(id='live', type='text', data={'textPath': 'assets/live/content.md'})
    tools = CanvasTools(CanvasDocument(nodes=[file_node]), {'text'})
    assert node_functions(file_node) == []
    with pytest.raises(ValueError, match='external document'):
        tools.execute('nodeTools', {'nodeId': 'live', 'name': 'node:setText', 'args': {'text': 'overwrite'}})


def test_draft_text_is_not_rewritten_by_the_host_or_treated_as_advertising_approval():
    tools = CanvasTools(CanvasDocument(), {'text'})
    node = add(tools, 'text')
    result = tools.execute('nodeTools', {'nodeId': node, 'name': 'node:setText', 'args': {'text': 'Non-toxic material. Show custom fit and cleaning.'}})
    assert result['text'] == 'Non-toxic material. Show custom fit and cleaning.'
    assert result['status'] == 'staged_pending_commit'
    assert 'Show custom fit and cleaning.' in result['text']


def test_campaign_rules_are_read_through_matching_builtin_skill_not_generic_workflow():
    creative = SkillDefinition(id='ctv-creative-strategy', name='CTV', builtin=True, instructions='Use verified facts.')
    content = read_skill({'action': 'read', 'name': creative.id}, [creative])['content']
    assert content.startswith(creative.instructions)
    assert "For Moloco CTV, use the customer's campaign profile" in content
    assert '450 MB' in content
    assert "For Moloco CTV, use the customer's campaign profile" not in read_skill({'action': 'read', 'name': 'workflow'}, [])['content']
    custom = SkillDefinition(id='ctv-creative-strategy', name='Custom', instructions='User-defined workflow.')
    assert read_skill({'action': 'read', 'name': custom.id}, [custom])['content'] == custom.instructions
