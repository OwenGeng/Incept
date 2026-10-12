// Restore only text the compatibility bridge actually translated.
// A reactive component may already have rendered the new locale itself.
export function restoredLocaleText(current: string, original: string | undefined, translated: string | undefined): string {
  return original !== undefined && current === translated ? original : current;
}
