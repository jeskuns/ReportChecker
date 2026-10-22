/** 把 pdf.js 运行时复制到 public/vendor，避免依赖外部 CDN */
import { copyFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, '../node_modules/pdfjs-dist/build');
const DST = resolve(HERE, '../public/vendor');

mkdirSync(DST, { recursive: true });
for (const f of ['pdf.min.js', 'pdf.worker.min.js']) {
  copyFileSync(resolve(SRC, f), resolve(DST, f));
}
console.log('已复制 pdf.js 到 public/vendor');
