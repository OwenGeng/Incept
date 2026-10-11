"""Deterministic user intent, durable choices and final-answer safeguards.

Only user turns establish production decisions. Model output and files cannot
approve their own brief or silently replace a previously selected product.
"""

import math
import re
from urllib.parse import urlsplit


_URL = re.compile(r"https?://[^\s<>\]\[()（），。；、\"']+", re.I)
_ASSET = r"(?:素材|图片|视频|logo|icon|assets?|images?|videos?)"
_FETCH = r"(?:抓取?|拉取|下载|导入|采集|获取|fetch|download|import|collect|scrape)"
_SENSITIVE = re.compile(r"无毒|零排放|无甲醛|零甲醛|零气味|无异味|不含有毒|zero\s*(?:odor|emissions?|formaldehyde)|non[- ]?toxic|toxin[- ]?free", re.I)
_UNCERTAIN = re.compile(r"待(?:核验|确认|验证|客户|检测)|未(?:核验|核实|确认|验证|证实)|不能确认|无法确认|(?:不能|不得|不应|禁止|不要)宣称|避免使用|不纳入投放|需(?:要)?(?:核验|确认|检测|证明|客户)|不作为已证实|unverified|not verified|needs? verification|not established|do not claim|must not claim|avoid claiming", re.I)
_ATTRIBUTED = re.compile(r"官网(?:宣称|称|声明|标注|描述)|网站(?:宣称|称|声明|标注)|(?:品牌|客户)(?:宣称|声明)|according to.{0,60}(?:website|brand)|(?:website|brand)\s+claims?", re.I)
_TIMELINE = re.compile(r"(?<![\d:.])(\d+(?::[0-5]\d)?(?:\.\d+)?)\s*(?:秒|s)?\s*[-–—~至]\s*(\d+(?::[0-5]\d)?(?:\.\d+)?)\s*(?:秒|s)?", re.I)


def production_continuation(prompt: str, state: dict) -> bool:
    """A short reply can refer to a pending draft, but never grants tool rights."""
    return bool(state.get('production_draft') and re.search(
        r'确认|开始制作|继续制作|继续|刚才|这个方案|该方案|批准的方案|\b(?:confirm(?:ed)?|approved|continue|proceed|start production)\b', prompt, re.I))


def _accept_pending_draft(text: str) -> bool:
    # Exact positive intent, not a substring of a question or a refusal.
    return bool(re.fullmatch(
        r'(?:(?:好的|好|可以|yes|okay|ok)[，,\s]*)?(?:我们|let[’\x27]s\s+)?'
        r'(?:确认|可以开始制作|开始制作吧?|确认并开始制作|confirm(?:ed)?|approved|proceed|start production)'
        r'(?:[，,\s]+let[’\x27]s\s+(?:proceed|start production))?[!！。.\s]*', text.strip(), re.I))


def qualify_preliminary_claims(result: dict, task: str, language: str) -> None:
    """Keep preliminary work useful without promoting safety claims into ad copy.

    Never relax final storyboard/canvas delivery checks. Brand web evidence is
    not an independent toxicology or emissions certification.
    """
    if task not in {'proposal', 'research', 'chat'}:
        return
    english = language.lower().startswith('en')
    prefix = ('[Unverified claim about this product — requires client test evidence before advertising] ' if english else
              '【待核验声明，需要客户提供检测证明，确认前不得用于投放】')
    changed = False
    def qualify(match):
        nonlocal changed
        sentence = match.group()
        if _SENSITIVE.search(sentence) and not _UNCERTAIN.search(sentence):
            changed = True
            return prefix + sentence
        return sentence
    result['message'] = re.sub(r'[^。！？!?\n]+[。！？!?]?', qualify, str(result.get('message') or ''))
    if changed and isinstance(result.get('research'), dict):
        research = result['research']
        research['status'] = 'needs_input'
        question = ('Please provide client test evidence before using safety or emissions claims in advertising.' if english else
                    '请客户提供检测证明后，再确认安全、排放等声明是否可用于投放文案。')
        questions = research.get('questions')
        research['questions'] = list(dict.fromkeys([*(questions if isinstance(questions, list) else []), question]))


def _affirmative_clauses(text: str) -> list[str]:
    """Conservative intent boundary: rejected options/questions are not choices."""
    clauses = re.split(r'[，,;；。!！?？\n]|但是|不过|而是|\b(?:but|instead)\b', text, flags=re.I)
    return [clause for clause in clauses if not re.search(
        r'不要|别|不(?:用|要|选|改|做|确认)|无需|禁止|不能|暂不|尚未|还没|未(?:确认|批准)|'
        r'\b(?:do not|don\x27t|not|never|without)\b', clause, re.I)]


def canvas_edit_requested(prompt: str) -> bool:
    for clause in _affirmative_clauses(prompt):
        if re.search(r'解释|说明|如何|怎么|怎样|为什么|\b(?:explain|describe|how|why)\b', clause, re.I):
            continue
        if re.search(r'(?:搭建|创建|添加|删除|修改|更新|连接|断开|移动|移除).{0,80}(?:节点|画布|工作流)|'
                     r'\b(?:build|create|add|remove|delete|update|connect|disconnect|move|change)\b.{0,80}\b(?:node|canvas|workflow)', clause, re.I):
            return True
    return False


def classify_task(prompt: str) -> str:
    """Route the latest question before considering historical production work."""
    text = prompt.strip()
    asset_text = '，'.join(_affirmative_clauses(text))
    asset_request = bool(re.search(_FETCH + r".{0,35}" + _ASSET, asset_text, re.I))
    asset_context = asset_request or bool(re.search(_ASSET + r".{0,35}" + _FETCH, asset_text, re.I))
    capability_question = bool(re.search(r"能(?:否|不能|够)?|可以|可否|是否支持|解释|如何|怎么|怎样|can\s+(?:you|we|it)|is it possible|\b(?:explain|how)\b", asset_text, re.I))
    if asset_context and capability_question:
        return "asset_capability"
    if asset_context:
        return "asset_import"
    if re.search(r"分镜|脚本|storyboard|(?:write|create|generate).{0,20}script", text, re.I):
        return "storyboard"
    if canvas_edit_requested(text):
        return "canvas_edit"
    proposal = bool(re.search(r"方案|创意|提案|proposal|creative\s*(?:plan|direction)", text, re.I))
    if re.search(r"调研|研究|research|investigate", text, re.I) or (_URL.search(text) and proposal):
        return "research"
    if proposal:
        return "proposal"
    return "chat"


def _field(message, name):
    return message.get(name, "") if isinstance(message, dict) else getattr(message, name, "")


def ordinary_chat_messages(messages):
    """Retain casual conversation, excluding previous production/tool scopes.

    The attachment reader remains latest-turn-only. This is text memory, not
    permission to replay old media or turn research receipts into evidence.
    """
    retained = []
    casual_turn = False
    for message in messages:
        if _field(message, 'role') == 'user':
            text = str(_field(message, 'content'))
            casual_turn = (classify_task(text) == 'chat' and not _URL.search(text)
                           and not _SENSITIVE.search(text) and not _field(message, 'attachments')
                           and not re.search(r'确认|制作|方案|分镜|批准|continue|confirm|proceed|production', text, re.I))
        if casual_turn:
            retained.append(message)
    if messages and (not retained or retained[-1] is not messages[-1]):
        retained.append(messages[-1])
    return retained


def task_state_from_messages(messages) -> dict:
    """Replay all user choices, so a long assistant history cannot erase them."""
    state = {"duration_seconds": None, "product_url": None, "website": None,
             "approved_direction": None, "brief_approved": False, "confirmed_constraints": []}
    constraints = []
    for message in messages:
        if _field(message, "role") == "assistant":
            text = str(_field(message, 'content'))
            draft = _field(message, 'production_draft')
            # Legacy conversations have no draft metadata. Only an actual plan
            # offered for confirmation is eligible, never a generic greeting.
            if draft or (re.search(r'方案|脚本|分镜|\b(?:plan|storyboard|script)\b', text, re.I)
                         and re.search(r'请确认|确认后|请告诉我|please confirm', text, re.I)):
                prior = state.get('production_draft')
                if not prior or prior['content'] != text[:8_000] or prior.get('storyboard') != (draft or None):
                    state['production_draft'] = {'message_id': _field(message, 'id'),
                        'content': text[:8_000], 'storyboard': draft or None}
                    state['brief_approved'] = False
            continue
        if _field(message, "role") != "user":
            continue
        text = str(_field(message, "content"))
        previous = (state["duration_seconds"], state["product_url"], state["approved_direction"])
        choice_text = '，'.join(clause for clause in _affirmative_clauses(text)
            if not re.search(r'为什么|为何|是否|能否|吗|\b(?:why|whether|how)\b', clause, re.I))
        urls = _URL.findall(choice_text)
        # A platform specification/reference is not a customer replacement.
        reference_only = bool(re.search(r"参考|规格|指南|文档|要求|documentation|specification|guide", text, re.I)
                              and not re.search(r"客户|品牌|商品|新产品|/products/", text, re.I))
        customer_urls = [] if reference_only else urls
        if customer_urls:
            website = customer_urls[-1].rstrip(".,;:!?？")
            old_host = urlsplit(state["website"] or "").hostname
            new_host = urlsplit(website).hostname
            if old_host and new_host and old_host.removeprefix("www.") != new_host.removeprefix("www."):
                state["product_url"] = None
                state["approved_direction"] = None
                state["brief_approved"] = False
                state.pop('production_draft', None)
                constraints.clear()
            state["website"] = website
            products = [url.rstrip(".,;:!?？") for url in customer_urls if "/products/" in urlsplit(url).path
                        and urlsplit(url).hostname == new_host]
            if products:
                state["product_url"] = products[-1]
        # A range/list of recommendations is not a single user duration choice.
        durations = re.findall(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(?:秒|seconds?|secs?|s\b)", choice_text, re.I)
        choices = list(re.finditer(r"(?:改成|改为|选择|就做|制作|做|时长(?:为|是)?|duration\s*(?:is|=|:)?|make(?: it)?)\s*(\d{1,3}(?:\.\d+)?)\s*(?:秒|seconds?|secs?|s\b)", choice_text, re.I))
        chosen = choices[-1] if choices else None
        if chosen or len(durations) == 1:
            duration = float(chosen.group(1) if chosen else durations[0])
            if 6 <= duration <= 180:
                state["duration_seconds"] = int(duration) if duration.is_integer() else duration
        directions = list(re.finditer(r"(?:选(?:择)?|确认|采用|就用)\s*方向\s*(\d+)|方向\s*(\d+)\s*(?:没问题|可以|确认|批准|就这个|很好)", choice_text))
        direction = directions[-1] if directions else None
        if direction:
            state["approved_direction"] = int(direction.group(1) or direction.group(2))
        if previous != (state["duration_seconds"], state["product_url"], state["approved_direction"]):
            state["brief_approved"] = False
            state.pop('production_draft', None)
        negative = re.search(r"(?:没|未|不|尚未|还没).{0,6}(?:批准|确认)|(?:取消|撤回).{0,8}(?:批准|确认)", text)
        approval = re.search(r"(?:批准|确认).{0,12}(?:brief|方案|脚本|简报)|(?:brief|方案|脚本|简报).{0,12}(?:批准|确认)", text, re.I)
        if negative:
            state["brief_approved"] = False
        elif (approval or (state.get('production_draft') and _accept_pending_draft(text))) and not re.search(r"[?？]|(?:吗|是否|有没有|了吗)", text):
            state["brief_approved"] = True
        if urls or durations or direction or approval or re.search(r"要求|必须|不要|保留|产品|客户|SKU|constraint", text, re.I):
            constraints.append(text[:20_000])
    # Keep complete latest statements rather than arbitrary assistant summaries.
    retained, remaining = [], 20_000
    for text in reversed(constraints):
        if len(text) <= remaining:
            retained.append(text)
            remaining -= len(text)
        elif not retained:
            retained.append(text[-remaining:])
            break
    state["confirmed_constraints"] = list(reversed(retained))
    return state


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def _timecode_seconds(value):
    if ":" in value:
        minutes, seconds = value.split(":", 1)
        return float(minutes) * 60 + float(seconds)
    return float(value)


def validate_delivery(result: dict, task: str, state: dict, evidence) -> list[str]:
    """Return retryable violations; never invent missing facts or approval."""
    errors = []
    message = str(result.get("message", "")).strip()
    actionable = task in {"research", "proposal", "asset_import", "storyboard", "canvas_edit"}
    if actionable and state.get('production_draft'):
        for sentence in re.split(r'[。！？!?\n]', message):
            if not re.search(r'请.{0,16}(?:告诉|提供)|(?:what|please.{0,16}(?:provide|tell)).{0,40}', sentence, re.I):
                continue
            if ((state.get('website') or state.get('product_url')) and re.search(r'品牌(?!授权|素材|规范|标识|检测)|产品官网|商品链接|brand(?!\s+(?:rights|authorization|assets|guidelines|permission))|product.{0,16}(?:url|link|name)', sentence, re.I)) or (
                    state.get('duration_seconds') and re.search(r'时长|duration|how long', sentence, re.I)):
                errors.append('已知品牌、商品链接和时长必须从当前方案续接，不能重复询问；只询问具体尚缺的信息。')
                break
    if actionable and (not message or message.lower().strip(".!。！") in {"done", "complete", "completed", "完成", "已完成"}
                       or re.match(r"(?:您好|你好|hello|hi)[!！,.，\s]*我是.{0,80}(?:助手|assistant)", message, re.I)):
        errors.append("必须直接交付当前任务的结果或具体限制，不能只返回Done或自我介绍。")

    blocked = result.get("status") in {"blocked", "needs_input"} or (
        isinstance(result.get("research"), dict) and result["research"].get("status") in {"blocked", "needs_input"})
    if blocked and actionable:
        limitation = re.search(r"无法|失败|缺少|需要|请(?:确认|提供)|未(?:提供|找到|确认)|不支持|不可用|受限|返回\s*[45]\d\d|blocked|cannot|unavailable|missing|failed|\b(?:provide|confirm|need|requires?)\b|denied", message, re.I)
        specific = re.search(r"网页|网站|素材|图片|视频|客户|产品|授权|脚本|时长|URL|文件|工具|配置|网络|模型|权限|检测|账户|预算|目标|语言|地区|SKU|brief|source|asset|image|video|website|file|tool|permission|model|product|client|test evidence|https?://|\b[45]\d\d\b", message, re.I)
        if len(message) < 10 or not limitation or not specific:
            errors.append("blocked/needs_input必须说明具体缺失信息、工具限制或需要用户回答的问题。")
    board = result.get("storyboard")
    if task == "storyboard" and not blocked and not board:
        errors.append("分镜/脚本请求必须返回storyboard结构，含每个镜头的duration_seconds。")
    if board:
        shots = board.get("shots") if isinstance(board, dict) else board
        if not isinstance(shots, list) or not shots:
            errors.append("storyboard.shots必须为非空镜头数组。")
        else:
            durations = [_number(shot.get("duration_seconds", shot.get("duration"))) if isinstance(shot, dict) else None for shot in shots]
            if any(value is None for value in durations):
                errors.append("每个分镜镜头必须有有效的正数duration_seconds。")
            else:
                total = sum(durations)
                expected = _number(state.get("duration_seconds"))
                declared = _number(board.get("duration_seconds")) if isinstance(board, dict) else None
                if expected and abs(total - expected) > 0.1:
                    errors.append(f"镜头时长合计{total:g}秒，不等于用户确认的{expected:g}秒。")
                if declared and abs(total - declared) > 0.1:
                    errors.append(f"镜头时长合计{total:g}秒，不等于分镜声明的{declared:g}秒。")
                if expected and declared and abs(expected - declared) > 0.1:
                    errors.append("分镜声明时长与用户确认时长不一致。")

    if task == "storyboard" and not blocked:
        intervals = [(_timecode_seconds(match[1]), _timecode_seconds(match[2]))
                     for match in _TIMELINE.finditer(message)
                     if ':' in match[0] or (float(match[1]) < 180 and float(match[2]) <= 180
                         and not re.match(r'\s*(?:fps|帧|hz|px)', message[match.end():], re.I))]
        # A standalone specification range such as 6–180 seconds is not a
        # storyboard timeline. Actual timelines begin at zero or have stages.
        if intervals and (intervals[0][0] == 0 or len(intervals) > 1):
            cursor = 0.0
            for start, end in intervals:
                if end <= start or abs(start - cursor) > 0.1:
                    errors.append("用户可见分镜时间轴存在空缺、重叠或非正时长，请从0秒连续编排。")
                    break
                cursor = end
            expected_total = _number(state.get("duration_seconds"))
            if not expected_total and isinstance(board, dict):
                expected_total = _number(board.get("duration_seconds"))
            if expected_total and abs(intervals[-1][1] - expected_total) > 0.1:
                errors.append(f"用户可见分镜时间轴结束于{intervals[-1][1]:g}秒，应为{expected_total:g}秒。")

    expected = _number(state.get("duration_seconds"))
    if expected and task not in {"asset_capability", "chat"}:
        production_duration = re.findall(r"(?:制作|做(?:成)?|交付|改(?:成|为)|规划|搭建|这是|本(?:次|方案|片)|时长(?:为|是)?|make(?: it)?|deliver)\s*(?:一个|一支|这个|为|是|a\s*)?(\d{1,3}(?:\.\d+)?)\s*(?:秒|seconds?|secs?)(?!\s*(?:的)?(?:开场|收尾|片头|片尾|镜头|分镜|shot|opening|closing))", message, re.I)
        if any(abs(float(value) - expected) > 0.1 for value in production_duration):
            errors.append(f"回答改变了用户已确认的{expected:g}秒时长，请保留用户选择。")

    items = evidence.get("evidence", []) if isinstance(evidence, dict) else evidence or []
    supported = [str(item.get("claim", "")) for item in items if isinstance(item, dict)
                 and item.get("source_url") and item.get("status", "supported") == "supported"
                 and item.get("confidence_status", "supported") == "supported"]
    for sentence in re.split(r"[。！？!?\n]", message):
        if _SENSITIVE.search(sentence) and not _UNCERTAIN.search(sentence):
            # The exact recorded claim must be present, not merely a matching
            # keyword in an unrelated source or another product's evidence.
            matching_claims = [claim for claim in supported if claim.strip() and (
                sentence.strip().rstrip(".") in claim.rstrip("。.!！") or claim.rstrip("。.!！") in sentence.strip())]
            sensitive_phrases = _SENSITIVE.findall(sentence)
            if any(not any(phrase.lower() in claim.lower() for claim in matching_claims)
                   for phrase in sensitive_phrases):
                errors.append("无毒、零排放、无甲醛等敏感产品声明需要对应的已记录证据，或明确标注待核验。")
                break
            if not _ATTRIBUTED.search(sentence):
                errors.append("官网记录仅证明品牌的宣称；敏感产品声明必须标注官网宣称，不能写成独立检测结论。")
                break
    return errors
