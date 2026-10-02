/* Signal sea: one GPU draw call, original Canvas rendering as a fallback.
   Begins after the opening; pauses while offscreen or the tab is hidden. */
(function () {
    "use strict";
    var canvas = document.getElementById("hero-canvas");
    var hero = document.getElementById("nf-hero");
    if (!canvas || !hero) return;
    var fallbackUrl = document.currentScript && document.currentScript.dataset.fallbackSrc;
    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function fallback(error) {
        if(error && window.console) console.warn("[signal-field] Canvas fallback", String(error));
        var replacement = canvas.cloneNode(false);
        canvas.replaceWith(replacement);
        if (fallbackUrl) { var script = document.createElement("script"); script.src = fallbackUrl; document.head.appendChild(script); }
    }
    if (reduced) { fallback(); return; }
    var ready = window.ESTA && window.ESTA.preload ? window.ESTA.preload.done : Promise.resolve();
    // Let the curtain transition finish and navigation paint before allocating
    // a GPU context. All points and interactions still use the full GPU scene.
    ready.then(function () { return new Promise(function(resolve){ setTimeout(resolve, 1100); }); })
    .then(function () { return import("three"); }).then(function (THREE) {
        var renderer;
        try { renderer = new THREE.WebGLRenderer({canvas: canvas, alpha: true, antialias: false, powerPreference: "low-power"}); }
        catch (error) { fallback(error); return; }
        canvas.dataset.renderer = "gpu";
        var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
        renderer.setPixelRatio(dpr);
        var uniforms = { uTime: {value: 0}, uSize: {value: new THREE.Vector2()}, uDpr: {value: dpr},
            uPointer: {value: new THREE.Vector2(-9999, -9999)},
            uShocks: {value: Array.from({length: 5}, function () { return new THREE.Vector3(-9999, -9999, -100); })} };
        var material = new THREE.ShaderMaterial({transparent: true, depthTest: false, depthWrite: false,
            blending: THREE.AdditiveBlending, uniforms: uniforms,
            vertexShader: `
                uniform float uTime; uniform vec2 uSize; uniform float uDpr;
                uniform vec2 uPointer; uniform vec3 uShocks[5];
                varying float vAlpha; varying float vHot;
                void main() {
                    float x=position.x, z=position.y, t=uTime;
                    float y=34.0*sin(x*.0021+t*.9+z*.0012)+22.0*sin(z*.004-t*.65)
                        +14.0*sin((x*.55+z)*.0035+t*1.35)+7.0*sin(x*.008-t*.5);
                    float pulseZ=1500.0-mod(t,6.5)/6.5*1690.0;
                    float pulse=exp(-pow(z-pulseZ,2.0)/(2.0*130.0*130.0)); y+=pulse*26.0;
                    float scale=max(uSize.x*.36,300.0)/z;
                    vec2 screen=vec2(uSize.x*.5+x*scale,uSize.y*.34+(150.0-y)*scale);
                    float fade=clamp(1.25-z/1500.0*1.35,0.0,1.0);
                    float boost=exp(-dot(screen-uPointer,screen-uPointer)/(2.0*78.0*78.0));
                    screen.y-=boost*16.0;
                    float alpha=.05+fade*.34+pulse*.42+boost*.55;
                    for(int i=0;i<5;i++) {
                        float age=t-uShocks[i].z;
                        if(age>=0.0 && age<1.8) {
                            float dist=distance(screen,uShocks[i].xy);
                            float band=exp(-pow(dist-age*620.0,2.0)/(2.0*46.0*46.0))*(1.0-age/1.8);
                            screen.y-=band*22.0; alpha+=band*.8;
                        }
                    }
                    vAlpha=min(alpha,.95); vHot=clamp(pulse*.7+boost,0.0,1.0);
                    gl_Position=vec4(screen.x/uSize.x*2.0-1.0,1.0-screen.y/uSize.y*2.0,0.0,1.0);
                    gl_PointSize=(.8+fade*1.8)*(1.0+pulse*.8+boost*.7)*4.0*uDpr;
                }`,
            fragmentShader: `
                varying float vAlpha; varying float vHot;
                void main() {
                    float r=length(gl_PointCoord-vec2(.5))*2.0;
                    if(r>1.0) discard;
                    float glow=r<.28 ? mix(1.0,.55,r/.28) : .55*(1.0-(r-.28)/.72);
                    vec3 color=mix(vec3(.255,.847,.91),vec3(.92,.97,1.0),vHot*max(0.0,1.0-r*2.0));
                    gl_FragColor=vec4(color,glow*vAlpha);
                }`});
        var scene=new THREE.Scene(), camera=new THREE.Camera(), geometry=new THREE.BufferGeometry();
        var points=new THREE.Points(geometry,material);points.frustumCulled=false;scene.add(points);
        function resize() {
            var w=hero.clientWidth, h=hero.clientHeight;
            if (!w || !h) return;
            uniforms.uSize.value.set(w,h);renderer.setSize(w,h,false);
            var cols=w>900?128:84, rows=w>900?52:38, data=new Float32Array(cols*rows*3), index=0;
            for(var iz=0;iz<rows;iz++) for(var ix=0;ix<cols;ix++) {
                data[index++]=(ix/(cols-1)-.5)*w*3.6;
                data[index++]=110+(1500-110)*Math.pow(iz/(rows-1),1.55);data[index++]=0;
            }
            geometry.setAttribute('position',new THREE.BufferAttribute(data,3));
            renderer.render(scene,camera);
        }
        var raf=0, visible=true, start=performance.now(), slot=0;
        function frame(now) { raf=0;uniforms.uTime.value=(now-start)/1000;renderer.render(scene,camera);if(visible&&!document.hidden&&!reduced)raf=requestAnimationFrame(frame); }
        function sync() { if(raf)cancelAnimationFrame(raf);raf=0;if(visible&&!document.hidden&&!reduced)raf=requestAnimationFrame(frame); }
        resize();
        var observer=new IntersectionObserver(function(entries){visible=entries[0].isIntersecting;sync();});observer.observe(hero);
        document.addEventListener('visibilitychange',sync);
        window.addEventListener('resize',resize);
        if(window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
            hero.addEventListener('pointermove',function(e){var r=canvas.getBoundingClientRect();uniforms.uPointer.value.set(e.clientX-r.left,e.clientY-r.top);});
            hero.addEventListener('pointerleave',function(){uniforms.uPointer.value.set(-9999,-9999);});
        }
        hero.addEventListener('pointerdown',function(e){if(e.target.closest('a,button'))return;var r=canvas.getBoundingClientRect();uniforms.uShocks.value[slot++%5].set(e.clientX-r.left,e.clientY-r.top,uniforms.uTime.value);});
        canvas.addEventListener('webglcontextlost',function(e){e.preventDefault();visible=false;sync();});
        canvas.addEventListener('webglcontextrestored',function(){visible=true;resize();sync();});
    }).catch(fallback);
})();
