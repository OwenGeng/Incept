// Strip only explicit two-language calls; unrelated Chinese on the same line
// must still be checked. data-no-translate is not a blanket audit exemption.
export function withoutInlineTranslations(line) {
  return line.replace(/\bt\(\s*(['"])([^'"\n]*)\1\s*,\s*(['"])([^'"\n]*)\3\s*\)/gu,
    (call, _zhQuote, _zh, _enQuote, english) =>
      english.trim() && !/[\u3400-\u9fff]/u.test(english) ? '' : call);
}

export function untranslatedStaticText(line, phrases) {
  return [...line.matchAll(/>([^<>]+)</gu)].map(match => match[1].trim())
    .filter(text => /[\u3400-\u9fff]/u.test(text) && !text.includes('{{') && !phrases.includes(text));
}
