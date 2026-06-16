import { Injectable } from '@angular/core';
import DOMPurify from 'dompurify';
import { marked } from 'marked';

/**
 * Renders untrusted Markdown (LLM output) into sanitized HTML.
 * Supports GFM tables, code blocks, lists, blockquotes, and ```mermaid
 * diagrams (rendered lazily so mermaid is only loaded when needed).
 */
@Injectable({ providedIn: 'root' })
export class MarkdownService {
  private mermaidLoaded = false;
  private seq = 0;

  constructor() {
    marked.setOptions({ gfm: true, breaks: true });
  }

  render(md: string | null | undefined): string {
    const raw = marked.parse(md ?? '', { async: false }) as string;
    return DOMPurify.sanitize(raw, {
      ADD_ATTR: ['target', 'class'],
      ADD_TAGS: ['cite'],
    });
  }

  /** Convert ```mermaid code blocks inside `host` into rendered SVG diagrams. */
  async renderMermaid(host: HTMLElement): Promise<void> {
    const blocks = Array.from(
      host.querySelectorAll('code.language-mermaid, pre > code.language-mermaid'),
    );
    if (blocks.length === 0) return;

    const { default: mermaid } = await import('mermaid');
    if (!this.mermaidLoaded) {
      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral' });
      this.mermaidLoaded = true;
    }

    for (const codeEl of blocks) {
      const pre = codeEl.closest('pre') ?? codeEl;
      const source = codeEl.textContent ?? '';
      const id = `mermaid-${Date.now()}-${this.seq++}`;
      try {
        const { svg } = await mermaid.render(id, source);
        const wrapper = document.createElement('div');
        wrapper.className = 'mermaid-diagram';
        wrapper.innerHTML = svg;
        pre.replaceWith(wrapper);
      } catch {
        // Leave the original code block in place if the diagram is invalid.
      }
    }
  }
}
