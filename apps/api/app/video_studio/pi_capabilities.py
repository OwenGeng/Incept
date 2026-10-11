"""Thinking options from the pinned SDK catalog or explicit deployment settings."""
import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from app.routers.video_runtime import configured_text_models


@lru_cache(maxsize=32)
def _catalog(provider,model):
    runtime=Path(os.getenv('INCEPT_PROJECT_ROOT') or Path(__file__).resolve().parents[4])/'apps/video-vue/apps/agentRuntime'
    node=shutil.which('node')
    if not node: return None
    script="import {getBuiltinModel} from '@earendil-works/pi-ai/providers/all'; const m=getBuiltinModel(process.argv[1],process.argv[2]); console.log(JSON.stringify(m?{reasoning:m.reasoning,thinkingLevelMap:m.thinkingLevelMap}:null));"
    try:
        result=subprocess.run([node,'--input-type=module','-e',script,provider,model],cwd=runtime,capture_output=True,text=True,timeout=10,check=True)
        return json.loads(result.stdout)
    except (OSError,subprocess.SubprocessError,ValueError): return None


def thinking_levels(provider,model):
    overrides=json.loads(os.getenv('VIDEO_AGENT_THINKING_LEVELS','{}'))
    values=overrides.get(f'{provider}:{model}')
    if values is not None:
        if not isinstance(values,list) or not values or any(v not in {'off','low','medium','high'} for v in values):
            raise ValueError('Invalid deployment thinking levels')
        return list(dict.fromkeys(['off',*values]))
    # Exact documented model, never a guessed family/alias capability.
    # https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash
    if provider=='google-vertex-ai' and model=='gemini-3.8-flash':
        return ['off','low','medium','high']  # off retains provider default, not MINIMAL.
    entry=_catalog(provider,model)
    if not entry or not entry.get('reasoning'): return ['off']
    mapping=entry.get('thinkingLevelMap') or {}
    return [level for level in ('off','low','medium','high') if mapping.get(level,level) is not None]


def validate_thinking(model,level):
    level=level or 'off'
    if level not in thinking_levels(model['providerId'],model['modelId']):
        raise ValueError('This thinking level is not confirmed for the configured model')
    return level


def capabilities():
    return {'models':[{**m,'thinkingLevels':thinking_levels(m['providerId'],m['modelId'])} for m in configured_text_models()],
        'budgets':{'modelCalls':40,'children':4,'seconds':1800,
            'contextTokens':int(os.getenv('VIDEO_AGENT_CONTEXT_BUDGET','65536')),
            'outputTokens':int(os.getenv('VIDEO_AGENT_OUTPUT_BUDGET','16384'))},'cost':None}
