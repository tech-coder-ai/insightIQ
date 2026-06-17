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
        @if (showTitle && payload.title) {
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
          @case ('chart_line') {
            <div class="line-chart">
              <svg viewBox="0 0 400 160" preserveAspectRatio="none" class="line-svg">
                <polyline [attr.points]="linePoints" fill="none" stroke="var(--primary)" stroke-width="2" />
                @for (point of linePointCoords; track point.i) {
                  <circle [attr.cx]="point.x" [attr.cy]="point.y" r="3" fill="var(--primary)" />
                }
              </svg>
              <div class="line-labels">
                @for (label of chartLabels; track label) {
                  <span>{{ label }}</span>
                }
              </div>
              <div class="line-values">
                @for (value of chartValues; track $index) {
                  <span>{{ value }}</span>
                }
              </div>
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
      .line-chart { display: grid; gap: 8px; }
      .line-svg { width: 100%; height: 160px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md); }
      .line-labels, .line-values {
        display: grid;
        grid-auto-flow: column;
        grid-auto-columns: 1fr;
        gap: 6px;
        font-size: var(--text-xs);
        color: var(--text-muted);
        text-align: center;
        font-variant-numeric: tabular-nums;
      }
      .line-values { color: var(--text-2); font-weight: 550; }
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
  @Input() showTitle = true;

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

  get linePointCoords(): { i: number; x: number; y: number }[] {
    const values = this.chartValues;
    if (!values.length) return [];
    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const span = Math.max(max - min, 1);
    const last = values.length - 1;
    return values.map((value, i) => ({
      i,
      x: last === 0 ? 200 : (i / last) * 380 + 10,
      y: 150 - ((Number(value) - min) / span) * 130,
    }));
  }

  get linePoints(): string {
    return this.linePointCoords.map((p) => `${p.x},${p.y}`).join(' ');
  }
}
