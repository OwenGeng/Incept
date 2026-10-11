import threading
import pytest
from app.video_studio import store, pi_runs
from app.video_studio.models import ProjectCreate
from app.video_studio.agent_turns import prepare_turn, TurnControl

EMAIL = 'runs@example.com'

@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setenv('VIDEO_STUDIO_DATA_DIR', str(tmp_path))
    project = store.create_project(EMAIL, ProjectCreate(name='Events'))
    conv = prepare_turn(email=EMAIL, project_id=project.id, prompt='Hello', conversation_id=None)
    return pi_runs.RunJournal(EMAIL, project.id, conv.id, conv.run_id), conv

def test_replay_cursor_identity_and_scope(run):
    journal, conv = run
    journal.create()
    assert journal.emit({'type':'text', 'blockId':'b', 'delta':'Hello'})['sequence'] == 1
    journal.emit({'type':'text','blockId':'b','delta':' again'})
    assert [e['sequence'] for e in journal.events(1)] == [2]
    restored = pi_runs.RunJournal(EMAIL, journal.project_id, conv.id, conv.run_id)
    assert restored.events(0)[0]['delta'] == 'Hello'
    with pytest.raises(FileNotFoundError):
        pi_runs.RunJournal('other@example.com', journal.project_id, conv.id, conv.run_id).state()

def test_controls_are_scoped_ordered_and_do_not_approve_mutation(run):
    journal, _ = run
    journal.create()
    journal.enqueue('steer','Keep the brand')
    journal.enqueue('followUp','Next draft')
    assert [e['type'] for e in journal.commands(0)] == ['steer','followUp']
    assert journal.commands(1)[0]['prompt'] == 'Next draft'
    with pytest.raises(ValueError): journal.enqueue('approve','Anything')
    journal.finish('completed')
    with pytest.raises(ValueError): journal.enqueue('steer','Late')

def test_question_answer_single_use_skip_not_consent(run):
    journal, conv = run
    journal.create()
    control = TurnControl(EMAIL, journal.project_id, conv)
    answers = []
    def ask(): answers.append(journal.ask('tool-1', {'title':'Direction','question':'Which?', 'options':['A','B']}, control))
    thread = threading.Thread(target=ask)
    thread.start()
    for _ in range(100):
        events = journal.events(0)
        if any(e['type']=='question' for e in events): break
        threading.Event().wait(.01)
    question = next(e for e in events if e['type']=='question')
    assert question['sessionFile'] == f'agent/{conv.id}.json'
    pi_runs.answer(EMAIL,journal.project_id,question['callId'], {'skipped':True})
    thread.join(3)
    assert answers == [{'answer':'','skipped':True}]
    with pytest.raises(ValueError): pi_runs.answer(EMAIL,journal.project_id,question['callId'], {'answer':'A'})

def test_question_form_validates_required_fields(run):
    journal, _ = run
    journal.create()
    call = journal.question('tool-2', {'title':'Form','question':'Complete', 'fields':[
        {'field':'choice','title':'Choice','type':'radio','options':['A','B'],'required':True}]})
    with pytest.raises(ValueError): pi_runs.answer(EMAIL,journal.project_id,call, {'values':{'choice':'C'}})
    result = pi_runs.answer(EMAIL,journal.project_id,call, {'values':{'choice':'A'}})
    assert result['values'] == {'choice':'A'}
