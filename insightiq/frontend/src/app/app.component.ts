import { Component, computed, inject, signal } from '@angular/core';
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
    <div class="app-frame" [class.with-shell]="showShell()" [class.sidebar-open]="sidebarOpen()">
      @if (showShell()) {
        <button
          type="button"
          class="mobile-nav-toggle"
          (click)="toggleSidebar()"
          [attr.aria-expanded]="sidebarOpen()"
          aria-controls="app-sidebar"
        >
          <span class="sr-only">{{ sidebarOpen() ? 'Close menu' : 'Open menu' }}</span>
          <span class="bar"></span>
          <span class="bar"></span>
          <span class="bar"></span>
        </button>

        @if (sidebarOpen()) {
          <button type="button" class="sidebar-scrim" (click)="closeSidebar()" aria-label="Close menu"></button>
        }

        <nav id="app-sidebar" class="sidebar">
          <div class="brand">
            <span class="brand-mark">IQ</span>
            <span class="brand-name">InsightIQ</span>
          </div>

          <div class="nav-scroll">
            @for (group of nav; track group.title) {
              <div class="nav-group">
                <div class="nav-group-title">{{ group.title }}</div>
                @for (item of group.items; track item.path) {
                  <a
                    [routerLink]="item.path"
                    routerLinkActive="active"
                    class="nav-item"
                    (click)="closeSidebar()"
                  >
                    <span class="nav-icon" [innerHTML]="iconFor(item.icon)"></span>
                    <span>{{ item.label }}</span>
                  </a>
                }
              </div>
            }
          </div>

          <div class="sidebar-footer">
            <button class="theme-toggle" (click)="toggleTheme()" [title]="isDark() ? 'Switch to light mode' : 'Switch to dark mode'">
              <span class="theme-icon" [innerHTML]="isDark() ? iconMoon : iconSun"></span>
              <span class="theme-label">{{ isDark() ? 'Dark mode' : 'Light mode' }}</span>
            </button>

            <div class="user-row">
              <div class="avatar">{{ initials() }}</div>
              <div class="user-meta">
                <div class="user-name">{{ email() }}</div>
                <div class="user-sub">Workspace member</div>
              </div>
              <button class="signout" (click)="logout()" title="Sign out" aria-label="Sign out">
                <span [innerHTML]="iconLogout"></span>
              </button>
            </div>
          </div>
        </nav>
      }

      <main class="main-outlet" [class.content]="showShell()">
        <div [class.content-inner]="showShell()">
          <router-outlet />
        </div>
      </main>
    </div>
  `,
  styles: [`
    :host { display: block; height: 100vh; }

    .app-frame { display: flex; height: 100vh; overflow: hidden; }
    .app-frame.with-shell { display: flex; }

    /* ── Sidebar ── */
    .sidebar {
      width: var(--sidebar-w);
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      background: var(--surface-glass);
      backdrop-filter: blur(16px) saturate(1.4);
      border-right: 1px solid var(--border);
      padding: var(--space-5) var(--space-4);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: var(--space-1) var(--space-2) var(--space-6);
    }
    .brand-mark {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-md);
      display: grid;
      place-items: center;
      background: var(--primary-gradient);
      color: #fff;
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 13px;
      letter-spacing: -0.04em;
      box-shadow: var(--shadow-glow);
    }
    .brand-name {
      font-family: var(--font-display);
      font-size: var(--text-lg);
      font-weight: 700;
      letter-spacing: -0.03em;
    }

    .nav-scroll {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: var(--space-6);
    }
    .nav-group { display: flex; flex-direction: column; gap: 4px; }
    .nav-group-title {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--text-muted);
      font-weight: 600;
      padding: 0 var(--space-3) var(--space-2);
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px var(--space-3);
      border-radius: var(--radius-md);
      text-decoration: none;
      color: var(--text-2);
      font-size: var(--text-base);
      font-weight: 500;
      border: 1px solid transparent;
      transition:
        background var(--dur-fast) var(--ease),
        color var(--dur-fast) var(--ease),
        border-color var(--dur-fast) var(--ease);
    }
    .nav-item:hover {
      background: var(--surface-2);
      color: var(--text);
    }
    .nav-item.active {
      background: var(--primary-soft);
      color: var(--text);
      border-color: rgba(59, 130, 246, 0.2);
      font-weight: 550;
    }
    .nav-item.active .nav-icon { color: var(--primary-text); }
    .nav-icon {
      width: 18px;
      height: 18px;
      display: inline-flex;
      color: var(--text-muted);
      transition: color var(--dur-fast) var(--ease);
    }
    .nav-item:hover .nav-icon { color: var(--text-2); }
    .nav-icon :global(svg) { width: 18px; height: 18px; }

    /* ── Footer ── */
    .sidebar-footer {
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
      padding-top: var(--space-4);
      border-top: 1px solid var(--border);
    }

    .theme-toggle {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      padding: 10px var(--space-3);
      border-radius: var(--radius-md);
      border: 1px solid var(--border);
      background: var(--surface-2);
      color: var(--text-2);
      cursor: pointer;
      font-size: var(--text-sm);
      font-family: inherit;
      transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease);
    }
    .theme-toggle:hover { background: var(--surface-hover); color: var(--text); }
    .theme-icon {
      width: 18px;
      height: 18px;
      display: inline-flex;
      color: var(--text-muted);
    }
    .theme-icon :global(svg) { width: 18px; height: 18px; }
    .theme-label { font-weight: 500; }

    .user-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: var(--space-3);
      border-radius: var(--radius-md);
      background: var(--surface-2);
      border: 1px solid var(--border);
    }
    .avatar {
      width: 32px;
      height: 32px;
      border-radius: var(--radius-md);
      flex-shrink: 0;
      display: grid;
      place-items: center;
      font-size: 11px;
      font-weight: 650;
      background: var(--primary-soft);
      color: var(--primary-text);
      border: 1px solid rgba(59, 130, 246, 0.2);
    }
    .user-meta { flex: 1; min-width: 0; }
    .user-name {
      font-size: var(--text-sm);
      font-weight: 550;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .user-sub { font-size: 10px; color: var(--text-muted); margin-top: 1px; }
    .signout {
      border: none;
      background: transparent;
      color: var(--text-muted);
      cursor: pointer;
      padding: 6px;
      border-radius: var(--radius-sm);
      display: inline-flex;
      transition: color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
    }
    .signout :global(svg) { width: 18px; height: 18px; }
    .signout:hover { color: var(--danger); background: var(--danger-soft); }

    /* ── Content ── */
    .main-outlet { flex: 1; min-width: 0; }
    .main-outlet.content {
      overflow: hidden;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .content-inner {
      padding: var(--space-6) var(--space-8) var(--space-10);
      flex: 1;
      min-height: 0;
      overflow: auto;
      display: flex;
      flex-direction: column;
      max-width: calc(var(--content-max) + var(--space-8) * 2);
      margin: 0 auto;
      width: 100%;
      box-sizing: border-box;
    }

    .mobile-nav-toggle,
    .sidebar-scrim { display: none; }

    @media (max-width: 900px) {
      .mobile-nav-toggle {
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 5px;
        position: fixed;
        top: var(--space-4);
        left: var(--space-4);
        z-index: 1101;
        width: 44px;
        height: 44px;
        padding: 0;
        border-radius: var(--radius-md);
        border: 1px solid var(--border-strong);
        background: var(--surface);
        box-shadow: var(--shadow-md);
        cursor: pointer;
      }
      .mobile-nav-toggle .bar {
        display: block;
        width: 18px;
        height: 2px;
        margin: 0 auto;
        border-radius: 2px;
        background: var(--text);
      }
      .sidebar-scrim {
        display: block;
        position: fixed;
        inset: 0;
        z-index: 1099;
        border: none;
        background: var(--overlay);
        backdrop-filter: blur(2px);
        cursor: pointer;
      }
      .sidebar {
        position: fixed;
        top: 0;
        left: 0;
        bottom: 0;
        z-index: 1100;
        width: min(var(--sidebar-w), 86vw);
        transform: translateX(-105%);
        transition: transform var(--dur) var(--ease);
        box-shadow: var(--shadow-lg);
      }
      .app-frame.with-shell.sidebar-open .sidebar { transform: translateX(0); }
      .content-inner { padding: calc(var(--space-10) + 12px) var(--space-5) var(--space-8); }
    }

    @media (max-width: 720px) {
      .content-inner { padding: calc(var(--space-10) + 8px) var(--space-4) var(--space-6); }
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
  readonly sidebarOpen = signal(false);

  private readonly svg = 'stroke="currentColor" stroke-width="1.75" fill="none" stroke-linecap="round" stroke-linejoin="round"';
  readonly iconSun = this.safeIcon(`<svg viewBox="0 0 24 24" ${this.svg}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>`);
  readonly iconMoon = this.safeIcon(`<svg viewBox="0 0 24 24" ${this.svg}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`);
  readonly iconLogout = this.safeIcon(`<svg viewBox="0 0 24 24" ${this.svg}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`);

  showShell = computed(() => this.auth.isAuthenticated());
  isDark = computed(() => this.theme.theme() === 'dark');
  email = computed(() => this.auth.email() ?? 'user@insightiq');
  initials = computed(() => {
    const e = this.auth.email() ?? 'IQ';
    return e.slice(0, 2).toUpperCase();
  });

  toggleTheme(): void { this.theme.toggle(); }

  toggleSidebar(): void { this.sidebarOpen.update((v) => !v); }
  closeSidebar(): void { this.sidebarOpen.set(false); }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }

  iconFor(name: string): SafeHtml {
    const cached = this.iconCache.get(name);
    if (cached) return cached;
    const s = this.svg;
    const icons: Record<string, string> = {
      database: `<svg viewBox="0 0 24 24" ${s}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/></svg>`,
      chart: `<svg viewBox="0 0 24 24" ${s}><path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6" rx="0.5"/><rect x="13" y="7" width="3" height="10" rx="0.5"/></svg>`,
      doc: `<svg viewBox="0 0 24 24" ${s}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/></svg>`,
      pencil: `<svg viewBox="0 0 24 24" ${s}><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>`,
      library: `<svg viewBox="0 0 24 24" ${s}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
      grid: `<svg viewBox="0 0 24 24" ${s}><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>`,
    };
    const safe = this.safeIcon(icons[name] ?? '');
    this.iconCache.set(name, safe);
    return safe;
  }

  private safeIcon(html: string): SafeHtml {
    const safe = this.sanitizer.bypassSecurityTrustHtml(html);
    return safe;
  }
}
