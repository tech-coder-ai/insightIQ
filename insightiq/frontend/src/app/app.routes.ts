import { Routes } from '@angular/router';

import { DashboardCanvasComponent } from './features/dashboards/dashboard-canvas.component';
import { DashboardListComponent } from './features/dashboards/dashboard-list.component';
import { PublicDashboardComponent } from './features/dashboards/public-dashboard.component';
import { LoginComponent } from './features/auth/login.component';
import { TalkToDataComponent } from './features/talk-to-data/talk-to-data.component';
import { TalkToDocsComponent } from './features/talk-to-docs/talk-to-docs.component';
import { HomeComponent } from './home.component';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'login', component: LoginComponent },
  { path: 'talk-to-data', component: TalkToDataComponent },
  { path: 'talk-to-docs', component: TalkToDocsComponent },
  { path: 'dashboards', component: DashboardListComponent },
  { path: 'dashboards/:id', component: DashboardCanvasComponent },
  { path: 'd/:token', component: PublicDashboardComponent },
];
