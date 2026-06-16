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
        padding: 12px;
        box-sizing: border-box;
      }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }
      h3 {
        margin: 0;
        font-size: 14px;
      }
      .mode {
        font-size: 11px;
        opacity: 0.6;
        text-transform: uppercase;
      }
    `,
  ],
})
export class DashboardCardComponent {
  @Input() title = '';
  @Input() refreshMode = 'snapshot';
  @Input() payload: { response_type: string; title?: string; data: Record<string, unknown> } | null = null;
}
