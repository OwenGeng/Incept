"""CTV reference routing and receipt-backed observation boundaries.

Search results establish discovery; subtitles establish speech, not pixels.
No current server tool attests viewing platform video frames. Reports must
remain partial until that capability exists or separately inspected evidence
is available. Never download competitors into the client's asset library.
"""

import re
from . import store
from .workspace_documents import document_lock


def answer_research_question(*, email: str, project_id: str, conversation_id: str,
                             question_id: str, choice: str, skipped: bool = False, notes: str = '') -> dict:
    store.get_project(email, project_id)
    if choice not in {'light', 'deep', 'off'} or (skipped and choice != 'off'):
        raise ValueError('请选择轻量调研、深度调研或暂不调研。')
    if not isinstance(notes, str) or len(notes) > 2000:
        raise ValueError('补充要求不能超过2000字符。')
    with document_lock(store._conversation_path(email, project_id, conversation_id)):
        conversation = store.get_conversation(email, project_id, conversation_id)
        question = conversation.research_question
        if not question or question.get('id') != question_id:
            raise ValueError('问题已失效，请重新打开当前会话。')
        if conversation.run_status == 'running':
            raise ValueError('会话仍在处理中，请稍后提交。')
        if question['status'] == 'consumed':
            raise ValueError('该回答已经启动过任务，请查看会话结果或重试任务。')
        if question['status'] == 'answered' and (question.get('choice') != choice or question.get('skipped') != skipped or question.get('notes', '') != notes):
            raise ValueError('该问题已经回答，不能修改已提交的选择。')
        if question['status'] == 'pending':
            conversation.research_decisions = (conversation.research_decisions + [
                {'id':question_id,'choice':choice,'skipped':skipped,'prompt':question['prompt'],'notes':notes}])[-30:]
        question.update(status='answered', choice=choice, skipped=skipped, notes=notes)
        store.save_conversation(email, project_id, conversation)
        return {'questionId': question_id, 'choice': choice, 'skipped': skipped, 'prompt': question['prompt']}


def reference_declined(prompt: str) -> bool:
    return bool(re.search(r'不用调研|无需调研|不要调研|不(?:用|要)(?:查|研究)竞品|只看官网|'
                          r'without research|skip (?:research|competitors)|no research|website only', prompt, re.I))


def reference_mode(prompt: str, *, approved_direction: bool = False) -> str:
    if reference_declined(prompt):
        return 'off'
    explicit = bool(re.search(r'竞品|案例|样本|参考|\b(?:competitors?|examples?|references?)\b', prompt, re.I))
    proposal = bool(re.search(r'方案|策略|创意|提案|\b(?:proposal|strategy|plan)\b', prompt, re.I))
    context = bool(re.search(r'https?://|ctv|客户|品牌|产品|商品|电商|\b(?:brand|product|client|ecommerce)\b', prompt, re.I))
    if not explicit and (approved_direction or not (proposal and context)):
        return 'off'
    return 'deep' if re.search(r'全面|完整审计|深度|20\s*[-–至]\s*30|full audit|comprehensive|deep research', prompt, re.I) else 'light'


def validate_reference_report(result: dict, receipts: list, *, mode: str, language: str) -> None:
    if mode == 'off':
        return
    english = language.lower().startswith('en')
    known: set[str] = set()
    transcripts: set[str] = set()
    for name, receipt in receipts:
        if not isinstance(receipt, dict) or receipt.get('error'):
            continue
        if name == 'web_search':
            known.update(source['url'] for source in receipt.get('sources', [])
                         if isinstance(source, dict) and isinstance(source.get('url'), str))
        elif name in {'web_fetch', 'video_transcript_fetch'} and isinstance(receipt.get('url'), str):
            known.add(receipt['url'])
            if name == 'video_transcript_fetch' and receipt.get('content'):
                transcripts.add(receipt['url'])
    report = result.get('references')
    if report is None:
        report = result['references'] = {'status': 'partial', 'samples': [
            {'url': url, 'format': 'unknown', 'observation_level': 'transcript' if url in transcripts else 'link'}
            for url in sorted(known)[:5]], 'limitations': [
            'Reference-video research is incomplete; no inspected sample set was delivered.' if english else
            '竞品／参考视频研究尚未完成，未交付已审看的样本集。']}
    if not isinstance(report, dict):
        report = result['references'] = {}
    samples = report.get('samples', [])
    limits = [item for item in report.get('limitations', []) if isinstance(item, str) and item.strip()] if isinstance(report.get('limitations', []), list) else []
    if not isinstance(samples, list):
        samples = []
    if len(samples) > (30 if mode == 'deep' else 5):
        limits.append('Reference sample budget reached; remaining candidates were omitted.' if english else '参考样本达到预算，超出项未纳入。')
    valid_samples = []
    urls: set[str] = set()
    formats: set[str] = set()
    for sample in samples:
        if not isinstance(sample, dict) or sample.get('url') not in known:
            if isinstance(sample, dict) and isinstance(sample.get('url'), str) and sample['url']:
                result['message'] = result['message'].replace(sample['url'], '[unverified reference removed]' if english else '【未核验参考链接已移除】')
            limits.append('A reference without successful tool evidence was excluded.' if english else '已排除没有成功检索证据的参考链接，不影响初步方案。')
            continue
        url = sample['url']
        if url in urls:
            continue
        urls.add(url)
        sample = dict(sample)
        level = sample.get('observation_level')
        if level not in {'link', 'transcript'} or (level == 'transcript' and url not in transcripts):
            sample['observation_level'] = 'transcript' if url in transcripts else 'link'
            sample['notes'] = 'Observation limited to tool receipts; visual claims removed.' if english else '仅有检索／字幕证据，未经审看的画面描述已移除。'
            limits.append('Video frames were not inspected.' if english else '参考视频画面尚未审看。')
        # Do not disguise unobserved frame-level fields as subtitle analysis.
        for field in ('hook', 'visual_proof', 'frames', 'visual_cta'):
            value = sample.get(field)
            if value and not re.search(r'未(?:观察|审看|核验)|不可得|unknown|unobserved|unverified|not inspected', str(value), re.I):
                sample.pop(field)
                limits.append('Unobserved frame-level descriptions were excluded.' if english else '已排除未经观察的画面级描述。')
        if isinstance(sample.get('format'), str) and sample['format'] not in {'unknown', '未知'}:
            formats.add(sample['format'])
        if len(valid_samples) < (30 if mode == 'deep' else 5):
            valid_samples.append(sample)
    report['samples'] = samples = valid_samples
    target = 20 if mode == 'deep' else 5
    if report.get('status') == 'complete':
        limits.append('Reference research remains partial; links/subtitles do not establish a complete visual audit.' if english else '参考研究仍为部分完成；链接／字幕不能证明完整视觉审看。')
    report['status'] = 'partial' if samples else 'blocked'
    if not limits:
        limits.append('Video frames were not inspected; links/subtitles are not a visual audit.' if english else
                      '尚未审看视频画面；链接／字幕不等于完整视觉分析。')
    report['limitations'] = limits = list(dict.fromkeys(limits))
    research = result.get('research')
    if isinstance(research, dict) and research.get('status') == 'complete':
        research['status'] = 'needs_input'
        research['verified_sources'] = research.get('sources', [])
        research.setdefault('questions', []).extend(item for item in limits if item not in research.get('questions', []))
    heading = 'Reference research (partial)' if english else '竞品／参考研究（未完成项）'
    lines = [f'\n\n{heading}：']
    for sample in samples:
        level = sample['observation_level']
        label = ('Subtitles only' if level == 'transcript' else 'Link discovered only') if english else (
            '仅读取字幕，未审看画面' if level == 'transcript' else '仅发现链接，未审看画面')
        lines.append(f"- {sample['url']} — {label}")
    lines.extend(f'- {limit}' for limit in limits)
    result['message'] += '\n'.join(lines)
