import { Component, Input } from '@angular/core';

import { ResponseRendererComponent } from './response-renderer.component';

@Component({
  selector: 'app-dashboard-card',
  standalone: true,
  imports: [ResponseRendererComponent],
  template: `
    <div class="dcard">
      <div class="head">
        <h3>{{ title }}</h3>
        <span class="mode">{{ refreshMode }}</span>
      </div>
      <app-response-renderer [payload]="payload" />
    </div>
  `,
  styles: [
    `
      .dcard {
        height: 100%;
        display: flex;
        flex-direction: column;
        padding: 14px;
        box-sizing: border-box;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-sm);
      }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
      }
      h3 {
        margin: 0;
        font-size: var(--text-base);
        color: var(--text);
      }
      .mode {
        font-size: var(--text-xs);
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
    `,
  ],
})
export class DashboardCardComponent {
  @Input() title = '';
  @Input() refreshMode = 'snapshot';
  @Input() payload: { response_type: string; title?: string; data: Record<string, unknown> } | null = null;
}
