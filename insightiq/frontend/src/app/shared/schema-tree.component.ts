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
        font-size: var(--text-sm);
      }
      details {
        margin-bottom: 6px;
      }
      summary {
        cursor: pointer;
        font-weight: 600;
        padding: 4px 0;
        color: var(--text);
      }
      summary:hover { color: var(--primary-text); }
      ul {
        margin: 4px 0 0;
        padding-left: 16px;
        list-style: none;
      }
      li {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        padding: 3px 0;
        color: var(--text-2);
      }
      .col-name { color: var(--text); }
      .col-type {
        color: var(--text-muted);
        font-family: var(--font-mono);
        font-size: var(--text-xs);
      }
      .empty {
        color: var(--text-muted);
        font-size: var(--text-sm);
      }
    `,
  ],
})
export class SchemaTreeComponent {
  @Input() schema: Schema | null = null;
}
