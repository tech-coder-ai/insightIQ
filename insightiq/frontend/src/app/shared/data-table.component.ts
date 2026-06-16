import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-data-table',
  standalone: true,
  template: `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            @for (col of columns; track col) {
              <th>{{ col }}</th>
            }
          </tr>
        </thead>
        <tbody>
          @for (row of rows; track $index) {
            <tr>
              @for (cell of row; track $index) {
                <td>{{ cell }}</td>
              }
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
  styles: [
    `
      .table-wrap {
        overflow: auto;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
      }
      th,
      td {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        text-align: left;
      }
      th {
        background: rgba(255, 255, 255, 0.04);
      }
    `,
  ],
})
export class DataTableComponent {
  @Input({ required: true }) columns: string[] = [];
  @Input({ required: true }) rows: unknown[][] = [];
}
