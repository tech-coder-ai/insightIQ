import { Routes } from '@angular/router';

import { LoginComponent } from './features/auth/login.component';
import { TalkToDataComponent } from './features/talk-to-data/talk-to-data.component';
import { HomeComponent } from './home.component';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'login', component: LoginComponent },
  { path: 'talk-to-data', component: TalkToDataComponent },
];
