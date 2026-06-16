import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE } from './api.config';

export type PromptTemplate = {
  id: string;
  name: string;
  description: string;
  bindings_json: Record<string, unknown>;
  is_shared: boolean;
  latest_version: number | null;
};

export type PromptVersion = {
  id: string;
  version_number: number;
  template_body: string;
  system_prompt: string;
  variables_schema_json: Record<string, unknown>;
  created_at: string;
};

export type PromptRun = {
  run_id: string;
  rendered_prompt: string;
  output: string;
  eval_scores: { faithfulness: number; relevancy: number; overall: number; notes: string };
  response: Record<string, unknown>;
};

@Injectable({ providedIn: 'root' })
export class PromptStudioService {
  private readonly http = inject(HttpClient);

  listTemplates(): Observable<PromptTemplate[]> {
    return this.http.get<PromptTemplate[]>(`${API_BASE}/prompt-studio/templates`);
  }

  createTemplate(body: {
    name: string;
    description?: string;
    template_body: string;
    system_prompt?: string;
    bindings_json?: Record<string, unknown>;
    variables_schema_json?: Record<string, unknown>;
  }): Observable<PromptTemplate> {
    return this.http.post<PromptTemplate>(`${API_BASE}/prompt-studio/templates`, body);
  }

  listVersions(templateId: string): Observable<PromptVersion[]> {
    return this.http.get<PromptVersion[]>(`${API_BASE}/prompt-studio/templates/${templateId}/versions`);
  }

  createVersion(
    templateId: string,
    body: {
      name: string;
      template_body: string;
      system_prompt?: string;
      variables_schema_json?: Record<string, unknown>;
    },
  ): Observable<PromptVersion> {
    return this.http.post<PromptVersion>(`${API_BASE}/prompt-studio/templates/${templateId}/versions`, body);
  }

  run(templateId: string, variables: Record<string, unknown>): Observable<PromptRun> {
    return this.http.post<PromptRun>(`${API_BASE}/prompt-studio/templates/${templateId}/run`, { variables });
  }

  listRuns(templateId: string): Observable<PromptRun[]> {
    return this.http.get<PromptRun[]>(`${API_BASE}/prompt-studio/templates/${templateId}/runs`);
  }

  share(templateId: string, isShared = true): Observable<PromptTemplate> {
    return this.http.patch<PromptTemplate>(
      `${API_BASE}/prompt-studio/templates/${templateId}/share?is_shared=${isShared}`,
      {},
    );
  }

  pinRun(runId: string, dashboardId: string, title?: string): Observable<{ card_id: string }> {
    return this.http.post<{ card_id: string }>(`${API_BASE}/prompt-studio/runs/${runId}/pin`, {
      dashboard_id: dashboardId,
      title,
    });
  }
}
