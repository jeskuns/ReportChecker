import { handleTest, json } from '../_lib/core.js';

export function onRequestPost({ request, env }) {
  return handleTest(request, env);
}

export function onRequest() {
  return json({ ok: false, message: '仅支持 POST' }, 405);
}
