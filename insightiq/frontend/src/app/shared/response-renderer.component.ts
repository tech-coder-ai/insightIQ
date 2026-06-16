import { JsonPipe } from '@angular/common';
import { Component, Input } from '@angular/core';

import { DataTableComponent } from './data-table.component';

type ResponsePayload = {
  response_type: string;
  title?: string;
  data: Record<string, unknown>;
};

@Component({
  selector: 'app-response-renderer',
  standalone: true,
  imports: [DataTableComponent, JsonPipe],
  template: `
    @if (payload) {
      <div class="response">
        @if (payload.title) {
          <h3>{{ payload.title }}</h3>
        }

        @switch (payload.response_type) {
          @case ('kpi_card') {
            <div class="kpi">
              <div class="kpi-value">{{ payload.data['value'] }}</div>
              <div class="kpi-label">{{ payload.data['label'] }}</div>
            </div>
          }
          @case ('chart_bar') {
            <div class="chart">
              @for (label of chartLabels; track label; let i = $index) {
                <div class="bar-row">
                  <span class="bar-label">{{ label }}</span>
                  <div class="bar-track">
                    <div class="bar-fill" [style.width.%]="barWidth(i)"></div>
                  </div>
                  <span class="bar-value">{{ chartValues[i] }}</span>
                </div>
              }
            </div>
          }
          @case ('data_table') {
            <app-data-table
              [columns]="tableColumns"
              [rows]="tableRows"
            />
          }
          @case ('explanation') {
            <div class="explanation">{{ payload.data['output'] }}</div>
          }
          @default {
            <pre>{{ payload | json }}</pre>
          }
        }
      </div>
    }
  `,
  styles: [
    `
      .response h3 {
        margin: 0 0 12px;
        font-size: var(--text-md);
        color: var(--text);
      }
      .kpi {
        padding: 24px;
        border-radius: var(--radius-md);
        background: var(--primary-soft);
        border: 1px solid var(--primary-soft-2);
        text-align: center;
      }
      .kpi-value {
        font-size: 36px;
        font-weight: 700;
        color: var(--primary-text);
      }
      .kpi-label {
        color: var(--text-2);
        margin-top: 4px;
      }
      .chart {
        display: grid;
        gap: 9px;
      }
      .bar-row {
        display: grid;
        grid-template-columns: 110px 1fr 60px;
        gap: 10px;
        align-items: center;
        font-size: var(--text-sm);
        color: var(--text-2);
      }
      .bar-track {
        height: 10px;
        background: var(--surface-3);
        border-radius: var(--radius-pill);
        overflow: hidden;
      }
      .bar-fill {
        height: 100%;
        background: linear-gradient(90deg, var(--primary), var(--primary-hover));
        border-radius: var(--radius-pill);
        transition: width var(--dur) var(--ease);
      }
      .bar-value { text-align: right; color: var(--text); font-variant-numeric: tabular-nums; }
      .explanation {
        line-height: 1.6;
        white-space: pre-wrap;
        color: var(--text);
      }
      pre {
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        padding: 12px;
        overflow: auto;
        font-size: var(--text-xs);
        font-family: var(--font-mono);
        color: var(--text-2);
      }
    `,
  ],
})
export class ResponseRendererComponent {
  @Input() payload: ResponsePayload | null = null;

  get tableColumns(): string[] {
    return (this.payload?.data['columns'] as string[]) ?? [];
  }

  get tableRows(): unknown[][] {
    return (this.payload?.data['rows'] as unknown[][]) ?? [];
  }

  get chartLabels(): string[] {
    return (this.payload?.data['labels'] as string[]) ?? [];
  }

  get chartValues(): number[] {
    return (this.payload?.data['values'] as number[]) ?? [];
  }

  barWidth(index: number): number {
    const values = this.chartValues;
    const max = Math.max(...values, 1);
    return (Number(values[index]) / max) * 100;
  }
}
