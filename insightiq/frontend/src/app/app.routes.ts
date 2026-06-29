import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';
import { DashboardListComponent } from './features/dashboards/dashboard-list.component';
import { PublicDashboardComponent } from './features/dashboards/public-dashboard.component';
import { DatasourceDetailComponent } from './features/datasources/datasource-detail.component';
import { DatasourcesComponent } from './features/datasources/datasources.component';
import { PromptLibraryComponent } from './features/prompt-library/prompt-library.component';
import { PromptStudioComponent } from './features/prompt-studio/prompt-studio.component';
import { TalkToDataComponent } from './features/talk-to-data/talk-to-data.component';
import { TalkToDocsComponent } from './features/talk-to-docs/talk-to-docs.component';
import { LoginComponent } from './features/auth/login.component';

export const routes: Routes = [
  { path: '',          redirectTo: 'datasources', pathMatch: 'full' },
  { path: 'login',     component: LoginComponent },
  { path: 'd/:token',  component: PublicDashboardComponent },

  // Protected routes
  { path: 'datasources',      component: DatasourcesComponent,       canActivate: [authGuard] },
  { path: 'datasources/:id',  component: DatasourceDetailComponent,  canActivate: [authGuard] },
  { path: 'talk-to-data',     component: TalkToDataComponent,        canActivate: [authGuard] },
  { path: 'talk-to-docs',  component: TalkToDocsComponent,    canActivate: [authGuard] },
  { path: 'prompt-library', component: PromptLibraryComponent, canActivate: [authGuard] },
  { path: 'prompt-studio', component: PromptStudioComponent,  canActivate: [authGuard] },
  { path: 'dashboards',     component: DashboardListComponent,     canActivate: [authGuard] },
  {
    path: 'dashboards/:id',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/dashboards/dashboard-canvas.component').then((m) => m.DashboardCanvasComponent),
  },
];
