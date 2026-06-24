import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { PromptStudioService, PromptTemplate } from '../core/prompt-studio.service';

@Component({
  standalone: true,
  imports: [RouterLink],
  selector: 'app-prompt-picker',
  template: `
    <label class="picker">
      <span class="picker-label">Prompt template</span>
      <select [value]="selectedId ?? ''" (change)="onChange($any($event.target).value)">
        <option value="">None — default behavior</option>
        @for (t of templates(); track t.id) {
          <option [value]="t.id">
            {{ t.name }}{{ t.is_shared && !t.is_mine ? ' (shared)' : '' }}
          </option>
        }
      </select>
    </label>
    @if (selectedId) {
      <a class="picker-link" [routerLink]="['/prompt-studio']" [queryParams]="{ template: selectedId }">
        Open in Studio ↗
      </a>
    }
  `,
  styles: [`
    :host { display: block; margin-bottom: 10px; }
    .picker { display: grid; gap: 6px; }
    .picker-label {
      font-size: var(--text-xs); color: var(--text-2); font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.04em;
    }
    select {
      width: 100%; padding: 8px 10px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong); background: var(--input-bg);
      color: var(--text); font-family: inherit; font-size: var(--text-sm);
    }
    .picker-link {
      font-size: var(--text-xs); color: var(--primary-text); text-decoration: none;
    }
    .picker-link:hover { text-decoration: underline; }
  `],
})
export class PromptPickerComponent implements OnInit {
  private readonly promptService = inject(PromptStudioService);

  @Input() selectedId: string | null = null;
  @Output() selectedIdChange = new EventEmitter<string | null>();

  readonly templates = signal<PromptTemplate[]>([]);

  ngOnInit(): void {
    this.promptService.listTemplates({ scope: 'all' }).subscribe({
      next: (items) => this.templates.set(items),
    });
  }

  onChange(value: string): void {
    const id = value || null;
    this.selectedId = id;
    this.selectedIdChange.emit(id);
  }
}
