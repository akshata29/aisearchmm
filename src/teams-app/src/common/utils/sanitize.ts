const HTML_ESCAPE_REGEX = /[&<>"']/g;
const HTML_ESCAPE_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
};

export function sanitizeMarkdown(input: string): string {
  return input.replace(HTML_ESCAPE_REGEX, (character) => HTML_ESCAPE_MAP[character]);
}

export function safeTrim(value: string | undefined | null): string {
  return value?.trim() ?? '';
}
