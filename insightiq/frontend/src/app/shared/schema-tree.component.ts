import { Component, Input } from '@angular/core';

type Column = { name: string; data_type: string };
type Table = { name: string; columns: Column[] };
type Schema = { tables: Table[] };

@Component({
  selector: 'app-schema-tree',
  standalone: true,
  template: `
    <div class="tree">
      @if (!schema?.tables?.length) {
        <p class="empty">No schema loaded</p>
      }
      @for (table of schema?.tables ?? []; track table.name) {
        <details open>
          <summary>{{ table.name }}</summary>
          <ul>
            @for (col of table.columns; track col.name) {
              <li>
                <span class="col-name">{{ col.name }}</span>
                <span class="col-type">{{ col.data_type }}</span>
              </li>
            }
          </ul>
        </details>
      }
    </div>
  `,
  styles: [
    `
      .tree {
        font-size: 13px;
      }
      details {
        margin-bottom: 8px;
      }
      summary {
        cursor: pointer;
        font-weight: 600;
      }
      ul {
        margin: 6px 0 0;
        padding-left: 16px;
        list-style: none;
      }
      li {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        padding: 2px 0;
      }
      .col-type {
        opacity: 0.6;
        font-family: monospace;
      }
      .empty {
        opacity: 0.6;
        font-size: 13px;
      }
    `,
  ],
})
export class SchemaTreeComponent {
  @Input() schema: Schema | null = null;
}
