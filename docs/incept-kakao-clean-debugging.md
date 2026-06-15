# Kakao Clean Debugging Notes

## Symptom

Kakao clean job fails with an error like:

```text
RuntimeError: Gemini returned no image data. Model text response: I'm just a language model and can't help with that.
```

This means the backend expected image bytes from Gemini, but Gemini returned a text refusal instead.

## Root Cause From This Incident

The failure was caused by Gemini's built-in safety/compliance refusal, not by Python image parsing.

In this incident, the prompt and input combination made the request more likely to be blocked:

- The uploaded image was a well-known commercial game ad creative with visible logos and branded IP.
- The prompt was too specific and too forceful.
- The prompt hard-coded brand/content details from a particular image instead of staying generic.

Examples of problematic prompt patterns:

- Naming specific branded text to erase, such as `AGE OF EMPIRES`
- Describing exact character appearance or pose in detail
- Using overly rigid command wording like `CRITICAL`, `TOTAL REMOVAL`, `ABSOLUTE FIDELITY`

When Gemini refuses, the backend may see only a plain text response instead of any generated image.

## Practical Interpretation

If Kakao clean returns:

```text
I'm just a language model and can't help with that.
```

assume the first debugging hypothesis is:

`Gemini safety/compliance refusal on the image-edit request`

Do not start by guessing that:

- the PNG decoding is broken
- the response parser is broken
- the job queue is broken

Those may still be worth checking later, but refusal should be ruled in or out first.

## What Worked Better

A very short, generic prompt worked:

```text
Please remove the text and UI elements from this image and fill the background naturally.
```

This reduced refusal risk compared with long, hard-coded, highly directive prompts.

## Recommended Prompt Rules For Kakao Clean

- Keep the prompt short.
- Keep the prompt generic.
- Do not mention specific brand names, game titles, logos, or character descriptions.
- Do not over-specify exact scene details unless absolutely necessary.
- Avoid aggressive compliance wording like `CRITICAL`, `TOTAL`, or `ABSOLUTE` unless testing proves it is safe.

Preferred direction:

```text
Please remove the text and UI elements from this image and fill the background naturally.
```

## Fast Triage Checklist

If Kakao clean fails again:

1. Check whether Gemini returned text refusal instead of image data.
2. Compare the current prompt with the short generic prompt above.
3. Check whether the uploaded asset contains famous branded IP, logos, or copyrighted promo art.
4. Retry with the shortest possible generic prompt before changing backend logic.
5. Only after that, inspect request shape and response parsing.

## Key Lesson

For Kakao clean, prompt simplicity is a reliability feature.

The backend chain can be correct while the model still refuses the request. When that happens, reduce prompt specificity before changing the pipeline.
