import { cpSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const outDir = join(root, 'public', 'assets', 'pdfjs');
const srcDir = join(root, 'node_modules', 'pdfjs-dist', 'build');

mkdirSync(outDir, { recursive: true });
for (const name of ['pdf.worker.min.mjs', 'pdf.worker.mjs']) {
  cpSync(join(srcDir, name), join(outDir, name));
}
