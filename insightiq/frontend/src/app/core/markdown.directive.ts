import { Directive, ElementRef, Input, OnChanges, inject } from '@angular/core';

import { MarkdownService } from './markdown.service';

@Directive({
  selector: '[appMarkdown]',
  standalone: true,
})
export class MarkdownDirective implements OnChanges {
  @Input('appMarkdown') content = '';

  private readonly el = inject(ElementRef<HTMLElement>);
  private readonly md = inject(MarkdownService);

  ngOnChanges(): void {
    const host = this.el.nativeElement as HTMLElement;
    host.innerHTML = this.md.render(this.content);
    void this.md.renderMermaid(host);
  }
}
