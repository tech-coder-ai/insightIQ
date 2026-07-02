import { Component, Input, OnChanges, computed, inject, signal } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

const STROKE = 'stroke="currentColor" stroke-width="1.75" fill="none" stroke-linecap="round" stroke-linejoin="round"';

const ICONS: Record<string, string> = {
  close: `<path d="M18 6 6 18M6 6l12 12"/>`,
  'star-outline': `<path d="M12 2.5 15 9l7 1-5 5 1.3 7L12 18.8 5.7 22 7 15 2 10l7-1z"/>`,
  'star-filled': `<path fill="currentColor" stroke="none" d="M12 2.5 15 9l7 1-5 5 1.3 7L12 18.8 5.7 22 7 15 2 10l7-1z"/>`,
  edit: `<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>`,
  trash: `<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>`,
  refresh: `<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/>`,
  copy: `<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>`,
  check: `<polyline points="20 6 9 17 4 12"/>`,
  'check-circle': `<circle cx="12" cy="12" r="9"/><polyline points="8.5 12.5 11 15 16 9"/>`,
  'alert-circle': `<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="13"/><line x1="12" y1="16.5" x2="12" y2="16.51"/>`,
  info: `<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="7.5" x2="12" y2="7.51"/>`,
  pin: `<path d="M12 2a6 6 0 0 0-6 6c0 4.5 6 12 6 12s6-7.5 6-12a6 6 0 0 0-6-6z"/><circle cx="12" cy="8" r="2"/>`,
  plus: `<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>`,
  upload: `<path d="M12 3v12"/><path d="m7 8 5-5 5 5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>`,
  folder: `<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>`,
  search: `<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>`,
  'external-link': `<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>`,
  'chevron-down': `<polyline points="6 9 12 15 18 9"/>`,
  warning: `<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12" y2="17.01"/>`,
  database: `<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>`,
  doc: `<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>`,
  chart: `<path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6" rx="0.5"/><rect x="13" y="7" width="3" height="10" rx="0.5"/>`,
  grid: `<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>`,
  library: `<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>`,
  download: `<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>`,
  'more-horizontal': `<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>`,
  sparkle: `<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>`,
  file: `<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M13 2v7h7"/>`,
};

@Component({
  selector: 'app-icon',
  standalone: true,
  template: `<span class="app-icon" [style.width.px]="size" [style.height.px]="size" [innerHTML]="svg()"></span>`,
  styles: [
    `
      .app-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
      .app-icon ::ng-deep svg { width: 100%; height: 100%; display: block; }
    `,
  ],
})
export class IconComponent implements OnChanges {
  @Input() name = 'info';
  @Input() size = 16;

  private readonly sanitizer = inject(DomSanitizer);
  private readonly nameSignal = signal('info');

  ngOnChanges(): void {
    this.nameSignal.set(this.name);
  }

  readonly svg = computed<SafeHtml>(() => {
    const body = ICONS[this.nameSignal()] ?? ICONS['info'];
    const markup = `<svg viewBox="0 0 24 24" ${STROKE}>${body}</svg>`;
    return this.sanitizer.bypassSecurityTrustHtml(markup);
  });
}
