"""Current-turn tool authority only; never infer production stage or model context."""
import re


def tool_permissions(prompt):
    clauses = re.split(r'[，,;；。!！?？\n]|但是|不过|而是|\b(?:but|instead)\b', prompt, flags=re.I)
    positive = [clause for clause in clauses if not re.search(
        r'不要|别|不(?:用|要|选|改|做|确认)|无需|禁止|不能|暂不|尚未|还没|未(?:确认|批准)|'
        r'\b(?:do not|don\x27t|not|never|without)\b', clause, re.I)]
    affirmative = ' '.join(positive)
    canvas = any(not re.search(r'解释|说明|如何|怎么|怎样|为什么|\b(?:explain|describe|how|why)\b', clause, re.I)
        and re.search(r'(?:搭建|创建|添加|删除|修改|更新|连接|断开|移动|移除).{0,80}(?:节点|画布|工作流)|'
            r'\b(?:build|create|add|remove|delete|update|connect|disconnect|move|change)\b.{0,80}\b(?:node|canvas|workflow)', clause, re.I)
        for clause in positive)
    fetching = r'(?:抓取?|拉取|下载|导入|采集|获取|fetch|download|import|collect|scrape)'
    assets = r'(?:素材|图片|视频|logo|icon|assets?|images?|videos?)'
    collection = bool(re.search(fetching + r'.{0,35}' + assets + '|' + assets + r'.{0,35}' + fetching, affirmative, re.I))
    capability = bool(re.search(r'能(?:否|不能|够)?|可以|可否|是否支持|解释|如何|怎么|怎样|can\s+(?:you|we|it)|is it possible|\b(?:explain|how)\b', affirmative, re.I))
    return {
        'canvas': bool(canvas),
        'destructive': bool(re.search(r'删除|移除|断开|\b(?:delete|remove|disconnect)\b', affirmative, re.I)),
        'research': bool(re.search(r'/skill:(?:ctv-reference-research|brand-product-intake)(?:\s|$)|调研|研究|\b(?:research|investigate)\b', affirmative, re.I)),
        'collection': collection and not capability,
        'public_fetch': bool(re.search(r'https?://|方案|创意|提案|分镜|脚本|\b(?:proposal|creative|storyboard|script)\b', prompt, re.I)),
        'workspace': bool(re.search(r'(?:创建|修改|保存|写入|更新).{0,40}(?:文档|文件)|\b(?:create|edit|save|write|update)\b.{0,40}\b(?:document|file)\b',affirmative,re.I)) and not capability,
        'media': bool(re.search(r'(?:生成|制作|导出|裁剪|提取|缩放).{0,40}(?:图片|视频|音频|成片|帧)|\b(?:generate|produce|export|trim|extract|resize)\b.{0,40}\b(?:image|video|audio|film|frame)\b',affirmative,re.I)) and not capability,
    }
