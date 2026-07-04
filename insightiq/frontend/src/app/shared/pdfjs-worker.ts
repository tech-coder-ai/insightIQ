import * as pdfjsLib from 'pdfjs-dist';

let worker: Worker | null = null;

function resolveWorkerUrl(): string {
  // Prefer bundled asset (served from app origin).
  try {
    return new URL('assets/pdfjs/pdf.worker.min.mjs', document.baseURI).href;
  } catch {
    return `/assets/pdfjs/pdf.worker.min.mjs`;
  }
}

function createWorker(url: string): Worker {
  return new Worker(url, { type: 'module' });
}

/** Configure pdf.js to use a dedicated module worker (avoids fake-worker import failures). */
export function ensurePdfjsWorker(): void {
  if (typeof Worker === 'undefined') return;
  if (pdfjsLib.GlobalWorkerOptions.workerPort) return;

  if (!worker) {
    worker = createWorker(resolveWorkerUrl());
  }

  pdfjsLib.GlobalWorkerOptions.workerPort = worker;
}
