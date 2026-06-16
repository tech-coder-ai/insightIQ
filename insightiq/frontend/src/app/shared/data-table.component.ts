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
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: var(--text-sm);
      }
      th,
      td {
        padding: 10px 13px;
        border-bottom: 1px solid var(--border);
        text-align: left;
        color: var(--text);
      }
      tbody tr:last-child td { border-bottom: none; }
      tbody tr:hover td { background: var(--surface-2); }
      th {
        background: var(--surface-3);
        color: var(--text-2);
        font-weight: 600;
        position: sticky;
        top: 0;
      }
    `,
  ],
})
export class DataTableComponent {
  @Input({ required: true }) columns: string[] = [];
  @Input({ required: true }) rows: unknown[][] = [];
}
