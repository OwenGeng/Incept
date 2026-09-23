# Linglong Lab — 7-minute talk track

> Audience: CEO / CTO
> Deck: `docs/presentation-assets/linglong-lab-three-slide-brief.pptx`
> Tone: conversational, first-person, a little informal. This is a talk, not a whitepaper — write it the way you'd actually say it out loud.
> Structure: follows the deck's 3 slides — Slide 1 (Problem), Slide 2 (Product / how it works), Slide 3 (Proof / real outputs).
> Pacing: ~7 minutes total. Opening ~30s, Slide 1 ~1.5 min, Slide 2 ~2 min, Slide 3 ~2.5 min, Close ~30s.
> Level of detail: leadership audience — lead with pain point, data, solution, impact. Keep any workflow/technical detail to one line of credibility, not a walkthrough.

## Opening — 30 seconds

Thanks for the time — I'll keep this to about seven minutes. Quick word on me first: I partnered with the CSE team on AdForge, our playable-ad platform — requirements, product design, building out the templates — mostly shaping the product around what sales actually needed in the field, and testing it with them. These days I'm spending most of my time building Linglong Lab.

Longer term, we want Linglong Lab to be Moloco's platform for frontier AI capability. Today I would like to show you the first thing we've actually built and shipped: Studio — our image and video production tool.

## Slide 1 — The problem — 1.5 minutes

Let's start with something unglamorous but very real: resizing. Every campaign needs the same creative in a dozen sizes and formats. Kakao alone has its own set of premium composite sizes. Today, that's manual work — a designer opens the source file, resizes it, checks it, exports it, one size at a time. A single approved concept can easily take several days to turn into a complete size set. It's a real chunk of our creative capacity going into file prep instead of creative making and insights.

Then there's the bigger version of the same problem: producing new creative — especially video — takes weeks: concept, shoot or render, edit, review. Because it's slow and expensive, in practice it mostly goes to our biggest accounts. Smaller advertisers with real growth potential almost can not gets that level of creative support.

And here's the part I would like to mention: the video models — Veo, Seedance, for instance — are already very capable. But hand one of them a rough idea and ask for a finished video, and what comes back is inconsistent part — characters that drift between shots, footage that doesn't cut together. Simple prompt-to-video doesn't get you to commercial quality, no matter how good the model is.

So it's not one problem, it's three: too much of our capacity goes into repetitive format work, creative support doesn't scale past our biggest accounts, and even when we throw a good model at it, the output doesn't hold together. That's the gap Linglong Lab is built to close.

## Slide 2 — What we built — 2 minutes

Studio's image tool compresses the resizing problem. Approved images in, every size we need out — including Kakao's composite formats — in about five minutes. Not five hours. Five minutes.

The studio is building to facilitate the video creation process and create more fancy videos which perform. We studied how frontier platforms like Runway and Higgsfield structure production, and built the same discipline into our own pipeline: a brief becomes a script, the script becomes a storyboard, and only then does it go to Veo, shot by shot, reviewable at every step. The result is that someone with no video production background — a GM, anyone on the team — can walk in with a rough idea and walk out with a video that actually looks and cuts like a real commercial. That workflow, not the model underneath it, is Linglong Lab's contribution here.

## Slide 3 — What it's already producing — 2.5 minutes

On the image side, this part is already live — a good number of our GMs use it directly in their day-to-day work today. A GM can produce Moloco-ready creative easily, without routing everything through the studio queue. That saves real time and real Creative Studio headcount. The impact for the client is just as direct: they no longer need to run their own creative team through weeks of production just to get something that fits our formats. We're adding that value ourselves, which means less work on their side — and clients that see us removing work from their plate are more willing to spend with us.

On the video side — what you're seeing here is a 15-to-30-second spot we generated for a simulation game, built shot by shot off a storyboard. To be clear on where this stands today: video is brand new, still in beta. We just develop it and will running it with a small set of users, iterating on their feedback before we widen access. And regardless of how good the pipeline gets, every piece of creative this produces still goes to the advertiser for review before it ever runs.

## Close — 30 seconds

This is the first wedge of what we want Linglong Lab to become: a place where frontier AI capability turns into something that actually add value to our customers. Image is live today with real GM adoption; video is the next step — it's in beta now, and it'll get better in the near future. Thank you.
