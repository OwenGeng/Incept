"use client";

import { Bold, Code2, Heading1, Heading2, Italic, List, ListOrdered, Quote } from "lucide-react";
import { useEffect, useRef } from "react";

const ALLOWED_TAGS = new Set([
  "B", "STRONG", "I", "EM", "H1", "H2", "H3", "P", "DIV", "UL", "OL", "LI",
  "BLOCKQUOTE", "CODE", "PRE", "BR",
]);

function sanitizeHtml(value: string): string {
  const parsed = new DOMParser().parseFromString(value, "text/html");
  const clean = (node: Node): void => {
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === Node.ELEMENT_NODE) {
        const element = child as HTMLElement;
        if (!ALLOWED_TAGS.has(element.tagName)) {
          element.replaceWith(...Array.from(element.childNodes));
          continue;
        }
        for (const attribute of Array.from(element.attributes)) element.removeAttribute(attribute.name);
      }
      clean(child);
    }
  };
  clean(parsed.body);
  return parsed.body.innerHTML;
}

export function RichDocumentEditor({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  const editor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = editor.current;
    if (!element || document.activeElement === element) return;
    const next = sanitizeHtml(value);
    if (element.innerHTML !== next) element.innerHTML = next;
  }, [value]);

  const command = (name: string, argument?: string) => {
    editor.current?.focus();
    document.execCommand(name, false, argument);
    if (editor.current) onChange(sanitizeHtml(editor.current.innerHTML));
  };

  const toolbar = [
    { label: "H1", icon: Heading1, action: () => command("formatBlock", "h1") },
    { label: "H2", icon: Heading2, action: () => command("formatBlock", "h2") },
    { label: "Bold", icon: Bold, action: () => command("bold") },
    { label: "Italic", icon: Italic, action: () => command("italic") },
    { label: "Bullet list", icon: List, action: () => command("insertUnorderedList") },
    { label: "Numbered list", icon: ListOrdered, action: () => command("insertOrderedList") },
    { label: "Quote", icon: Quote, action: () => command("formatBlock", "blockquote") },
    { label: "Code", icon: Code2, action: () => command("formatBlock", "pre") },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap gap-1 border-b border-[#ebeef5] px-4 py-2">
        {toolbar.map(({ label, icon: Icon, action }) => <button key={label} type="button" title={label} aria-label={label} onMouseDown={(event) => { event.preventDefault(); action(); }} className="rounded-lg p-2 text-[#606266] hover:bg-[#f5f1ff] hover:text-[#8b5cf6]"><Icon className="size-4" /></button>)}
      </div>
      <div
        ref={editor}
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        onInput={(event) => onChange(sanitizeHtml(event.currentTarget.innerHTML))}
        onPaste={(event) => {
          event.preventDefault();
          document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
        }}
        className="video-rich-document min-h-0 flex-1 overflow-y-auto px-10 py-8 text-[15px] leading-7 outline-none [&_blockquote]:border-l-4 [&_blockquote]:border-[#c4b5fd] [&_blockquote]:pl-4 [&_h1]:mb-4 [&_h1]:text-3xl [&_h1]:font-bold [&_h2]:mb-3 [&_h2]:text-2xl [&_h2]:font-semibold [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mb-3 [&_pre]:rounded-xl [&_pre]:bg-[#f5f7fa] [&_pre]:p-4 [&_ul]:list-disc [&_ul]:pl-6 empty:before:pointer-events-none empty:before:text-[#b1b5bf] empty:before:content-[attr(data-placeholder)]"
      />
    </div>
  );
}
