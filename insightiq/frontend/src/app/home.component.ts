import { AsyncPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

type HealthzResponse = { status: string };

@Component({
  standalone: true,
  imports: [AsyncPipe, RouterLink],
  template: `
    <div class="wrap">
      <div class="card">
        <div class="title">InsightIQ</div>
        <div class="subtitle">v2 scaffold (Phase 0)</div>

        <div class="section">
          <div class="label">Gateway health</div>
          <div class="value">
            @if (health$ | async; as h) {
              <span class="pill ok">ok</span>
              <span class="mono">{{ h.status }}</span>
            } @else {
              <span class="pill warn">connecting</span>
              <span class="mono">http://localhost:8000/healthz</span>
            }
          </div>
        </div>

        <div class="links">
          <a routerLink="/login">Login / Register</a>
          <a routerLink="/talk-to-data">Talk to Data</a>
          <a routerLink="/talk-to-docs">Talk to Documents</a>
        </div>
      </div>
    </div>
  `,
  styles: [
    `
      .wrap {
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
      }
      .card {
        width: min(720px, 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: rgba(255, 255, 255, 0.04);
        border-radius: 16px;
        padding: 24px;
        backdrop-filter: blur(10px);
      }
      .title {
        font-size: 28px;
        font-weight: 650;
        letter-spacing: 0.2px;
      }
      .subtitle {
        opacity: 0.75;
        margin-top: 4px;
      }
      .section {
        margin-top: 20px;
        display: grid;
        gap: 8px;
      }
      .label {
        font-size: 12px;
        opacity: 0.7;
        text-transform: uppercase;
        letter-spacing: 0.12em;
      }
      .value {
        display: flex;
        gap: 10px;
        align-items: center;
        flex-wrap: wrap;
      }
      .pill {
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        border: 1px solid rgba(255, 255, 255, 0.14);
      }
      .ok {
        background: rgba(24, 160, 88, 0.22);
      }
      .warn {
        background: rgba(233, 176, 29, 0.18);
      }
      .mono {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
          monospace;
        opacity: 0.9;
      }
      .links {
        margin-top: 20px;
        display: flex;
        gap: 16px;
      }
      .links a {
        color: #8ec5ff;
        text-decoration: none;
      }
    `,
  ],
})
export class HomeComponent {
  private readonly http = inject(HttpClient);
  readonly health$ = this.http.get<HealthzResponse>('http://localhost:8000/healthz');
}

