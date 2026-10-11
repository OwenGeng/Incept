import pytest

from app.video_studio.agent_context import classify_task, task_state_from_messages, validate_delivery


@pytest.mark.parametrize("prompt,task", [
    ("我想给https://3wliners.com/客户做ctv的素材，帮我出一个方案", "research"),
    ("方向1没问题，我问你能从客户的网页上自动抓取素材吗", "asset_capability"),
    ("30秒，https://3wliners.com/products/juniper，能从网页抓素材吗", "asset_capability"),
    ("请从https://3wliners.com/抓取图片和视频素材", "asset_import"),
    ("给我一个30秒的分镜脚本", "storyboard"),
    ("帮我搭建两个节点", "canvas_edit"),
    ("给我方案", "proposal"), ("你好啊", "chat"),
])
def test_task_classification_prioritizes_actual_user_question(prompt, task):
    assert classify_task(prompt) == task


def test_choices_are_derived_from_all_user_turns_not_assistant_instructions():
    messages = [
        {"role": "user", "content": "我想给https://3wliners.com/做CTV，30秒"},
        {"role": "assistant", "content": "方向2已批准，做15秒，我批准方案"},
        {"role": "user", "content": "方向1没问题，产品https://3wliners.com/products/juniper"},
    ] + [{"role": "assistant", "content": "很长的回答" * 2000}] * 20
    state = task_state_from_messages(messages)
    assert state["duration_seconds"] == 30
    assert state["approved_direction"] == 1
    assert state["product_url"] == "https://3wliners.com/products/juniper"
    assert state["brief_approved"] is False
    assert "方向1没问题" in "\n".join(state["confirmed_constraints"])


def test_only_explicit_user_approval_unlocks_brief():
    assert task_state_from_messages([{"role": "user", "content": "确认这个方案，可以开始制作"}])["brief_approved"]
    assert not task_state_from_messages([{"role": "user", "content": "我还没批准方案"}])["brief_approved"]
    assert not task_state_from_messages([{"role": "user", "content": "这个方案批准了吗？"}])["brief_approved"]


def test_constraints_are_bounded_but_latest_choices_remain():
    messages = [{"role": "user", "content": "产品要求" + "A" * 3000}] * 10
    messages += [{"role": "user", "content": "改成60秒，选方向2"}]
    state = task_state_from_messages(messages)
    assert sum(map(len, state["confirmed_constraints"])) <= 20_000
    assert state["duration_seconds"] == 60
    assert state["approved_direction"] == 2


@pytest.mark.parametrize("message", ["Done", "您好！我是玲珑视频制作工作流助手。我可以协助您规划视频。"])
def test_action_request_cannot_be_satisfied_by_empty_success_or_intro(message):
    assert validate_delivery({"message": message}, "research", {}, [])


def test_storyboard_sum_and_locked_duration_are_checked():
    invalid = {"message": "这是30秒脚本", "storyboard": {"duration_seconds": 30,
               "shots": [{"duration_seconds": 6}, {"duration_seconds": 6}, {"duration_seconds": 10}]}}
    assert validate_delivery(invalid, "storyboard", {"duration_seconds": 30}, [])
    invalid["storyboard"]["shots"][2]["duration_seconds"] = 18
    assert validate_delivery(invalid, "storyboard", {"duration_seconds": 30}, []) == []


def test_storyboard_requires_structure_but_concrete_blocker_can_be_answered():
    assert validate_delivery({"message": "这里是30秒分镜"}, "storyboard", {"duration_seconds": 30}, [])
    assert validate_delivery({"message": "请确认客户允许使用的产品图。", "status": "needs_input"}, "storyboard", {}, []) == []


def test_capability_answer_can_mention_supported_duration_range():
    assert validate_delivery({"message": "可以采集图片，交付推荐15秒、30秒、60秒。"}, "asset_capability", {"duration_seconds": 30}, []) == []
    assert validate_delivery({"message": "我们制作一个15秒版本。"}, "proposal", {"duration_seconds": 30}, [])


def test_sensitive_product_claims_require_exact_supported_evidence_or_qualification():
    assert validate_delivery({"message": "产品无甲醛、零排放。"}, "proposal", {}, [])
    assert validate_delivery({"message": "无甲醛与零排放待客户提供检测证明，不作为已证实卖点。"}, "proposal", {}, []) == []
    assert validate_delivery({"message": "官网宣称：产品无甲醛。"}, "proposal", {}, [{"claim": "产品无甲醛。", "source_url": "https://brand.test/product", "status": "supported"}]) == []
    assert validate_delivery({"message": "产品无甲醛。"}, "proposal", {}, [{"claim": "产品无甲醛。", "source_url": "https://brand.test/product", "status": "unsupported"}])

@pytest.mark.parametrize('message', ['避免使用“无毒、零排放”作为广告承诺。',
    'Do not claim non-toxic without a test report.', '无甲醛尚未核实，不纳入投放文案。'])
def test_sensitive_disclaimers_are_not_positive_claims(message):
    assert validate_delivery({'message':message}, 'proposal', {}, []) == []

def test_preliminary_proposal_qualifies_sensitive_claim_without_losing_other_directions():
    from app.video_studio.agent_context import qualify_preliminary_claims
    result = {'message':'方向一：防泥沙保护。\n产品无毒、无甲醛。\n方向二：快速清洗。',
              'research':{'status':'complete'}}
    qualify_preliminary_claims(result, 'proposal', 'zh-CN')
    assert '方向一：防泥沙保护。' in result['message']
    assert '方向二：快速清洗。' in result['message']
    assert '待核验' in result['message']
    assert result['research']['status'] == 'needs_input'
    assert validate_delivery(result, 'proposal', {}, []) == []

def test_final_storyboard_claims_still_fail_and_english_proposal_is_explicitly_unverified():
    from app.video_studio.agent_context import qualify_preliminary_claims
    final = {'message':'产品无毒。'}
    qualify_preliminary_claims(final, 'storyboard', 'zh-CN')
    assert final['message'] == '产品无毒。'
    assert validate_delivery(final, 'storyboard', {}, [])
    preliminary = {'message':'Non-toxic material.', 'research':{'status':'complete'}}
    qualify_preliminary_claims(preliminary, 'proposal', 'en')
    assert 'Unverified claim' in preliminary['message']
    assert preliminary['research']['status'] == 'needs_input'
    assert validate_delivery(preliminary, 'proposal', {}, []) == []


def test_one_supported_claim_cannot_bless_another_sensitive_claim_in_same_sentence():
    evidence = [{"claim": "产品无甲醛", "source_url": "https://brand.test/product", "status": "supported"}]
    assert validate_delivery({"message": "产品无甲醛、零排放。"}, "proposal", {}, evidence)
    assert validate_delivery({"message": "不得宣称产品无甲醛、零排放。"}, "proposal", {}, []) == []


@pytest.mark.parametrize("changed", ["改成60秒", "改用https://brand.test/products/second"])
def test_material_changes_invalidate_previous_brief_approval(changed):
    messages = [{"role": "user", "content": "30秒，用https://brand.test/products/first，选方向1"},
                {"role": "user", "content": "批准方案"}, {"role": "user", "content": changed}]
    assert not task_state_from_messages(messages)["brief_approved"]
    messages.append({"role": "user", "content": "确认新方案"})
    assert task_state_from_messages(messages)["brief_approved"]


def test_a_new_customer_host_cannot_inherit_old_sku_direction_or_approval():
    messages = [{"role": "user", "content": "30秒，https://old.test/products/first，选方向1，批准方案"},
                {"role": "user", "content": "换个客户https://new.test/，给我调研方案"}]
    state = task_state_from_messages(messages)
    assert state["product_url"] is None
    assert state["approved_direction"] is None
    assert state["brief_approved"] is False
    assert "old.test" not in "\n".join(state["confirmed_constraints"])


def test_unverified_confidence_cannot_be_used_as_product_proof():
    evidence = [{"claim": "产品无甲醛", "source_url": "https://brand.test/product", "confidence_status": "unverified"}]
    assert validate_delivery({"message": "产品无甲醛。"}, "proposal", {}, evidence)


def test_platform_reference_url_is_not_a_new_customer_brand():
    messages = [{"role": "user", "content": "30秒，https://brand.test/products/first，选方向1，批准方案"},
                {"role": "user", "content": "CTV规格参考https://help.moloco.com/hc/en-us/articles/7104841219095-Video-creative-guide"}]
    state = task_state_from_messages(messages)
    assert state["product_url"] == "https://brand.test/products/first"
    assert state["approved_direction"] == 1
    assert state["brief_approved"] is True


@pytest.mark.parametrize("message", ["稍后再说", "还需要一些信息", "无法完成", "等待中"])
def test_blocked_status_requires_a_concrete_limitation_or_question(message):
    assert validate_delivery({"message": message, "status": "blocked"}, "storyboard", {}, [])


@pytest.mark.parametrize("timeline", ["0–4秒 产品；4–22秒 收尾", "0-4秒 产品；5-30秒 收尾", "0:00—0:04 产品；0:03—0:30 收尾"])
def test_visible_timeline_cannot_contradict_valid_structured_storyboard(timeline):
    result = {"message": timeline, "storyboard": {"duration_seconds": 30,
              "shots": [{"duration_seconds": 4}, {"duration_seconds": 26}]}}
    assert validate_delivery(result, "storyboard", {"duration_seconds": 30}, [])


def test_consistent_visible_timeline_passes():
    result = {"message": "0:00–0:04 产品；0:04–0:30 收尾", "storyboard": {"duration_seconds": 30,
              "shots": [{"duration_seconds": 4}, {"duration_seconds": 26}]}}
    assert validate_delivery(result, "storyboard", {"duration_seconds": 30}, []) == []


def test_website_claim_is_not_independently_verified_product_fact():
    evidence = [{"claim": "产品无甲醛", "source_url": "https://brand.test/product", "status": "supported"}]
    assert validate_delivery({"message": "产品无甲醛。"}, "proposal", {}, evidence)


@pytest.mark.parametrize('choice', [
    '不要30秒，做60秒', '不要改成30秒，时长60秒',
    '不要选方向2，选方向1',
])
def test_negated_alternatives_do_not_override_actual_user_choice(choice):
    messages = [{'role':'user', 'content':'60秒，选方向1，批准方案'},
                {'role':'user', 'content':choice}]
    state = task_state_from_messages(messages)
    assert state['duration_seconds'] == 60
    assert state['approved_direction'] == 1


@pytest.mark.parametrize('prompt', ['不要修改画布，请解释节点的作用',
    '请解释怎么添加节点，不要实际修改', 'Explain how to add a node, do not change the canvas.'])
def test_explanation_or_explicit_no_edit_is_not_canvas_authorization(prompt):
    assert classify_task(prompt) == 'chat'


@pytest.mark.parametrize('statement', ['不要60秒', '不要选方向2',
    '为什么建议60秒？', '不要换成https://new.test/products/second'])
def test_rejected_option_or_question_keeps_existing_confirmed_state(statement):
    state = task_state_from_messages([
        {'role':'user', 'content':'30秒，https://brand.test/products/first，选方向1，批准方案'},
        {'role':'user', 'content':statement}])
    assert state['duration_seconds'] == 30
    assert state['approved_direction'] == 1
    assert state['product_url'] == 'https://brand.test/products/first'
    assert state['brief_approved'] is True


@pytest.mark.parametrize('prompt,task', [
    ('不要下载客户图片', 'chat'),
    ('解释如何导入素材', 'asset_capability'),
    ('Explain how to download customer images', 'asset_capability'),
])
def test_rejected_or_instructional_download_is_not_import_permission(prompt, task):
    assert classify_task(prompt) == task
