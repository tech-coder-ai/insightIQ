import { HttpClient } from '@angular/common/http';
import {
  Component,
  ElementRef,
  Injector,
  Input,
  OnChanges,
  SimpleChanges,
  afterNextRender,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import * as pdfjsLib from 'pdfjs-dist';
import { firstValueFrom } from 'rxjs';
import mammoth from 'mammoth';

import { API_BASE } from '../core/api.config';
import { ensurePdfjsWorker } from './pdfjs-worker';

type HighlightRegion = {
  page: number;
  boxes: number[][];
  page_width: number;
  page_height: number;
};

@Component({
  selector: 'app-original-document-viewer',
  standalone: true,
  template: `
    @if (loading()) {
      <p class="viewer-hint">Loading original document…</p>
    } @else if (error()) {
      <p class="viewer-error">{{ error() }}</p>
    } @else if (mode() === 'pdf') {
      <div class="pdf-shell">
        <div class="pdf-toolbar">
          <button type="button" class="btn btn-ghost btn-sm" (click)="prevPage()" [disabled]="currentPage() <= 1">Previous</button>
          <span>Page {{ currentPage() }} / {{ totalPages() }}</span>
          <button type="button" class="btn btn-ghost btn-sm" (click)="nextPage()" [disabled]="currentPage() >= totalPages()">Next</button>
        </div>
        <div class="pdf-scroll" #pdfScroll>
          <div class="pdf-page-wrap">
            <canvas #pdfCanvas></canvas>
            <canvas #overlayCanvas class="pdf-overlay"></canvas>
          </div>
        </div>
      </div>
    } @else if (mode() === 'word') {
      <div class="word-shell doc-view-scroll" [innerHTML]="wordHtml()"></div>
    }
  `,
  styles: [
    `
      .viewer-hint, .viewer-error { font-size: var(--text-sm); color: var(--text-muted); padding: var(--space-4); }
      .viewer-error { color: var(--danger); }
      .pdf-shell { display: flex; flex-direction: column; gap: var(--space-3); min-height: 0; }
      .pdf-toolbar { display: flex; align-items: center; justify-content: center; gap: var(--space-3); font-size: var(--text-sm); flex-shrink: 0; }
      .pdf-scroll {
        max-height: min(62vh, 720px);
        overflow: auto;
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        background: #f5f5f5;
        padding: var(--space-4);
        display: flex;
        justify-content: center;
      }
      .pdf-page-wrap { position: relative; display: inline-block; line-height: 0; flex-shrink: 0; }
      .pdf-page-wrap canvas {
        display: block;
        border-radius: var(--radius-sm);
        box-shadow: var(--shadow-sm);
      }
      .pdf-overlay {
        position: absolute;
        left: 0;
        top: 0;
        pointer-events: none;
      }
      .word-shell { max-height: 60vh; overflow: auto; padding: var(--space-4); background: var(--surface-2); border-radius: var(--radius-md); }
      .word-shell :global(mark.viewer-highlight) {
        background: color-mix(in srgb, var(--warning, #d29922) 35%, transparent);
        padding: 0 2px; border-radius: 2px;
      }
    `,
  ],
})
export class OriginalDocumentViewerComponent implements OnChanges {
  @Input({ required: true }) documentId = '';
  @Input() mimeType: string | null = null;
  @Input() filename = '';
  @Input() highlightRegions: HighlightRegion[] | null = null;
  @Input() textSnippet = '';

  private readonly http = inject(HttpClient);
  private readonly injector = inject(Injector);
  private readonly pdfCanvas = viewChild<ElementRef<HTMLCanvasElement>>('pdfCanvas');
  private readonly overlayCanvas = viewChild<ElementRef<HTMLCanvasElement>>('overlayCanvas');
  private readonly pdfScroll = viewChild<ElementRef<HTMLElement>>('pdfScroll');

  readonly loading = signal(false);
  readonly error = signal('');
  readonly mode = signal<'pdf' | 'word' | ''>('');
  readonly wordHtml = signal('');
  readonly currentPage = signal(1);
  readonly totalPages = signal(1);

  private pdfDoc: pdfjsLib.PDFDocumentProxy | null = null;
  private renderScale = 1.35;
  private renderTask: pdfjsLib.RenderTask | null = null;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['documentId']) {
      void this.loadOriginal();
      return;
    }
    if (changes['highlightRegions'] && this.pdfDoc && this.mode() === 'pdf') {
      void this.renderPdfPage();
      return;
    }
    if (changes['highlightRegions']) {
      void this.loadOriginal();
    }
  }

  prevPage(): void {
    if (this.currentPage() > 1) {
      this.currentPage.update((p) => p - 1);
      void this.renderPdfPage();
    }
  }

  nextPage(): void {
    if (this.currentPage() < this.totalPages()) {
      this.currentPage.update((p) => p + 1);
      void this.renderPdfPage();
    }
  }

  private async loadOriginal(): Promise<void> {
    if (!this.documentId) return;
    this.loading.set(true);
    this.error.set('');
    this.mode.set('');
    this.pdfDoc = null;
    try {
      const blob = await firstValueFrom(
        this.http.get(`${API_BASE}/talk-to-docs/documents/${this.documentId}/original`, { responseType: 'blob' }),
      );
      const mime = this.mimeType || blob.type || '';
      const lower = this.filename.toLowerCase();
      if (mime.includes('pdf') || lower.endsWith('.pdf')) {
        ensurePdfjsWorker();
        const data = new Uint8Array(await blob.arrayBuffer());
        this.pdfDoc = await pdfjsLib.getDocument({ data }).promise;
        this.totalPages.set(this.pdfDoc.numPages);
        const targetPage = this.highlightRegions?.[0]?.page ?? 1;
        this.currentPage.set(Math.min(Math.max(targetPage, 1), this.pdfDoc.numPages));
        this.mode.set('pdf');
        this.loading.set(false);
        await this.waitForView();
        await this.renderPdfPage();
      } else if (
        mime.includes('wordprocessingml') ||
        mime.includes('msword') ||
        lower.endsWith('.docx') ||
        lower.endsWith('.doc')
      ) {
        this.mode.set('word');
        const buffer = await blob.arrayBuffer();
        const result = await mammoth.convertToHtml({ arrayBuffer: buffer });
        this.wordHtml.set(this.applyWordHighlight(result.value));
        this.loading.set(false);
      } else {
        throw new Error('Original preview is only supported for PDF and Word documents.');
      }
    } catch (err) {
      this.error.set(err instanceof Error ? err.message : 'Could not load original document.');
      this.loading.set(false);
    }
  }

  private waitForView(): Promise<void> {
    return new Promise((resolve) => {
      afterNextRender(() => resolve(), { injector: this.injector });
    });
  }

  private async renderPdfPage(): Promise<void> {
    if (!this.pdfDoc) return;
    await this.waitForView();
    const pageNum = this.currentPage();
    const page = await this.pdfDoc.getPage(pageNum);
    const viewport = page.getViewport({ scale: this.renderScale });
    const canvas = this.pdfCanvas()?.nativeElement;
    const overlay = this.overlayCanvas()?.nativeElement;
    if (!canvas || !overlay) return;

    if (this.renderTask) {
      try {
        await this.renderTask.cancel();
      } catch {
        /* ignore cancelled render */
      }
      this.renderTask = null;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const outputScale = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    overlay.width = canvas.width;
    overlay.height = canvas.height;
    overlay.style.width = `${viewport.width}px`;
    overlay.style.height = `${viewport.height}px`;

    const transform = outputScale !== 1 ? ([outputScale, 0, 0, outputScale, 0, 0] as const) : null;

    this.renderTask = page.render({
      canvasContext: ctx,
      canvas,
      viewport,
      transform: transform ? [...transform] : undefined,
    });
    await this.renderTask.promise;
    this.drawPdfHighlights(overlay, pageNum, viewport, outputScale);
  }

  private drawPdfHighlights(
    overlay: HTMLCanvasElement,
    pageNum: number,
    viewport: pdfjsLib.PageViewport,
    outputScale: number,
  ): void {
    const ctx = overlay.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(outputScale, 0, 0, outputScale, 0, 0);
    ctx.clearRect(0, 0, overlay.width / outputScale, overlay.height / outputScale);

    const rects = this.collectViewportRects(pageNum, viewport);
    const pad = 2.5;
    const radius = 4;

    for (const rect of rects) {
      const x = rect.x - pad;
      const y = rect.y - pad;
      const w = rect.w + pad * 2;
      const h = rect.h + pad * 2;
      ctx.fillStyle = 'rgba(210, 153, 34, 0.42)';
      ctx.strokeStyle = 'rgba(154, 103, 0, 0.75)';
      ctx.lineWidth = 1.25;
      if (typeof (ctx as CanvasRenderingContext2D & { roundRect?: Function }).roundRect === 'function') {
        ctx.beginPath();
        ctx.roundRect(x, y, w, h, radius);
        ctx.fill();
        ctx.stroke();
      } else {
        ctx.fillRect(x, y, w, h);
        ctx.strokeRect(x, y, w, h);
      }
    }

    if (rects.length) {
      this.scrollHighlightsIntoView(rects);
    }
  }

  private collectViewportRects(
    pageNum: number,
    viewport: pdfjsLib.PageViewport,
  ): Array<{ x: number; y: number; w: number; h: number }> {
    const regions = (this.highlightRegions ?? []).filter((r) => r.page === pageNum);
    const raw: Array<{ x: number; y: number; w: number; h: number }> = [];
    for (const region of regions) {
      for (const box of region.boxes ?? []) {
        if (box.length < 4) continue;
        const [x1, y1] = viewport.convertToViewportPoint(box[0], box[1]);
        const [x2, y2] = viewport.convertToViewportPoint(box[2], box[3]);
        raw.push({
          x: Math.min(x1, x2),
          y: Math.min(y1, y2),
          w: Math.abs(x2 - x1),
          h: Math.abs(y2 - y1),
        });
      }
    }
    return this.mergeViewportRects(raw);
  }

  private mergeViewportRects(
    rects: Array<{ x: number; y: number; w: number; h: number }>,
    yTol = 4,
    xGap = 8,
  ): Array<{ x: number; y: number; w: number; h: number }> {
    if (!rects.length) return [];
    const sorted = [...rects].sort((a, b) => a.y - b.y || a.x - b.x);
    const merged: Array<{ x: number; y: number; w: number; h: number }> = [];
    for (const rect of sorted) {
      const right = rect.x + rect.w;
      const bottom = rect.y + rect.h;
      let placed = false;
      for (let i = 0; i < merged.length; i += 1) {
        const cur = merged[i];
        const curRight = cur.x + cur.w;
        const curBottom = cur.y + cur.h;
        const sameLine = Math.abs(cur.y - rect.y) <= yTol && Math.abs(curBottom - bottom) <= yTol;
        const adjacent = rect.x <= curRight + xGap && right >= cur.x - xGap;
        if (sameLine && adjacent) {
          const nx = Math.min(cur.x, rect.x);
          const ny = Math.min(cur.y, rect.y);
          const nr = Math.max(curRight, right);
          const nb = Math.max(curBottom, bottom);
          merged[i] = { x: nx, y: ny, w: nr - nx, h: nb - ny };
          placed = true;
          break;
        }
      }
      if (!placed) merged.push({ ...rect });
    }
    return merged;
  }

  private scrollHighlightsIntoView(rects: Array<{ x: number; y: number; w: number; h: number }>): void {
    afterNextRender(
      () => {
        const container = this.pdfScroll()?.nativeElement;
        if (!container || !rects.length) return;
        const first = rects[0];
        const targetTop = Math.max(0, first.y - container.clientHeight * 0.35);
        container.scrollTo({ top: targetTop, behavior: 'smooth' });
      },
      { injector: this.injector },
    );
  }

  private applyWordHighlight(html: string): string {
    const snippet = (this.textSnippet || '').trim();
    if (!snippet || snippet.length < 8) return html;
    const match = snippet.slice(0, Math.min(80, snippet.length));
    const idx = html.indexOf(match);
    if (idx < 0) return html;
    return html.replace(match, `<mark class="viewer-highlight">${match}</mark>`);
  }
}
