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
  {
    path: 'datasources',
    component: DatasourcesComponent,
    canActivate: [authGuard],
    data: { title: 'Datasources', breadcrumb: ['Data', 'Datasources'] },
  },
  {
    path: 'datasources/:id',
    component: DatasourceDetailComponent,
    canActivate: [authGuard],
    data: { title: 'Datasource detail', breadcrumb: ['Data', 'Datasources', 'Detail'] },
  },
  {
    path: 'talk-to-data',
    component: TalkToDataComponent,
    canActivate: [authGuard],
    data: { title: 'Talk to Data', breadcrumb: ['Data', 'Talk to Data'] },
  },
  {
    path: 'talk-to-docs',
    component: TalkToDocsComponent,
    canActivate: [authGuard],
    data: { title: 'Talk to Docs', breadcrumb: ['Data', 'Talk to Docs'] },
  },
  {
    path: 'prompt-library',
    component: PromptLibraryComponent,
    canActivate: [authGuard],
    data: { title: 'Prompt Library', breadcrumb: ['Build', 'Prompt Library'] },
  },
  {
    path: 'prompt-studio',
    component: PromptStudioComponent,
    canActivate: [authGuard],
    data: { title: 'Prompt Studio', breadcrumb: ['Build', 'Prompt Studio'] },
  },
  {
    path: 'dashboards',
    component: DashboardListComponent,
    canActivate: [authGuard],
    data: { title: 'Dashboards', breadcrumb: ['Build', 'Dashboards'] },
  },
  {
    path: 'dashboards/:id',
    canActivate: [authGuard],
    data: { title: 'Dashboard', breadcrumb: ['Build', 'Dashboards', 'Detail'] },
    loadComponent: () =>
      import('./features/dashboards/dashboard-canvas.component').then((m) => m.DashboardCanvasComponent),
  },
];
