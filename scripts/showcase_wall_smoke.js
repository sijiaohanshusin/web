/* Dependency-free regression checks for asynchronous filters and motion cleanup. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/showcase-wall.js', 'utf8');
function target(extra = {}) {
    const events = {};
    return Object.assign({events, addEventListener(name, fn) { events[name] = fn; }}, extra);
}
function setup(reduce = false, empty = false) {
    const requests = [], timers = new Map(), animations = [], observers = [];
    let nextTimer = 0, result, hydrated = 0;
    const q = target({value:''});
    const form = target({action:'https://example.test/team/', elements:{q}});
    for (const key of ['cohort','direction','position','sort']) form.elements[key] = {value:key === 'sort' ? 'cohort_desc' : ''};
    const makeResult = count => ({dataset:{count:String(count)}, busy:false, cards:[{isConnected:true}],
        querySelectorAll() { return this.cards; }, setAttribute() { this.busy = true; },
        removeAttribute() { this.busy = false; }, replaceWith(other) { result = other; }, focus() {},
    });
    result = makeResult(6);
    const heading = {isConnected:true};
    const wall = target({querySelector() { return form; }, querySelectorAll() { return result.cards; }});
    const feedback = {textContent:'', children:[], replaceChildren(...children) { this.children = children; }, append(...children) { this.children.push(...children); }};
    const count = {textContent:'6'};
    const reduced = target({matches:reduce});
    const location = {href:'https://example.test/team/'};
    const motion = {EASE:{rise:'ease'}, scene(name, fn) { fn(); },
        once(card, fn) { const observer = {disconnected:false, disconnect() { this.disconnected = true; }}; observers.push(observer); fn(); return observer; },
        gsap:{fromTo(node) { animations.push(node); }, killTweensOf(node) { node.killed = true; }, set(node) { node.cleared = true; }},
    };
    const originalQuery = wall.querySelector;
    wall.querySelector = selector => selector === '.sc-wall-heading' ? heading : empty ? null : originalQuery();
    const win = target({ESTA:{motion, hydrateImageFades() { hydrated++; }}});
    const context = {window:win, location, URL, URLSearchParams, AbortController,
        document:{getElementById(id) { return {'member-wall':wall,'filter-feedback':feedback,'member-results':result,'member-count':count}[id]; },
            createTextNode: value => value, createElement: () => ({})},
        matchMedia:() => reduced,
        FormData:class { constructor() { return Object.entries(form.elements).map(([key, input]) => [key,input.value]); } },
        DOMParser:class { parseFromString(text) { return {getElementById:() => makeResult(Number(text))}; } },
        history:{pushState(state, title, url) { location.href = url.href; }},
        setTimeout(fn) { timers.set(++nextTimer,fn); return nextTimer; }, clearTimeout(id) { timers.delete(id); },
        fetch(url, options) { return new Promise((resolve,reject) => requests.push({url,options,resolve,reject})); },
    };
    vm.runInNewContext(source,context);
    const flush = async () => { for (let i=0; i<10; i++) await Promise.resolve(); };
    return {form,q,requests,reduced,win,feedback,count,location,animations,observers,
        get result() { return result; }, get hydrated() { return hydrated; },
        input(value) { q.value=value; q.events.input(); },
        tick() { for (const fn of [...timers.values()]) fn(); timers.clear(); },
        async answer(index, number) { requests[index].resolve({ok:true, text:async () => String(number)}); await flush(); }, flush,
    };
}
(async () => {
    const empty = setup(false, true);
    assert.equal(empty.requests.length, 0, 'empty wall initializes without a search form');
    let env = setup();
    env.input('old'); env.tick();
    env.input('new');
    assert.equal(env.requests[0].options.signal.aborted,true);
    await env.answer(0,99);
    assert.equal(env.count.textContent,'6', 'stale result cannot win inside debounce window');
    env.tick(); await env.answer(1,2);
    assert.equal(env.count.textContent,'2');
    assert.equal(new URL(env.location.href).searchParams.get('q'),'new');
    assert.equal(env.result.busy,false);
    assert.equal(env.hydrated,2, 'new results reinitialize image loading');

    env = setup(); env.q.events.compositionstart(); env.input('lin'); env.tick();
    assert.equal(env.requests.length,0, 'IME intermediate input must not search');
    env.q.value='林'; env.q.events.compositionend(); env.tick(); await env.answer(0,1);
    assert.equal(new URL(env.location.href).searchParams.get('q'),'林');
    env.location.href='https://example.test/team/?direction=software&sort=cohort_asc';
    env.win.events.popstate(); await env.answer(1,3);
    assert.equal(env.form.elements.direction.value,'software');
    assert.equal(env.form.elements.sort.value,'cohort_asc');
    assert.equal(env.count.textContent,'3');

    env = setup(); env.input('retry'); env.tick(); env.requests[0].reject(new Error('offline')); await env.flush();
    assert.equal(env.count.textContent,'6');
    assert.equal(env.result.busy,false);
    assert.equal(env.feedback.children.at(-1).href,'https://example.test/team/?q=retry');

    env = setup(true);
    assert.equal(env.animations.length,0);
    assert.equal(env.hydrated,1, 'reduced motion still loads images');
    env = setup(); env.reduced.matches=true; env.reduced.events.change();
    assert.ok(env.animations.every(node => node.killed && node.cleared));
    assert.ok(env.observers.every(observer => observer.disconnected));
    console.log('PASS: race cancellation, IME, history, failure fallback, image hydration, reduced motion');
})().catch(error => { console.error(error); process.exitCode=1; });
