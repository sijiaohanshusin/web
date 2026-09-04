/* Shared, DOM-free editing rules; also exercised by the race-condition tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ShowcaseState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const clone = value => JSON.parse(JSON.stringify(value));
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  class EditorState {
    constructor(server) {
      this.server = clone(server);
      this.draft = clone(server.draft);
      this.generation = 0;
      this.sequence = 0;
      this.busy = false;
      this.ticket = "";
    }
    get revision() { return this.server.revision; }
    get dirty() { return !equal(this.draft, this.server.draft); }
    touch() { this.generation++; this.sequence++; this.ticket = ""; }
    set(path, value) {
      const parts = path.split(".");
      let object = this.draft;
      for (const key of parts.slice(0, -1)) object = object[key];
      if (!equal(object[parts.at(-1)], value)) { object[parts.at(-1)] = clone(value); this.touch(); }
    }
    snapshot() { return Object.freeze({ design: clone(this.draft), revision: this.revision, generation: this.generation, sequence: ++this.sequence }); }
    isCurrent(snapshot) { return snapshot.generation === this.generation && snapshot.revision === this.revision && snapshot.sequence === this.sequence; }
    acceptPreview(snapshot, ticket) {
      if (!this.isCurrent(snapshot)) return false;
      this.ticket = ticket || "";
      return true;
    }
    acceptSave(server, snapshot) {
      this.server = clone(server);
      if (snapshot.generation === this.generation) this.draft = clone(server.draft);
      this.touch();
    }
    load(server) { this.server = clone(server); this.draft = clone(server.draft); this.touch(); }
  }
  function move(array, index, target) {
    if (index < 0 || target < 0 || index >= array.length || target >= array.length) return array.slice();
    const result = array.slice();
    result.splice(target, 0, result.splice(index, 1)[0]);
    return result;
  }
  function removeWork(design, id) {
    const result = clone(design);
    result.content.works = result.content.works.filter(work => work.id !== id);
    if (result.card.featured_work === id) result.card.featured_work = "";
    return result;
  }
  function references(design) {
    const c = design.content;
    return new Set([c.avatar, c.cover, design.card.background.image, ...c.works.map(w => w.image), ...c.gallery.map(g => g.image)].filter(Boolean));
  }
  return { EditorState, clone, equal, move, removeWork, references };
});
