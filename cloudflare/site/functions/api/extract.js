import { handleExtract, json } from '../_lib/core.js';

export function onRequestPost({ request, env }) {
  return handleExtract(request, env);
}

export function onRequest() {
  return json({ ok: false, error: '仅支持 POST' }, 405);
}
