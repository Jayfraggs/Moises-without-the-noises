/** Small observable store for framework-free UI modules. */
export const store = {
  _state: {},
  _subs: new Set(),
  get() { return this._state; },
  set(patch) {
    this._state = { ...this._state, ...patch };
    this._subs.forEach((subscriber) => subscriber(this._state));
  },
  subscribe(subscriber) {
    this._subs.add(subscriber);
    return () => this._subs.delete(subscriber);
  },
};
