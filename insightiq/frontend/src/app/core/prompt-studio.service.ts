import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE } from './api.config';

export type PromptBindings = {
  type?: 'none' | 'sql' | 'rag' | 'file';
  datasource_id?: string;
  sql?: string;
  collection_id?: string;
  query_variable?: string;
  rag_profile?: string;
  document_id?: string;
};

export type PromptTemplate = {
  id: string;
  name: string;
  description: string;
  bindings_json: PromptBindings;
  is_shared: boolean;
  latest_version: number | null;
};

export type PromptTemplateDetail = PromptTemplate & {
  latest_version_id: string | null;
  template_body: string;
  system_prompt: string;
  variables_schema_json: Record<string, unknown>;
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
  context_preview?: string;
};

@Injectable({ providedIn: 'root' })
export class PromptStudioService {
  private readonly http = inject(HttpClient);

  listTemplates(): Observable<PromptTemplate[]> {
    return this.http.get<PromptTemplate[]>(`${API_BASE}/prompt-studio/templates`);
  }

  getTemplate(id: string): Observable<PromptTemplateDetail> {
    return this.http.get<PromptTemplateDetail>(`${API_BASE}/prompt-studio/templates/${id}`);
  }

  createTemplate(body: {
    name: string;
    description?: string;
    template_body: string;
    system_prompt?: string;
    bindings_json?: PromptBindings;
    variables_schema_json?: Record<string, unknown>;
  }): Observable<PromptTemplate> {
    return this.http.post<PromptTemplate>(`${API_BASE}/prompt-studio/templates`, body);
  }

  updateTemplate(
    id: string,
    body: { name?: string; description?: string; bindings_json?: PromptBindings },
  ): Observable<PromptTemplate> {
    return this.http.patch<PromptTemplate>(`${API_BASE}/prompt-studio/templates/${id}`, body);
  }

  listVersions(templateId: string): Observable<PromptVersion[]> {
    return this.http.get<PromptVersion[]>(`${API_BASE}/prompt-studio/templates/${templateId}/versions`);
  }

  createVersion(
    templateId: string,
    body: {
      template_body: string;
      system_prompt?: string;
      variables_schema_json?: Record<string, unknown>;
    },
  ): Observable<PromptVersion> {
    return this.http.post<PromptVersion>(`${API_BASE}/prompt-studio/templates/${templateId}/versions`, body);
  }

  run(
    templateId: string,
    variables: Record<string, unknown>,
    versionId?: string,
  ): Observable<PromptRun> {
    return this.http.post<PromptRun>(`${API_BASE}/prompt-studio/templates/${templateId}/run`, {
      variables,
      version_id: versionId ?? null,
    });
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
