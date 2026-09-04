const test = require("node:test");
const assert = require("node:assert/strict");
const {EditorState, move, removeWork, references} = require("../app/static/js/showcase-state.js");
const draft = () => ({nickname:"甲",card:{featured_work:"b",background:{image:"photo"}},page:{modules:[]},content:{avatar:"avatar",cover:"cover",works:[{id:"a",image:"a-image"},{id:"b",image:"b-image"}],gallery:[]}});
const state = () => new EditorState({revision:1,draft:draft(),published:false,assets:[]});
test("editing cannot mutate saved draft or immutable request snapshot",()=>{
  const s=state(), snapshot=s.snapshot();s.set("nickname","乙");
  assert.equal(snapshot.design.nickname,"甲");assert.equal(s.server.draft.nickname,"甲");assert.ok(s.dirty);
});
test("old preview cannot override a newer input",()=>{const s=state(),old=s.snapshot();s.set("nickname","乙");assert.equal(s.acceptPreview(old,"old"),false);assert.equal(s.ticket,"");});
test("reverse-order preview responses ignore obsolete requests",()=>{const s=state(),old=s.snapshot(),latest=s.snapshot();assert.ok(s.acceptPreview(latest,"new"));assert.equal(s.acceptPreview(old,"old"),false);assert.equal(s.ticket,"new");});
test("saving increments revision and invalidates previous preview",()=>{const s=state(),snap=s.snapshot();s.acceptPreview(snap,"ticket");s.acceptSave({revision:2,draft:snap.design},snap);assert.equal(s.revision,2);assert.equal(s.ticket,"");assert.ok(!s.dirty);});
test("late save response cannot erase newer input",()=>{const s=state(),snap=s.snapshot();s.set("nickname","新输入");s.acceptSave({revision:2,draft:snap.design},snap);assert.equal(s.draft.nickname,"新输入");assert.ok(s.dirty);});
test("work ordering preserves the independently selected id",()=>{const d=draft();d.content.works=move(d.content.works,0,1);assert.equal(d.card.featured_work,"b");assert.equal(d.content.works[0].id,"b");});
test("deleting selected work clears selection without fallback",()=>{const d=removeWork(draft(),"b");assert.equal(d.card.featured_work,"");assert.equal(d.content.works.length,1);});
test("deleting a different work retains selection",()=>assert.equal(removeWork(draft(),"a").card.featured_work,"b"));
test("disabled modules retain private references for deletion protection",()=>{const refs=references(draft());assert.ok(refs.has("cover"));assert.ok(refs.has("a-image"));});
test("failed network request leaves state intact",()=>{const s=state();s.set("nickname","未保存内容");const snap=s.snapshot();assert.equal(s.revision,1);assert.equal(s.draft.nickname,snap.design.nickname);assert.ok(s.dirty);});
test("server conflict is never accepted implicitly",()=>{const s=state();s.set("nickname","本地");const remote={revision:8,draft:draft()};assert.equal(s.revision,1);s.load(remote);assert.equal(s.revision,8);assert.equal(s.draft.nickname,"甲");assert.ok(!s.dirty);});
