"""Persisted turn identity and cooperative cancellation for all Agent entry points."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Callable

from . import store
from .models import AgentConversation, AgentMessage
from .workspace_documents import document_lock


class AgentCancelled(ValueError):
    pass


class AgentBusy(ValueError):
    pass


def agent_error_message(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return '项目、会话或附件已不存在，请重新载入。'
    if isinstance(error, (ValueError, AgentBusy)):
        return str(error)[:1000]
    status = getattr(error, 'status_code', None) or getattr(error, 'code', None)
    if isinstance(status, int):
        return f'模型或工具服务返回 HTTP {status}，本轮未完成。请检查供应商配置、权限或配额；不会自动修改模型或区域。'
    return '模型或工具执行失败，本轮未完成。会话和附件已保留，可重试；请检查服务端运行记录。'


def prepare_turn(*, email: str, project_id: str, prompt: str, conversation_id: str | None,
                 asset_paths: list[str] | None = None, resend_from: str | None = None,
                 research_question_id: str | None = None) -> AgentConversation:
    store.get_project(email, project_id)  # Ownership and existence before persistence.
    existing_requested = conversation_id is not None
    conversation_id = conversation_id or uuid.uuid4().hex
    path = store._conversation_path(email, project_id, conversation_id)
    with document_lock(path):
        try:
            conversation = store.get_conversation(email, project_id, conversation_id)
        except FileNotFoundError:
            if existing_requested:
                raise
            conversation = AgentConversation(id=conversation_id, name=prompt.strip()[:60] or '素材分析')
        if conversation.run_status == 'running':
            raise AgentBusy('该会话仍在处理中，请先停止或等待完成再重试。')
        if research_question_id:
            question = conversation.research_question
            if resend_from or not question or question.get('id') != research_question_id or question.get('status') != 'answered':
                raise ValueError('调研确认已失效或已使用，请重新打开会话。')
            prompt = question['prompt']
        else:
            conversation.research_question = None
        if not prompt.strip() or len(prompt) > 20_000:
            raise ValueError('消息必须为 1–20000 字符')
        if len(asset_paths or []) > 20:
            raise ValueError('每条消息最多 20 个附件')
        attachments = []
        for asset_path in dict.fromkeys(asset_paths or []):
            asset = store.safe_asset_path(store.assets_root(email, project_id), asset_path)
            if not asset.is_file():
                raise FileNotFoundError(asset_path)
            attachments.append({'name': Path(asset_path).name, 'path': asset_path, 'mimeType': store.asset_mime_type(asset)})
        if resend_from:
            index = next((index for index, item in enumerate(conversation.messages) if item.id == resend_from and item.role == 'user'), None)
            if index is None:
                raise ValueError('原消息不存在，请重新载入会话后再编辑重发。')
            conversation.messages = conversation.messages[:index]
            # Evidence remains in project storage, but the abandoned branch is not conversation context.
            conversation.research_history = []
            conversation.research_decisions = []
        if len(conversation.messages) >= 999:
            raise ValueError('会话已达到消息上限，请新建会话。')
        conversation.messages.append(AgentMessage(id=uuid.uuid4().hex, role='user', content=prompt.strip(), attachments=attachments))
        conversation.run_id = uuid.uuid4().hex
        if research_question_id:
            conversation.research_question.update(status='consumed', resume_run_id=conversation.run_id)
        conversation.run_status = 'running'
        conversation.run_error = None
        return store.save_conversation(email, project_id, conversation)


class TurnControl:
    def __init__(self, email: str, project_id: str, conversation: AgentConversation,
                 cancel_event: Event | None = None, progress: Callable[[dict], None] | None = None):
        self.email, self.project_id = email, project_id
        self.conversation_id, self.run_id = conversation.id, conversation.run_id
        self.cancel_event = cancel_event or Event()
        self.progress = progress

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise AgentCancelled('已取消；已发送到模型的请求可能仍在运行，但不会继续工具调用或保存后续结果。')
        current = store.get_conversation(self.email, self.project_id, self.conversation_id)
        if current.run_id != self.run_id or current.run_status != 'running':
            raise AgentCancelled('该轮已取消或被替换，不再保存结果。')

    def report(self, content: str) -> None:
        self.check()
        if self.progress:
            self.progress({'type': 'progress', 'content': content})

    def save(self, conversation: AgentConversation) -> None:
        with document_lock(store._conversation_path(self.email, self.project_id, conversation.id)):
            self.check()
            store.save_conversation(self.email, self.project_id, conversation)

    @contextmanager
    def mutation(self):
        # Serialize a short commit against persisted cancellation/retry. Never
        # hold this lock across network/model calls.
        with document_lock(store._conversation_path(self.email, self.project_id, self.conversation_id)):
            self.check()
            yield

    def finish(self, status: str, error: str | None = None) -> None:
        path = store._conversation_path(self.email, self.project_id, self.conversation_id)
        with document_lock(path):
            try:
                current = store.get_conversation(self.email, self.project_id, self.conversation_id)
            except FileNotFoundError:
                return  # Never resurrect a deleted conversation.
            if current.run_id == self.run_id and current.run_status == 'running':
                current.run_status = status
                current.run_error = error
                store.save_conversation(self.email, self.project_id, current)


class ScopedTurnControl:
    """Child mutations honor both parent cancellation and the child's own run."""
    def __init__(self, parent: TurnControl, conversation_id: str):
        self.parent = parent
        self.email, self.project_id = parent.email, parent.project_id
        self.conversation_id, self.run_id = conversation_id, parent.run_id

    def check(self):
        self.parent.check()
        child = store.get_conversation(self.email, self.project_id, self.conversation_id)
        if child.parent_file != f'agent/{self.parent.conversation_id}.json' or child.run_id != self.run_id or child.run_status != 'running':
            raise AgentCancelled('Child Agent cancelled or ended')

    @contextmanager
    def mutation(self):
        with self.parent.mutation(), document_lock(store._conversation_path(self.email, self.project_id, self.conversation_id)):
            self.check()
            yield


def cancel_turn(email: str, project_id: str, conversation_id: str, run_id: str | None = None) -> None:
    with document_lock(store._conversation_path(email, project_id, conversation_id)):
        conversation = store.get_conversation(email, project_id, conversation_id)
        if run_id and conversation.run_id != run_id:
            return
        if conversation.run_status == 'running':
            conversation.run_status = 'cancelled'
            store.save_conversation(email, project_id, conversation)
            # Child SDK processes end with the parent. Persist that boundary
            # before terminating IPC, including their pending answer cards.
            from .pi_runs import RunJournal, cancel_questions
            for child in store.list_conversations(email, project_id):
                if child.parent_file != f'agent/{conversation_id}.json' or child.run_id != conversation.run_id:
                    continue
                with document_lock(store._conversation_path(email, project_id, child.id)):
                    current = store.get_conversation(email, project_id, child.id)
                    if current.run_id != conversation.run_id or current.run_status != 'running':
                        continue
                    current.run_status = 'cancelled'
                    store.save_conversation(email, project_id, current)
                cancel_questions(email, project_id, child.id, conversation.run_id)
                try:
                    journal = RunJournal(email, project_id, child.id, conversation.run_id)
                    journal.emit({'type': 'done'})
                    journal.finish('cancelled')
                except FileNotFoundError:
                    pass
            cancel_questions(email, project_id, conversation_id, conversation.run_id)
