# LinglongLab: chat, research and client assets

## User controls

- Ordinary conversation and preliminary CTV proposals do not open research consent cards or automatically search competitors.
- Competitor/video-reference research is an optional built-in skill. Select `ctv-reference-research` in the Agent skill menu, or explicitly request competitor/video-reference research in the current message. A client URL alone does not invoke it.
- Website asset collection is a separate function inside Canvas → Asset Library → Website asset collection. Enter the public website/product URL, discover candidates, preview and select assets, then import or attach the selected assets. Selection/import alone does not send a model request or add assets to the final video.
- The Agent retains discovery/import tools for explicit asset requests. Import requires an import request; merely discussing a website does not authorize downloading its media.

## Isolation and partial delivery

- Binary/text attachments are analyzed only when attached to the current user turn. Historical attachment records remain saved but are not automatically reread. Reattach an asset to request another inspection.
- Ordinary chat receives no saved research/tool evidence or production task state. Greetings bypass the production/research pipeline.
- Failed/unverified reference items are excluded, unavailable visual observations downgraded, and research coverage disclosed. Preliminary directions remain deliverable.
- Research findings without recorded supporting evidence are not accepted as verified facts. They are marked pending verification and the report becomes incomplete, preserving usable directions. Advertising claims, final production approvals and media inspection boundaries still apply.
- Legacy question/answer records and endpoints are retained for compatibility, but new requests do not create questions and the chat UI does not show legacy research cards.

No model identifiers, regions, production storage or deployment configuration are changed by this separation.
