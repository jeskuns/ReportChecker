import { health } from '../_lib/core.js';

export function onRequestGet({ env }) {
  return health(env);
}
