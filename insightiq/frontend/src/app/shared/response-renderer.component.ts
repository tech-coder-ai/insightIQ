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
        font-size: 16px;
      }
      .kpi {
        padding: 20px;
        border-radius: 12px;
        background: rgba(88, 166, 255, 0.12);
        text-align: center;
      }
      .kpi-value {
        font-size: 36px;
        font-weight: 700;
      }
      .kpi-label {
        opacity: 0.75;
        margin-top: 4px;
      }
      .chart {
        display: grid;
        gap: 8px;
      }
      .bar-row {
        display: grid;
        grid-template-columns: 100px 1fr 60px;
        gap: 8px;
        align-items: center;
        font-size: 13px;
      }
      .bar-track {
        height: 10px;
        background: rgba(255, 255, 255, 0.08);
        border-radius: 999px;
        overflow: hidden;
      }
      .bar-fill {
        height: 100%;
        background: #58a6ff;
        border-radius: 999px;
      }
      .explanation {
        line-height: 1.5;
        white-space: pre-wrap;
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
