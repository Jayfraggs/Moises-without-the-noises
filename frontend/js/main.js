/** Native-module entry point. The existing vanilla app owns the full studio UI. */
import './app.js';

export function init() {
  return window._mwtn;
}
