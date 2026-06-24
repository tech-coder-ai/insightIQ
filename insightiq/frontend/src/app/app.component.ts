import { Component, computed, inject } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth.service';
import { ThemeService } from './core/theme.service';

type NavItem = { path: string; icon: string; label: string };
type NavGroup = { title: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    title: 'Data',
    items: [
      { path: '/datasources',  icon: 'database', label: 'Datasources'  },
      { path: '/talk-to-data', icon: 'chart',    label: 'Talk to Data' },
      { path: '/talk-to-docs', icon: 'doc',      label: 'Talk to Docs' },
    ],
  },
  {
    title: 'Build',
    items: [
      { path: '/prompt-library', icon: 'library', label: 'Prompt Library' },
      { path: '/prompt-studio', icon: 'pencil', label: 'Prompt Studio' },
      { path: '/dashboards',    icon: 'grid',   label: 'Dashboards'    },
    ],
  },
];

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    @if (showShell()) {
      <div class="shell">
        <nav class="sidebar">
          <div class="brand">
            <span class="brand-mark">IQ</span>
            <span class="brand-name">InsightIQ</span>
          </div>

          <div class="nav-scroll">
            @for (group of nav; track group.title) {
              <div class="nav-group">
                <div class="nav-group-title">{{ group.title }}</div>
                @for (item of group.items; track item.path) {
                  <a [routerLink]="item.path" routerLinkActive="active" class="nav-item">
                    <span class="nav-icon" [innerHTML]="iconFor(item.icon)"></span>
                    <span>{{ item.label }}</span>
                  </a>
                }
              </div>
            }
          </div>

          <div class="sidebar-footer">
            <button class="theme-toggle" (click)="toggleTheme()" [title]="isDark() ? 'Switch to light' : 'Switch to dark'">
              <span class="track" [class.light]="!isDark()">
                <span class="thumb">{{ isDark() ? '🌙' : '☀️' }}</span>
              </span>
              <span class="theme-label">{{ isDark() ? 'Dark' : 'Light' }}</span>
            </button>

            <div class="user-row">
              <div class="avatar">{{ initials() }}</div>
              <div class="user-meta">
                <div class="user-name">{{ email() }}</div>
                <div class="user-sub">Signed in</div>
              </div>
              <button class="signout" (click)="logout()" title="Sign out" aria-label="Sign out">⏻</button>
            </div>
          </div>
        </nav>

        <main class="content">
          <div class="content-inner">
            <router-outlet />
          </div>
        </main>
      </div>
    } @else {
      <router-outlet />
    }
  `,
  styles: [`
    :host { display: block; height: 100vh; }

    .shell { display: flex; height: 100vh; overflow: hidden; }

    /* ── Sidebar ── */
    .sidebar {
      width: var(--sidebar-w);
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      background: var(--surface);
      border-right: 1px solid var(--border);
      padding: var(--space-5) var(--space-3);
    }

    .brand {
      display: flex; align-items: center; gap: 10px;
      padding: 4px var(--space-2) var(--space-5);
    }
    .brand-mark {
      width: 32px; height: 32px; border-radius: 9px;
      display: grid; place-items: center;
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      color: #fff; font-weight: 700; font-size: 13px; letter-spacing: -0.5px;
      box-shadow: var(--shadow-sm);
    }
    .brand-name { font-size: var(--text-lg); font-weight: 700; letter-spacing: -0.02em; }

    .nav-scroll { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-5); }
    .nav-group { display: flex; flex-direction: column; gap: 2px; }
    .nav-group-title {
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.09em;
      color: var(--text-muted); font-weight: 700;
      padding: 0 var(--space-2) 6px;
    }

    .nav-item {
      display: flex; align-items: center; gap: 11px;
      padding: 9px var(--space-2); border-radius: var(--radius-md);
      text-decoration: none; color: var(--text-2);
      font-size: var(--text-base); font-weight: 500;
      transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease);
      position: relative;
    }
    .nav-item:hover { background: var(--surface-2); color: var(--text); }
    .nav-item.active { background: var(--primary-soft); color: var(--primary-text); }
    .nav-item.active::before {
      content: ''; position: absolute; left: -12px; top: 50%; transform: translateY(-50%);
      width: 3px; height: 18px; border-radius: 0 3px 3px 0; background: var(--primary);
    }
    .nav-icon { width: 18px; height: 18px; display: inline-flex; }
    .nav-icon :global(svg) { width: 18px; height: 18px; }

    /* ── Footer ── */
    .sidebar-footer { display: flex; flex-direction: column; gap: var(--space-3); padding-top: var(--space-4); }

    .theme-toggle {
      display: flex; align-items: center; gap: 10px;
      padding: 7px var(--space-2); border-radius: var(--radius-md);
      border: 1px solid var(--border); background: var(--surface-2);
      color: var(--text-2); cursor: pointer; font-size: var(--text-sm);
      transition: background var(--dur-fast) var(--ease);
    }
    .theme-toggle:hover { background: var(--surface-hover); }
    .track {
      width: 38px; height: 22px; border-radius: var(--radius-pill);
      background: var(--surface-3); border: 1px solid var(--border-strong);
      position: relative; flex-shrink: 0; transition: background var(--dur) var(--ease);
    }
    .thumb {
      position: absolute; top: 1px; left: 1px;
      width: 18px; height: 18px; border-radius: 50%;
      display: grid; place-items: center; font-size: 10px;
      background: var(--surface); box-shadow: var(--shadow-sm);
      transition: transform var(--dur) var(--ease);
    }
    .track.light .thumb { transform: translateX(16px); }
    .theme-label { font-weight: 500; }

    .user-row {
      display: flex; align-items: center; gap: 10px;
      padding: var(--space-2); border-radius: var(--radius-md);
      background: var(--surface-2); border: 1px solid var(--border);
    }
    .avatar {
      width: 30px; height: 30px; border-radius: 50%; flex-shrink: 0;
      display: grid; place-items: center; font-size: 12px; font-weight: 650;
      background: var(--primary-soft-2); color: var(--primary-text);
    }
    .user-meta { flex: 1; min-width: 0; }
    .user-name { font-size: var(--text-sm); font-weight: 550; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .user-sub { font-size: 10px; color: var(--text-muted); }
    .signout {
      border: none; background: transparent; color: var(--text-muted);
      cursor: pointer; font-size: 15px; padding: 4px; border-radius: var(--radius-sm);
      transition: color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
    }
    .signout:hover { color: var(--danger); background: var(--danger-soft); }

    /* ── Content ── */
    .content { flex: 1; overflow-y: auto; }
    .content-inner { padding: var(--space-8) var(--space-8) var(--space-12); }

    @media (max-width: 720px) {
      .sidebar { width: 64px; padding: var(--space-4) var(--space-2); }
      .brand-name, .nav-item span:last-child, .nav-group-title, .theme-label, .user-meta { display: none; }
      .nav-item { justify-content: center; }
      .content-inner { padding: var(--space-5); }
    }
  `],
})
export class AppComponent {
  private readonly auth = inject(AuthService);
  private readonly theme = inject(ThemeService);
  private readonly router = inject(Router);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly iconCache = new Map<string, SafeHtml>();
  readonly nav = NAV;

  showShell = computed(() => this.auth.isAuthenticated());
  isDark = computed(() => this.theme.theme() === 'dark');
  email = computed(() => this.auth.email() ?? 'user@insightiq');
  initials = computed(() => {
    const e = this.auth.email() ?? 'IQ';
    return e.slice(0, 2).toUpperCase();
  });

  toggleTheme(): void { this.theme.toggle(); }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }

  iconFor(name: string): SafeHtml {
    const cached = this.iconCache.get(name);
    if (cached) return cached;
    const s = 'stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"';
    const icons: Record<string, string> = {
      database: `<svg viewBox="0 0 24 24" ${s}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/></svg>`,
      chart: `<svg viewBox="0 0 24 24" ${s}><path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6"/><rect x="13" y="7" width="3" height="10"/></svg>`,
      doc: `<svg viewBox="0 0 24 24" ${s}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h8"/></svg>`,
      pencil: `<svg viewBox="0 0 24 24" ${s}><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>`,
      library: `<svg viewBox="0 0 24 24" ${s}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
      grid: `<svg viewBox="0 0 24 24" ${s}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>`,
    };
    const safe = this.sanitizer.bypassSecurityTrustHtml(icons[name] ?? '');
    this.iconCache.set(name, safe);
    return safe;
  }
}
