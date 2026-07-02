import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE } from './api.config';

@Injectable({ providedIn: 'root' })
export class ExportService {
  private readonly http = inject(HttpClient);

  exportConversation(conversationId: string, format: 'markdown' | 'pdf' | 'pptx' = 'markdown'): Observable<HttpResponse<Blob>> {
    return this.http.get(`${API_BASE}/export/conversations/${conversationId}?format=${format}`, {
      responseType: 'blob',
      observe: 'response',
    });
  }

  exportDashboard(
    dashboardId: string,
    format: 'pdf' | 'pptx' | 'markdown' = 'pdf',
    includeFilters = true,
  ): Observable<HttpResponse<Blob>> {
    return this.http.get(
      `${API_BASE}/export/dashboards/${dashboardId}?format=${format}&include_filters=${includeFilters}`,
      {
        responseType: 'blob',
        observe: 'response',
      },
    );
  }

  downloadBlob(response: HttpResponse<Blob>, fallbackName: string): void {
    const blob = response.body;
    if (!blob) return;
    const disposition = response.headers.get('Content-Disposition') ?? '';
    const match = /filename="([^"]+)"/.exec(disposition);
    const filename = match?.[1] ?? fallbackName;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }
}
