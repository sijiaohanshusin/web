/* ============================================================
   3D 会标：把矢量会标做成可交互的电路板实体
   ------------------------------------------------------------
   几何来源是页面里已经内联的那份 SVG（app/static/brand/logo-mark.svg），
   不在这里重写任何坐标 —— 会标只有一份几何，改 SVG 这里自动跟着变，
   而且 3D 与 WebGL 不可用时的 SVG 兜底形态永远是同一个形状。

   材质叙事照着真实 PCB 来：
     阻焊墨绿基板 + 白色丝印  →  --solder-mask / --silk
     铜箔走线（金属，粗糙度低）→  --copper
     沉金焊盘环（更亮更黄）    →  --pad-gold
   信号脉冲沿走线按 data-esta-order 的顺序流动：
     pad-in → trunk-in → pad-mid → (spiral ∥ trunk-out) → pad-out
   这个顺序写在 SVG 属性里，不是硬编码在这里。

   为什么走线用「线段盒 + 圆柱接头」而不是沿路径扫掠：
   会标有多个 90° 直角，ExtrudeGeometry 的 extrudePath 在这种拐角会出现
   截面挤压和法线翻转（Frenet 框架突变）。逐段拼盒子、拐角补圆柱，几何
   完全可控，还天然对应 SVG 的 round linejoin/linecap。多边形数只有几千，
   代价可以忽略。

   用法（页面侧）：
       const handle = await mountLogo3D(container, { source: '[data-esta-logo]' });
       handle.setPulse(0.4);      // 手动定位脉冲头（滚动分镜用）
       handle.emitPulse();        // 从入口焊盘打一发
       handle.destroy();          // 释放显存

   生命周期：离开视口/切后台自动停帧；destroy 时 dispose 全部几何、材质、
   贴图并主动丢弃 WebGL 上下文。移动端不降级效果，只按 caps.dpr 限制像素比。
   ============================================================ */

import * as THREE from "three";
import { SVGLoader } from "three/addons/loaders/SVGLoader.js";


/* ------------------------------------------------------------------
   设计常量。颜色取自 tokens.css，改令牌时这里要同步。
   ------------------------------------------------------------------ */
const COLOR = {
    copper: 0xd89a4a,       // --copper 提亮：金属的 color 就是反射率，
                            // 用 #c98a3d 原值经 ACES 映射后偏暗成暗青铜
    padGold: 0xf0c87a,      // --pad-gold 同理提亮
    // 基板用 --solder-mask-2 而不是 --solder-mask：后者 #0a2f2a 太暗，
    // 在纯黑页面上经色调映射直接压成黑色，「阻焊绿」这个身份读不出来
    mask: 0x11463c,
    // 基板 FR-4 用深石墨而不是真实的米黄色：米黄跟信号青/焊锡铜放一起
    // 会抢注意力，且与站点纯黑基调冲突。层次靠明度和粗糙度区分就够。
    substrate: 0x14181d,
    signal: 0x41d8e8,       // --accent-2
    silk: 0xe9edf4,         // --silk
};

// 厚度单位与 SVG 坐标一致（viewBox 216），最后统一缩放
// 层厚。真实 PCB 的铜箔只有 35µm、阻焊约 25µm，按真实比例在屏幕上根本看不见，
// 所以这里按"能吃住光、能拆得开"来夸张，但保持自下而上的层序不变。
const COPPER_THICKNESS = 5.5;
const PAD_THICKNESS = 7.0;      // 焊盘环比走线略厚，符合沉金工艺的观感
const SUBSTRATE_THICKNESS = 12; // 基板 FR-4
const MASK_THICKNESS = 2.4;     // 阻焊层
// 基板比图形外扩多少。要留够一圈「没有铜」的空白给丝印落字 —— 真实板子也必须
// 留边缘 keepout。原来是 16，字压在走线上被 silk clipping 咬掉半截。
// 顺带让板子不那么局促：外扩太小时最外圈走线几乎贴着板边。
const BOARD_PAD = 28;
const EXPLODE_SPAN = 40;        // 解构时层间的最大间距（SVG 坐标单位）
// 解构时层还要侧向错开。纯 Z 向分离在接近正面的视角下完全看不出来（Z 轴几乎
// 指向观察方向），而为了看清分离就得把模型转到侧面，会标图形又认不出了。
// 技术爆炸图的通用解法：叠加一个侧向错位，让每一层的轮廓都露出来。
// 0.62 是实测选出来的：更小的话阻焊层与铜箔重叠过多，会把铜染成橄榄色；
// 更大的话各层散得太开，看不出它们本是一块板。
const EXPLODE_LATERAL = 0.62;
// 阻焊层不透明度：合体时几乎透明（让铜箔可读），拆开后也只到半透 ——
// 拆开后若接近实心，它会把身后的铜箔层整个挡住，解构就白拆了。
const MASK_OPACITY = { assembled: 0.12, exploded: 0.52 };

const VIEWBOX = 216;
const CAP_SEGMENTS = 14;        // 走线两端圆帽的分段数
const CURVE_DIVISIONS = 26;     // 二次贝塞尔离散精度

/* ==================================================================
   SVG → 几何
   ================================================================== */

/**
 * 单点的 SVG → 场景变换，与 applyMapping 用的是同一个矩阵，只是作用在点上。
 * 给「几何在原点、位置靠 mesh.position」的物体用（焊盘、挂绳过孔）。
 * 传入的 y 必须是 parseLogo 已经取反过的那个值。
 */
function svgPointToScene(x, y, map) {
    return new THREE.Vector3(
        (x - VIEWBOX / 2) * map.scale,
        (y + VIEWBOX / 2) * map.scale,
        0,
    );
}

/** 归一化比例：把 216 的 viewBox 映射到约 1 个场景单位。 */
function makeMapper() {
    return { scale: 1 / VIEWBOX };
}

/** 折线总长与累积长度表，用于计算每个顶点的弧长位置。 */
function arcTable(points) {
    const acc = [0];
    let total = 0;
    for (let i = 1; i < points.length; i++) {
        total += points[i].distanceTo(points[i - 1]);
        acc.push(total);
    }
    return { acc, total };
}

/**
 * 沿折线挤出一条有厚度的走线：顶面 + 底面 + 两侧壁 + 两端圆帽，一个 mesh 搞定。
 *
 * 为什么不用「线段盒 + 每个顶点补圆柱」那种堆法：贝塞尔圆角被离散成
 * CURVE_DIVISIONS 段后，段长远小于线宽，于是相邻圆柱之间、圆柱与线段盒之间
 * 大面积重叠，而它们的顶面全部落在同一个 z 上 —— 共面重叠就是深度测试打平手，
 * 渲染出来是一片麻点状 z-fighting。放大截图看 trunk-in 的圆角非常明显。
 * 偏移带没有任何自重叠，顺带把三角形数砍掉一多半。
 *
 * 会标里最大的单顶点转角只有 45°（内框斜切），斜接长度系数 1/cos(22.5°)≈1.08，
 * 所以直接斜接就够，不必做尖角截断（miter limit）。
 */
function buildTraceGeometry(points, strokeWidth, thickness) {
    const halfW = strokeWidth / 2;
    const halfT = thickness / 2;
    const n = points.length;

    // 每个顶点的横向单位法线（指向左侧）+ 斜接放大系数
    const nrm = [];
    const widen = [];
    for (let i = 0; i < n; i++) {
        const prev = i > 0 ? points[i].clone().sub(points[i - 1]).normalize() : null;
        const next = i < n - 1 ? points[i + 1].clone().sub(points[i]).normalize() : null;
        let dir;
        let k = 1;
        if (prev && next) {
            dir = prev.clone().add(next);
            if (dir.lengthSq() < 1e-9) dir = next.clone();      // 180° 折返的退化保护
            else {
                dir.normalize();
                k = 1 / Math.max(0.35, dir.dot(next));          // 0.35 兜住极端锐角
            }
        } else {
            dir = (next || prev).clone();
        }
        nrm.push(new THREE.Vector2(-dir.y, dir.x));
        widen.push(k);
    }
    const left = points.map((p, i) => p.clone().addScaledVector(nrm[i], halfW * widen[i]));
    const right = points.map((p, i) => p.clone().addScaledVector(nrm[i], -halfW * widen[i]));

    const pos = [];
    const nor = [];
    const idx = [];
    /** 压一个顶点，返回它的下标 */
    const vert = (x, y, z, nx, ny, nz) => {
        const i = pos.length / 3;
        pos.push(x, y, z);
        nor.push(nx, ny, nz);
        return i;
    };
    /** 压一个四边形，四个顶点须按逆时针给（法线朝观察者） */
    const quad = (a, b, c, d) => idx.push(a, b, c, a, c, d);

    /* 顶面法线刻意不取 (0,0,1)，而是朝各自那一侧外倾 CROWN。
       原因：正面视角下一个完全平的金属面，反射方向几乎只采到环境贴图的一个点，
       整条走线是一块均匀的死色，像刷上去的漆而不是金属。让法线沿宽度方向张开，
       走线上就有一道横向的明暗渐变 —— 真实电镀铜箔的截面本来也是拱起的。
       只改法线，不加几何。0.26 是实测的分寸：再大就从"平铜箔"变成"弯折的金线"，
       这段叙事讲的是电路板，不是首饰。 */
    const CROWN = 0.26;
    const inv = 1 / Math.hypot(CROWN, 1);
    const crownL = (i) => [nrm[i].x * CROWN * inv, nrm[i].y * CROWN * inv, inv];
    const crownR = (i) => [-nrm[i].x * CROWN * inv, -nrm[i].y * CROWN * inv, inv];
    const flat = [0, 0, 1];
    const wallL = (i) => [nrm[i].x, nrm[i].y, 0];
    const wallR = (i) => [-nrm[i].x, -nrm[i].y, 0];

    const at = (p, z, nv) => vert(p.x, p.y, z, nv[0], nv[1], nv[2]);

    for (let i = 0; i < n - 1; i++) {
        const j = i + 1;
        // 顶面沿中线切成两条。不是为了造型（中线法线正好等于线性插值的结果，
        // 明暗完全不变），而是为了把四边形的对角线缩短一半：细长四边形拆成两个
        // 三角形后，两侧的法线插值梯度不同，会沿对角线留下一道可见的折痕。
        quad(at(right[i], halfT, crownR(i)), at(right[j], halfT, crownR(j)),
             at(points[j], halfT, flat), at(points[i], halfT, flat));
        quad(at(points[i], halfT, flat), at(points[j], halfT, flat),
             at(left[j], halfT, crownL(j)), at(left[i], halfT, crownL(i)));
        // 底面（朝下，绕向与顶面相反）
        const dn = [0, 0, -1];
        quad(at(right[i], -halfT, dn), at(left[i], -halfT, dn),
             at(left[j], -halfT, dn), at(right[j], -halfT, dn));
        // 两侧壁：掠射光专门打这里，是走线"有厚度"的唯一线索
        quad(at(left[i], halfT, wallL(i)), at(left[j], halfT, wallL(j)),
             at(left[j], -halfT, wallL(j)), at(left[i], -halfT, wallL(i)));
        quad(at(right[i], halfT, wallR(i)), at(right[i], -halfT, wallR(i)),
             at(right[j], -halfT, wallR(j)), at(right[j], halfT, wallR(j)));
    }

    /* 两端的圆帽，对应 SVG 的 stroke-linecap="round"。
       从起点一侧的偏移点出发、按角度递减扫过半圈，正好经过端点的朝外方向。 */
    const cap = (center, fromPoint) => {
        const a0 = Math.atan2(fromPoint.y - center.y, fromPoint.x - center.x);
        const ring = [];
        for (let s = 0; s <= CAP_SEGMENTS; s++) {
            const a = a0 - Math.PI * (s / CAP_SEGMENTS);
            ring.push({ x: center.x + halfW * Math.cos(a), y: center.y + halfW * Math.sin(a),
                        c: Math.cos(a), s: Math.sin(a) });
        }
        const cT = vert(center.x, center.y, halfT, 0, 0, 1);
        const cB = vert(center.x, center.y, -halfT, 0, 0, -1);
        for (let s = 0; s < CAP_SEGMENTS; s++) {
            const p = ring[s];
            const q = ring[s + 1];
            const pc = [p.c * CROWN * inv, p.s * CROWN * inv, inv];
            const qc = [q.c * CROWN * inv, q.s * CROWN * inv, inv];
            // 角度递减即顺时针，所以顶面取 (中心, 后一点, 前一点) 才朝 +Z
            idx.push(cT, vert(q.x, q.y, halfT, qc[0], qc[1], qc[2]),
                     vert(p.x, p.y, halfT, pc[0], pc[1], pc[2]));
            idx.push(cB, vert(p.x, p.y, -halfT, 0, 0, -1),
                     vert(q.x, q.y, -halfT, 0, 0, -1));
            quad(vert(p.x, p.y, halfT, p.c, p.s, 0), vert(q.x, q.y, halfT, q.c, q.s, 0),
                 vert(q.x, q.y, -halfT, q.c, q.s, 0), vert(p.x, p.y, -halfT, p.c, p.s, 0));
        }
    };
    cap(points[0], right[0]);
    cap(points[n - 1], left[n - 1]);

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
    geo.setIndex(idx);
    // 法线是手写的，不要再调 computeVertexNormals —— 那会把上面的拱起抹平
    return geo;
}

/**
 * 环形焊盘：外圆挖内孔再挤出，与 SVG 的 stroke 环等价。
 *
 * 几何以自身圆心为原点，(cx, cy) 交给 mesh.position —— 不要把偏移烘进几何里。
 * 焊盘的「弹出」动画要绕自己的中心缩放；几何若带着 (cx, cy)，缩放就变成沿着
 * 原点到圆心这条向量平移，焊盘会飞出画面。
 */
function buildPadGeometry(r, strokeWidth, thickness) {
    const rOuter = r + strokeWidth / 2;
    const rInner = r - strokeWidth / 2;

    const shape = new THREE.Shape();
    shape.absarc(0, 0, rOuter, 0, Math.PI * 2, false);
    const hole = new THREE.Path();
    hole.absarc(0, 0, rInner, 0, Math.PI * 2, true);
    shape.holes.push(hole);

    const geo = new THREE.ExtrudeGeometry(shape, {
        depth: thickness,
        bevelEnabled: true,
        bevelThickness: thickness * 0.18,
        bevelSize: strokeWidth * 0.1,
        bevelSegments: 2,
        curveSegments: 44,
    });
    geo.translate(0, 0, -thickness / 2);
    return geo;
}

/**
 * 给几何加 aArc 属性：每个顶点在本条走线上的归一化弧长位置。
 * 做法是把顶点投影到折线上取最近点的弧长——这样与几何是怎么拼出来的
 * 完全解耦（盒子、圆柱、以后换别的都行）。
 */
function attachArcAttribute(geometry, points) {
    const { acc, total } = arcTable(points);
    const pos = geometry.attributes.position;
    const arc = new Float32Array(pos.count);

    const ab = new THREE.Vector2();
    const ap = new THREE.Vector2();

    for (let v = 0; v < pos.count; v++) {
        const px = pos.getX(v);
        const py = pos.getY(v);
        let best = Infinity;
        let bestArc = 0;

        for (let i = 1; i < points.length; i++) {
            const a = points[i - 1];
            const b = points[i];
            ab.set(b.x - a.x, b.y - a.y);
            ap.set(px - a.x, py - a.y);
            const lenSq = ab.lengthSq();
            const t = lenSq > 1e-9 ? Math.max(0, Math.min(1, ap.dot(ab) / lenSq)) : 0;
            const qx = a.x + ab.x * t;
            const qy = a.y + ab.y * t;
            const d = (px - qx) ** 2 + (py - qy) ** 2;
            if (d < best) {
                best = d;
                bestArc = acc[i - 1] + Math.sqrt(lenSq) * t;
            }
        }
        arc[v] = total > 0 ? bestArc / total : 0;
    }

    geometry.setAttribute("aArc", new THREE.BufferAttribute(arc, 1));
    geometry.userData.arcLength = total;
    return geometry;
}

/**
 * 解析 SVG，产出走线与焊盘的几何描述。
 * 走线取 subPath 的离散点；焊盘直接读 <circle> 的 cx/cy/r —— SVGLoader 会把
 * circle 转成四段贝塞尔近似，读原始属性比反推更准，而且坐标依然来自 SVG。
 */
function parseLogo(svgText) {
    const loader = new SVGLoader();
    const parsed = loader.parse(svgText);
    const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");

    const traces = [];
    const pads = [];

    for (const shapePath of parsed.paths) {
        const node = shapePath.userData && shapePath.userData.node;
        if (!node) continue;

        const name = node.getAttribute("data-esta-trace");
        const padName = node.getAttribute("data-esta-pad");
        const order = parseInt(node.getAttribute("data-esta-order") || "0", 10);
        // stroke-width 可能写在元素上，也可能继承自 <g> 或 <svg>
        const strokeWidth = inheritedNumber(node, "stroke-width", 10);

        // Y 在这里就取反，而不是靠后面用负缩放翻转整个模型。
        // 负缩放的行列式为负，会一并镜像贴图（丝印文字反着写）并翻转面绕向，
        // 真实踩过这个坑。在源头取反，后续所有变换都保持正定。
        if (padName) {
            pads.push({
                name: padName,
                order,
                cx: parseFloat(node.getAttribute("cx")),
                cy: -parseFloat(node.getAttribute("cy")),
                r: parseFloat(node.getAttribute("r")),
                strokeWidth,
            });
            continue;
        }

        if (!name) continue;
        for (const subPath of shapePath.subPaths) {
            const pts = subPath.getPoints(CURVE_DIVISIONS)
                .map((p) => new THREE.Vector2(p.x, -p.y));
            if (pts.length > 1) traces.push({ name, order, strokeWidth, points: pts });
        }
    }

    if (!traces.length) throw new Error("SVG 里没解析到任何 data-esta-trace 走线");
    if (!pads.length) throw new Error("SVG 里没解析到任何 data-esta-pad 焊盘");

    // 用 DOM 量一下图形外接框，基板尺寸据此决定
    const bbox = measureBBox(traces, pads);
    return { traces, pads, bbox, doc };
}

function inheritedNumber(node, attr, fallback) {
    let el = node;
    while (el && el.getAttribute) {
        const raw = el.getAttribute(attr);
        if (raw !== null && raw !== "") {
            const n = parseFloat(raw);
            if (!Number.isNaN(n)) return n;
        }
        el = el.parentNode;
    }
    return fallback;
}

function measureBBox(traces, pads) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const t of traces) {
        const h = t.strokeWidth / 2;
        for (const p of t.points) {
            minX = Math.min(minX, p.x - h); maxX = Math.max(maxX, p.x + h);
            minY = Math.min(minY, p.y - h); maxY = Math.max(maxY, p.y + h);
        }
    }
    for (const p of pads) {
        const r = p.r + p.strokeWidth / 2;
        minX = Math.min(minX, p.cx - r); maxX = Math.max(maxX, p.cx + r);
        minY = Math.min(minY, p.cy - r); maxY = Math.max(maxY, p.cy + r);
    }
    return { minX, minY, maxX, maxY };
}

/* ==================================================================
   材质：铜箔 + 信号脉冲
   ================================================================== */

/**
 * 铜箔材质。在 MeshStandardMaterial 上注入一段发光计算，保留完整 PBR 光照，
 * 只叠加「信号脉冲」与「悬停高亮」两种自发光。
 *
 * 脉冲是一个沿弧长移动的高斯窗：
 *     glow = exp(-((globalArc - uHead) / uWidth)^2)
 * globalArc 把本条走线的局部弧长映射到整条链路的全局位置，这样多段走线能
 * 接成一条连续的电流，而不是各自闪。
 */
function makeCopperMaterial(color) {
    const material = new THREE.MeshStandardMaterial({
        color,
        metalness: 1.0,
        // 粗糙度压低 + 环境强度拉高：金属材质的观感几乎全靠环境反射，
        // 默认值下铜箔会闷成一块死板的棕色
        roughness: 0.26,
        envMapIntensity: 1.75,
    });

    const uniforms = {
        uHead: { value: -1 },        // 脉冲头的全局位置，负值表示没有脉冲
        uWidth: { value: 0.055 },    // 窄一点更像"一个信号"而不是"一段发光"
        uArcOffset: { value: 0 },
        uArcScale: { value: 1 },
        uHighlight: { value: 0 },    // 悬停高亮 0~1
        uSignal: { value: new THREE.Color(COLOR.signal) },
        // 蚀刻推进：全局弧长超过它的片元直接丢弃，走线就像正在被"长"出来。
        // 复用脉冲那套 aArc 属性，不额外加几何或贴图。1 = 全部显示。
        uReveal: { value: 1 },
    };
    material.userData.uniforms = uniforms;

    material.onBeforeCompile = (shader) => {
        Object.assign(shader.uniforms, uniforms);

        shader.vertexShader = shader.vertexShader
            .replace(
                "#include <common>",
                `#include <common>
                 attribute float aArc;
                 varying float vArc;`
            )
            .replace(
                "#include <begin_vertex>",
                `#include <begin_vertex>
                 vArc = aArc;`
            );

        shader.fragmentShader = shader.fragmentShader
            .replace(
                "#include <common>",
                `#include <common>
                 varying float vArc;
                 uniform float uHead;
                 uniform float uWidth;
                 uniform float uArcOffset;
                 uniform float uArcScale;
                 uniform float uHighlight;
                 uniform float uReveal;
                 uniform vec3 uSignal;`
            )
            // 丢弃要放在光照计算之前，省掉被裁掉片元的着色开销
            .replace(
                "#include <clipping_planes_fragment>",
                `#include <clipping_planes_fragment>
                 float revealArc = uArcOffset + vArc * uArcScale;
                 if (revealArc > uReveal) discard;`
            )
            .replace(
                "#include <dithering_fragment>",
                `#include <dithering_fragment>
                 float globalArc = uArcOffset + vArc * uArcScale;
                 float d = (globalArc - uHead) / uWidth;
                 float pulse = uHead < 0.0 ? 0.0 : exp(-d * d);
                 // 悬停时整条走线微亮，脉冲则是局部强亮
                 float glow = pulse * 1.75 + uHighlight * 0.28;
                 // 蚀刻前沿自带一道热边，像刚被腐蚀出来还发着光
                 float edge = smoothstep(0.03, 0.0, uReveal - globalArc) * step(uReveal, 1.0 - 1e-4);
                 gl_FragColor.rgb += uSignal * (glow + edge * 2.2);`
            );
    };

    return material;
}

/* ==================================================================
   程序化环境贴图与丝印贴图（不引外部 HDR / 图片）
   ================================================================== */

/**
 * 环境贴图：一张竖直渐变（上方冷白、下方近黑，中段掺一点信号青）过 PMREM。
 * 金属材质没有环境贴图会黑得像塑料，而引一张 HDR 又要多传几百 KB，
 * 程序生成正好。
 */
function makeEnvironment(renderer) {
    const size = 256;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");

    const g = ctx.createLinearGradient(0, 0, 0, size);
    g.addColorStop(0.00, "#dfe9f2");
    g.addColorStop(0.32, "#7f97ab");
    g.addColorStop(0.55, "#274b57");
    g.addColorStop(0.78, "#0d1a20");
    g.addColorStop(1.00, "#05070a");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, size, size);

    // 一道柔和的高光带，给金属一个可辨认的反射亮部
    const hl = ctx.createRadialGradient(size * 0.7, size * 0.18, 0, size * 0.7, size * 0.18, size * 0.42);
    hl.addColorStop(0, "rgba(255,255,255,.95)");
    hl.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = hl;
    ctx.fillRect(0, 0, size, size);

    const texture = new THREE.CanvasTexture(canvas);
    texture.mapping = THREE.EquirectangularReflectionMapping;
    texture.colorSpace = THREE.SRGBColorSpace;

    const pmrem = new THREE.PMREMGenerator(renderer);
    // 返回的是 WebGLRenderTarget，不是普通贴图。只 dispose 它的 .texture
    // 释放不掉底层 target，会留下泄漏（实测 destroy 后贴图计数降不到 0）。
    // 所以把整个 target 交给调用方保管与释放。
    const target = pmrem.fromEquirectangular(texture);
    pmrem.dispose();
    texture.dispose();
    return target;
}

/**
 * 丝印贴图：基板上那层白墨。画示波器网格 + 几个元件位号 + 协会英文名，
 * 都是真实 PCB 上会有的东西，也把「示波器网格」这条设计语言带到 3D 里。
 */
function makeSilkTexture(desc) {
    const { planeW, planeH, cx, cy, traces, pads, bbox } = desc;
    const w = 1024;
    const h = Math.max(256, Math.round(w * planeH / planeW));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");

    // SVG 坐标 → 画布像素。丝印片的尺寸是 planeW×planeH、中心在 (cx, cy)，
    // 而 SVG 的 y 在 parseLogo 里已经取反成"向上为正"，画布的 y 向下为正。
    const unit = w / planeW;
    const px = (x) => (x - (cx - planeW / 2)) * unit;
    const py = (y) => ((cy + planeH / 2) - y) * unit;

    // 背景必须是纯黑：这张图是当 alphaMap 用的，通道值直接就是不透明度。
    // 曾经填阻焊绿 #0a2f2a，绿通道 0x2f≈0.18，于是"本该透明"的整片区域有
    // 18% 不透明度，在近白色的丝印材质上糊成一块发白的板子，把会标全遮住。
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, w, h);

    const ink = (a) => `rgba(233,237,244,${a})`;

    // ---- 双层示波器网格，格距比与 --scope-cell / --scope-cell-fine 一致 ----
    const grid = (step, alpha) => {
        ctx.strokeStyle = ink(alpha);
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let x = 0; x <= w; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, h); }
        for (let y = 0; y <= h; y += step) { ctx.moveTo(0, y); ctx.lineTo(w, y); }
        ctx.stroke();
    };
    grid(w / 51.2, 0.09);
    grid(w / 10.24, 0.17);

    /* ---- 四角定位标：十字 + 圆，和站内「空焊盘占位」用的是同一套记号 ----
       定位标贴着板角，文字则从 textInset 起排，两者在横向上分开 —— 否则
       "HEU ESTA" 的首字母和 REV 号会正好压在角标上，糊成一团。 */
    const inset = w * 0.026;
    const textInset = w * 0.058;
    const fiducial = (fx, fy) => {
        const r = w * 0.010;
        ctx.strokeStyle = ink(0.34);
        ctx.lineWidth = Math.max(1.5, w / 460);
        ctx.beginPath();
        ctx.arc(fx, fy, r, 0, Math.PI * 2);
        ctx.moveTo(fx - r * 1.8, fy); ctx.lineTo(fx + r * 1.8, fy);
        ctx.moveTo(fx, fy - r * 1.8); ctx.lineTo(fx, fy + r * 1.8);
        ctx.stroke();
    };
    for (const [fx, fy] of [[inset, inset], [w - inset, inset],
                            [inset, h - inset], [w - inset, h - inset]]) fiducial(fx, fy);

    /* ---- 文字：只放协会自己的东西 ----
       实物卡片的意见是「学校相关的元素另一面已经有了，这面最好都是社团相关的」。
       这块 3D 板对应的就是社团那一面，所以位号 + 协会字标 + 版本，没有校徽校训。
       想换内容只改这个数组，不用碰绘制逻辑。 */
    /* 文字必须落在上下两条「没有铜」的空白带里。最后那一步会把铜的位置抠成
       全透明，压在走线上的字会被咬掉半截 —— 看着像字体渲染坏了。所以这里不写
       死坐标，而是从几何外接框算出空白带，再把字排进去；BOARD_PAD 改了也不用
       跟着调。

       字号按板宽比例给，且不小于 w*0.021：这块板在桌面上只占约 450px，1024
       画布上 17px 的字落到屏幕上不到 7px，糊成一团。丝印不承担阅读功能（正文
       就在旁边的 HTML 里），只需要"读起来像丝印"，所以宁可少写几行、写大一点。 */
    const bandBottom = (bbox.minY - (cy - planeH / 2)) * unit;   // 下空白带高度（px）
    const bandTop = ((cy + planeH / 2) - bbox.maxY) * unit;      // 上空白带高度（px）

    ctx.textBaseline = "alphabetic";
    const subBaseline = h - bandBottom * 0.22;
    ctx.fillStyle = ink(0.88);
    ctx.font = `700 ${Math.round(w * 0.038)}px ui-monospace, Consolas, monospace`;
    ctx.fillText("HEU  ESTA", textInset, subBaseline - bandBottom * 0.28);
    ctx.fillStyle = ink(0.44);
    ctx.font = `500 ${Math.round(w * 0.021)}px ui-monospace, Consolas, monospace`;
    ctx.fillText("ELECTRONIC SCI. & TECH. ASSOC.", textInset, subBaseline);

    ctx.textAlign = "right";
    ctx.fillStyle = ink(0.4);
    ctx.fillText("REV 2026.09", w - textInset, subBaseline);
    ctx.textAlign = "left";

    // "ESTA" 的 ASCII 二进制。实物卡片上会标外圈就是一层 0/1，把这条语言接过来。
    // 这一条是当纹理用的，看不清逐位内容没关系
    ctx.fillStyle = ink(0.28);
    ctx.font = `500 ${Math.round(w * 0.018)}px ui-monospace, Consolas, monospace`;
    ctx.fillText("01000101 01010011 01010100 01000001", textInset, bandTop * 0.62);

    // ---- 位号紧贴各自的焊盘，这才是真实丝印的摆法 ----
    const designators = { in: "J1", mid: "TP1", out: "J2" };
    ctx.fillStyle = ink(0.5);
    ctx.font = `500 ${Math.round(w * 0.019)}px ui-monospace, Consolas, monospace`;
    for (const pad of pads) {
        const label = designators[pad.name];
        if (!label) continue;
        const gap = (pad.r + pad.strokeWidth / 2 + 6) * unit;
        ctx.fillText(label, px(pad.cx) + gap * 0.35, py(pad.cy) - gap * 0.55);
    }

    /* ---- 最后把裸铜的位置抠回纯黑 ----
       真实工艺里丝印不会印在裸露的铜和焊盘上（板厂会自动做 silk clipping）。
       照着做同时解决一个观感问题：这张贴图整片都有网格，不抠掉的话铜箔上
       永远糊着一层白网，合体后铜色发闷 —— 而合体态正是用户看得最久的一帧。
       用纯黑覆盖而不是 destination-out：alphaMap 只看绿通道，黑就是全透明，
       行为确定，不必操心画布的预乘 alpha。 */
    ctx.globalCompositeOperation = "source-over";
    ctx.strokeStyle = "#000";
    ctx.fillStyle = "#000";
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (const t of traces) {
        ctx.lineWidth = (t.strokeWidth + 7) * unit;
        ctx.beginPath();
        t.points.forEach((p, i) => (i ? ctx.lineTo(px(p.x), py(p.y)) : ctx.moveTo(px(p.x), py(p.y))));
        ctx.stroke();
    }
    for (const pad of pads) {
        ctx.beginPath();
        ctx.arc(px(pad.cx), py(pad.cy), (pad.r + pad.strokeWidth / 2 + 4.5) * unit, 0, Math.PI * 2);
        ctx.fill();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 4;
    return texture;
}

/* ==================================================================
   装配
   ================================================================== */

export async function mountLogo3D(container, options = {}) {
    const opts = Object.assign({
        source: "[data-esta-logo]",
        dpr: Math.min(window.devicePixelRatio || 1, 2),
        autoRotate: true,
        idleDelay: 2600,
        // 基板可关：叠在 Hero 的粒子波场上时，悬浮的铜箔走线比一块实心板
        // 更容易和背景融合。关掉后仍保留走线与焊盘的完整 3D。
        showBoard: true,
        onReady: null,
    }, options);

    const svgText = await resolveSource(opts.source);
    const { traces, pads, bbox } = parseLogo(svgText);
    const map = makeMapper();

    /* ---------- 渲染器 ---------- */
    const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
    });
    renderer.setPixelRatio(opts.dpr);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.cssText = "display:block;width:100%;height:100%;touch-action:pan-y";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 20);
    const BASE_Z = 2.72;    // 收紧构图，别留太多空边
    camera.position.set(0, 0, BASE_Z);

    // makeEnvironment 返回的是 WebGLRenderTarget，场景要用它的 .texture，
    // 释放时要 dispose 整个 target（见 makeEnvironment 里的说明）
    const envTarget = makeEnvironment(renderer);
    scene.environment = envTarget.texture;

    /* ---------- 灯光 ----------
       三盏：主光给形体、轮廓光用信号青定调、掠射光专门打走线侧壁。
       第三盏是必要的 —— 正面视角下如果没有近乎平行于板面的光，铜箔的
       厚度和倒角完全不反光，整个图会塌成一张平面贴图。 */
    const key = new THREE.DirectionalLight(0xffffff, 2.8);
    key.position.set(-1.1, 1.5, 2.2);
    scene.add(key);

    const rim = new THREE.DirectionalLight(COLOR.signal, 1.9);
    rim.position.set(1.6, -0.9, -1.1);
    scene.add(rim);

    const graze = new THREE.DirectionalLight(0xfff2dd, 1.5);
    graze.position.set(2.4, 0.45, 0.28);   // 几乎贴着板面横扫
    scene.add(graze);

    scene.add(new THREE.AmbientLight(0xffffff, 0.3));

    /* ---------- 会标本体 ---------- */
    const root = new THREE.Group();
    scene.add(root);

    const disposables = [];
    const traceMeshes = [];
    const padMeshes = [];

    // 脉冲链路：按 data-esta-order 排；spiral 与 trunk-out 都从 pad-mid 出发，
    // 属于并联分支，共享同一段时间窗（电流分流，不是排队）。
    const chain = buildPulseChain(traces, pads);

    for (const trace of traces) {
        const merged = buildTraceGeometry(trace.points, trace.strokeWidth, COPPER_THICKNESS);
        attachArcAttribute(merged, trace.points);

        const material = makeCopperMaterial(COLOR.copper);
        const span = chain.span(trace.name);
        material.userData.uniforms.uArcOffset.value = span.offset;
        material.userData.uniforms.uArcScale.value = span.scale;

        const mesh = new THREE.Mesh(merged, material);
        mesh.userData.traceName = trace.name;
        applyMapping(mesh, map);
        root.add(mesh);
        traceMeshes.push(mesh);
        disposables.push(merged, material);
    }

    const padMaterial = new THREE.MeshStandardMaterial({
        color: COLOR.padGold,
        metalness: 1.0,
        // 别做成镜面。0.16 时焊盘面积又小又像镜子，倾斜角度下正好反射到
        // 环境贴图的暗部，整个变成"黑镜"，看不出是金的。真实沉金是半光泽。
        roughness: 0.30,
        envMapIntensity: 1.5,
        emissive: new THREE.Color(COLOR.signal),
        emissiveIntensity: 0,
    });
    disposables.push(padMaterial);

    for (const pad of pads) {
        const geo = buildPadGeometry(pad.r, pad.strokeWidth, PAD_THICKNESS);
        const mesh = new THREE.Mesh(geo, padMaterial.clone());
        mesh.userData.padName = pad.name;
        mesh.userData.padOrder = pad.order;
        // 这里刻意不走 applyMapping：那个函数把变换烘进 mesh.scale，而焊盘的
        // 弹出动画要动 scale，两者会互相覆盖。曾经就是这样把 1/216 的归一化
        // 比例覆盖成 ~1，焊盘被放大 216 倍飞出视锥，画面上三个焊盘位置只剩
        // 阻焊开窗露出的深色圆饼 —— 看着像「焊盘是黑的」，其实是没渲染。
        mesh.position.copy(svgPointToScene(pad.cx, pad.cy, map));
        mesh.userData.baseScale = map.scale;
        mesh.scale.setScalar(map.scale);
        root.add(mesh);
        padMeshes.push(mesh);
        disposables.push(geo, mesh.material);
    }

    /* ---------- 板层：按真实 PCB 层叠拆开 ----------
       自下而上 基板 → 铜箔 → 阻焊 → 丝印。铜箔（走线与焊盘）在上面已经建好，
       这里补另外三层。分层不只是为了解构动画好看：
       - 阻焊层在焊盘处开窗，这正是真实板子上焊盘裸露、其余覆绿的原因
       - 丝印层是独立的一张透明片，只有白墨的地方不透明
       合起来看是一块完整的板，拆开看是一套工艺。 */
    const layers = [];   // { name, mesh, explodeZ, label }

    if (opts.showBoard) buildBoardStack();

    function buildBoardStack() {
        const boardW = bbox.maxX - bbox.minX + BOARD_PAD * 2;
        const boardH = bbox.maxY - bbox.minY + BOARD_PAD * 2;
        const cx = (bbox.minX + bbox.maxX) / 2;
        const cy = (bbox.minY + bbox.maxY) / 2;
        const copperBottom = -COPPER_THICKNESS / 2;

        // ---- 基板（FR-4）：深石墨色，哑光，是整块板的载体 ----
        const subGeo = roundedBoxGeometry(boardW, boardH, SUBSTRATE_THICKNESS, 14);
        const subMat = new THREE.MeshStandardMaterial({
            color: COLOR.substrate,
            metalness: 0.02,
            roughness: 0.78,
            envMapIntensity: 0.55,
            transparent: true,      // 逐层制造时要淡入，见 setAssembly
        });
        const substrate = new THREE.Mesh(subGeo, subMat);
        substrate.position.set(cx, cy, copperBottom - SUBSTRATE_THICKNESS / 2);
        applyMapping(substrate, map);
        root.add(substrate);
        disposables.push(subGeo, subMat);
        layers.push({ name: "substrate", mesh: substrate, explodeZ: -1.35, label: "基板" });

        // ---- 阻焊层：墨绿，在三个焊盘处开窗 ----
        const maskShape = roundedRectShape(boardW - 4, boardH - 4, 12);
        for (const pad of pads) {
            const hole = new THREE.Path();
            // 开窗比焊盘外径再放一点，真实工艺也留余量
            hole.absarc(pad.cx - cx, pad.cy - cy, pad.r + pad.strokeWidth / 2 + 2.5, 0, Math.PI * 2, true);
            maskShape.holes.push(hole);
        }
        const maskGeo = new THREE.ExtrudeGeometry(maskShape, {
            depth: MASK_THICKNESS,
            bevelEnabled: false,
            curveSegments: 40,
        });
        maskGeo.translate(0, 0, -MASK_THICKNESS / 2);
        const maskMat = new THREE.MeshStandardMaterial({
            color: COLOR.mask,
            metalness: 0.06,
            roughness: 0.42,        // 阻焊是半哑光，不是全哑
            envMapIntensity: 1.1,
            transparent: true,
            // 关键取舍：真实 PCB 的阻焊层会把铜箔盖成绿色幽灵，但我们的会标
            // 是图形不是电路板照片 —— 合体时必须读得出铜箔走线。所以这一层的
            // 不透明度跟解构进度联动：合体只留一层淡绿罩色，拆开后才变实心板。
            // 取值见 setDeconstruct 里的 MASK_OPACITY。
            opacity: MASK_OPACITY.assembled,
            depthWrite: false,      // 半透时不写深度，免得把下面的铜剪掉
        });
        const mask = new THREE.Mesh(maskGeo, maskMat);
        mask.position.set(cx, cy, COPPER_THICKNESS / 2 + MASK_THICKNESS / 2);
        applyMapping(mask, map);
        root.add(mask);
        disposables.push(maskGeo, maskMat);
        layers.push({ name: "mask", mesh: mask, explodeZ: 0.9, label: "阻焊层" });

        // ---- 丝印层：只有白墨处不透明的一张片 ----
        const planeW = boardW - 6;
        const planeH = boardH - 6;
        const silk = makeSilkTexture({ planeW, planeH, cx, cy, traces, pads, bbox });
        disposables.push(silk);
        const silkGeo = new THREE.PlaneGeometry(planeW, planeH);
        const silkMat = new THREE.MeshStandardMaterial({
            color: COLOR.silk,
            alphaMap: silk,         // 贴图当蒙版：黑处透明、白处上墨
            transparent: true,
            metalness: 0,
            roughness: 0.85,
            envMapIntensity: 0.4,
            depthWrite: false,      // 透明片不写深度，避免遮住下层的边缘
        });
        const silkLayer = new THREE.Mesh(silkGeo, silkMat);
        silkLayer.position.set(cx, cy, COPPER_THICKNESS / 2 + MASK_THICKNESS + 0.6);
        applyMapping(silkLayer, map);
        root.add(silkLayer);
        disposables.push(silkGeo, silkMat);
        layers.push({ name: "silk", mesh: silkLayer, explodeZ: 1.85, label: "丝印层" });
    }

    // 铜箔层也参与解构：走线与焊盘一起，位移量为 0（作为参考层留在原处）
    layers.push({
        name: "copper",
        meshes: [...traceMeshes, ...padMeshes],
        explodeZ: 0,
        label: "铜箔走线",
    });

    // 记下每一层的初始位置，解构时以此为基准做偏移
    for (const layer of layers) {
        const list = layer.meshes || [layer.mesh];
        layer.list = list;
        layer.baseX = list.map((m) => m.position.x);
        layer.baseY = list.map((m) => m.position.y);
        layer.baseZ = list.map((m) => m.position.z);
    }

    /* ---------- 交互状态 ---------- */
    const state = {
        targetRot: new THREE.Vector2(0, 0),   // x=pitch, y=yaw
        rot: new THREE.Vector2(0, 0),
        dragging: false,
        lastPointer: new THREE.Vector2(),
        lastInteract: performance.now(),
        // 脉冲的"有没有"用独立标志，不要让 pulseHead 的正负兼职两种含义 ——
        // 曾经用 pulseHead>=0 判断是否推进，结果起跑值 -0.08（让入口焊盘先亮）
        // 永远进不了推进分支，脉冲一动不动。
        pulseActive: false,
        pulseHead: -1,
        pulseSpeed: 0.55,       // 每秒推进的全局弧长比例
        pulseAuto: true,
        pulseGap: 2.2,          // 两发之间的间隔秒数
        pulseIdleAt: 0,
        deconstruct: 0,         // 0 合体 / 1 层层拉开，见 setDeconstruct
        assembly: 1,            // 0 空基板 / 1 完整会标，见 setAssembly
        hovered: null,
        manualPulse: false,     // 被外部 setPulse 接管时不自动跑
    };

    const raycaster = new THREE.Raycaster();
    const pointerNdc = new THREE.Vector2();

    function markInteract() { state.lastInteract = performance.now(); }

    function onPointerDown(e) {
        if (e.target.closest && e.target.closest("a,button")) return;
        state.dragging = true;
        state.lastPointer.set(e.clientX, e.clientY);
        renderer.domElement.setPointerCapture?.(e.pointerId);
        markInteract();
    }

    function onPointerMove(e) {
        const rect = renderer.domElement.getBoundingClientRect();
        pointerNdc.set(
            ((e.clientX - rect.left) / rect.width) * 2 - 1,
            -((e.clientY - rect.top) / rect.height) * 2 + 1
        );

        if (state.dragging) {
            const dx = e.clientX - state.lastPointer.x;
            const dy = e.clientY - state.lastPointer.y;
            state.lastPointer.set(e.clientX, e.clientY);
            state.targetRot.y += dx * 0.0075;
            state.targetRot.x += dy * 0.0055;
            // 限制俯仰，避免转到看不出形状的角度
            state.targetRot.x = Math.max(-0.85, Math.min(0.85, state.targetRot.x));
            markInteract();
        }
        hitTest();
    }

    function onPointerUp(e) {
        state.dragging = false;
        renderer.domElement.releasePointerCapture?.(e.pointerId);
    }

    function onClick(e) {
        if (e.target.closest && e.target.closest("a,button")) return;
        emitPulse();
        markInteract();
    }

    function hitTest() {
        raycaster.setFromCamera(pointerNdc, camera);
        const hit = raycaster.intersectObjects(traceMeshes, false)[0];
        const name = hit ? hit.object.userData.traceName : null;
        if (name === state.hovered) return;
        state.hovered = name;
        for (const mesh of traceMeshes) {
            const u = mesh.material.userData.uniforms;
            u.uHighlight.value = mesh.userData.traceName === name ? 1 : 0;
        }
        container.style.cursor = name ? "grab" : "";
    }

    const el = renderer.domElement;
    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerUp);
    el.addEventListener("pointerleave", () => { state.dragging = false; });
    el.addEventListener("click", onClick);

    /* ---------- 脉冲 ---------- */
    function emitPulse() {
        state.manualPulse = false;
        state.pulseActive = true;
        state.pulseHead = -0.08;    // 起跑点略早于 0，让入口焊盘先亮再送出电流
    }

    function setPulse(t) {
        state.manualPulse = true;
        state.pulseActive = t >= 0;
        state.pulseHead = t;
    }

    /* ---------- 逐层制造（分镜 01 的主叙事）----------
       t=0 只有一块空基板，t=1 是完整的会标。按真实 PCB 工艺顺序加层：
         基板 → 蚀刻铜箔 → 沉金焊盘 → 覆阻焊 → 印丝印

       为什么用"制造过程"而不是"爆炸图"：板层的尺寸有 200 坐标单位，而层间距
       只有几十，爆炸图里各层永远互相重叠，阻焊层会把铜箔染成浑浊的橄榄绿；
       要让层分得开就得拉到很远，那时"它们本是一块板"的意思又没了。这是个
       内在矛盾。改成加法叙事后每层都有干净的独立时刻，而且更贴合"我们真的
       会做板子"这件事。setDeconstruct 保留给交互式轻微拆层用。

       各阶段的时间窗刻意重叠，避免出现"一层完全停住等下一层"的死点。 */
    const STAGE = {
        substrate: [0.00, 0.14],
        copper: [0.10, 0.56],
        pads: [0.46, 0.62],
        mask: [0.58, 0.80],
        silk: [0.78, 0.94],
    };

    /** 把全局进度映射到某阶段的 0~1，并做一次平滑 */
    function stageProgress(t, range) {
        const [a, b] = range;
        const raw = Math.max(0, Math.min(1, (t - a) / (b - a)));
        return raw * raw * (3 - 2 * raw);   // smoothstep
    }

    function setAssembly(t) {
        const p = Math.max(0, Math.min(1, t));
        state.assembly = p;

        const byName = (n) => layers.find((l) => l.name === n);

        // 基板：淡入
        const sub = byName("substrate");
        if (sub) {
            const k = stageProgress(p, STAGE.substrate);
            // 基板保底 0.35 不透明度：滚动分镜钉住后的第一帧若完全空白，
            // 看起来像加载失败。空板本身就是叙事起点，让它一开始就在。
            sub.mesh.material.opacity = 0.35 + 0.65 * k;
            // 不要中途翻 transparent：那会触发着色器重编译（掉帧），
            // 而基板是最后一层，常开 transparent 也不会有排序问题
            sub.mesh.visible = true;
        }

        // 铜箔：沿弧长蚀刻推进，前沿自带热边
        const copperK = stageProgress(p, STAGE.copper);
        for (const mesh of traceMeshes) {
            mesh.material.userData.uniforms.uReveal.value = copperK;
            mesh.visible = copperK > 0.001;
        }

        // 焊盘：逐个弹出（按 data-esta-order 的先后）
        const padK = stageProgress(p, STAGE.pads);
        padMeshes.forEach((mesh, i) => {
            const slot = padMeshes.length > 1 ? i / (padMeshes.length - 1) : 0;
            const local = Math.max(0, Math.min(1, (padK - slot * 0.45) / 0.55));
            mesh.visible = local > 0.001;
            // 轻微 overshoot，落定时有个"压上去"的手感。
            // 必须乘 baseScale：mesh.scale 同时承担 SVG→场景的归一化比例，
            // 直接 setScalar(动画值) 会把它冲掉。
            const s = local < 1 ? 1 + 0.35 * Math.sin(local * Math.PI) : 1;
            const pop = local === 0 ? 0.001 : s * (0.35 + 0.65 * local);
            mesh.scale.setScalar(mesh.userData.baseScale * pop);
        });

        // 阻焊：淡入到合体状态的淡绿罩色
        const mask = byName("mask");
        if (mask) {
            const k = stageProgress(p, STAGE.mask);
            mask.mesh.material.opacity = MASK_OPACITY.assembled * k;
            mask.mesh.visible = k > 0.001;
        }

        // 丝印：最后印上去
        const silk = byName("silk");
        if (silk) {
            const k = stageProgress(p, STAGE.silk);
            silk.mesh.material.opacity = k;
            silk.mesh.visible = k > 0.001;
        }
    }

    /* ---------- 轻微拆层（交互式"拆开看看"用，建议 t ≤ 0.5）----------
       层间距按 explodeZ 加权，符号决定往上还是往下走，铜箔留在原处作为参考层，
       基板下沉、阻焊与丝印上浮，读起来是"从中间打开"。另叠一个侧向错位，
       否则接近正面的视角下 Z 向位移完全看不出来。 */
    function setDeconstruct(t) {
        state.deconstruct = Math.max(0, Math.min(1, t));
        const span = EXPLODE_SPAN * map.scale * state.deconstruct;
        const lateral = span * EXPLODE_LATERAL;
        for (const layer of layers) {
            for (let i = 0; i < layer.list.length; i++) {
                const m = layer.list[i];
                m.position.z = layer.baseZ[i] + span * layer.explodeZ;
                // 侧向错开：往右上方扇出，让每层的边缘都能看见
                m.position.x = layer.baseX[i] + lateral * layer.explodeZ;
                m.position.y = layer.baseY[i] + lateral * layer.explodeZ * 0.72;
            }
        }
        // 阻焊层随拆开逐渐变实：合体时让铜箔透出来，拆开后是一块完整的绿板
        const maskLayer = layers.find((l) => l.name === "mask");
        if (maskLayer && maskLayer.mesh) {
            const k = MASK_OPACITY;
            maskLayer.mesh.material.opacity =
                k.assembled + (k.exploded - k.assembled) * state.deconstruct;
        }

        // 层拉开后整体变高，相机同步后退，否则上下两层会被裁到画外
        camera.position.z = baseCameraZ() * (1 + 0.3 * state.deconstruct);
    }

    function applyPulse() {
        for (const mesh of traceMeshes) {
            mesh.material.userData.uniforms.uHead.value = state.pulseHead;
        }
        // 焊盘在脉冲头经过自己所在位置时点亮
        for (const mesh of padMeshes) {
            const at = chain.padAt(mesh.userData.padName);
            const d = state.pulseHead < 0 ? 9 : Math.abs(state.pulseHead - at) / 0.1;
            mesh.material.emissiveIntensity = Math.exp(-d * d) * 2.4;
        }
    }

    /* ---------- 尺寸 ---------- */
    /** 当前长宽比下的基准机距。竖屏要拉远，否则会标左右被裁。 */
    function baseCameraZ() {
        return camera.aspect < 1 ? BASE_Z / camera.aspect * 0.82 : BASE_Z;
    }

    function resize() {
        const rect = container.getBoundingClientRect();
        const w = Math.max(1, rect.width);
        const h = Math.max(1, rect.height);
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        // 机距同时受长宽比与解构进度影响，统一在这里算，避免两处各写一份
        // 然后互相覆盖（resize 把解构的后退量抹掉过一次）
        camera.position.z = baseCameraZ() * (1 + 0.3 * state.deconstruct);
        camera.updateProjectionMatrix();
    }

    const ro = new ResizeObserver(resize);
    ro.observe(container);
    resize();

    /* ---------- 主循环 ---------- */
    let running = false;
    let rafId = 0;
    let lastFrame = performance.now();

    function frame(now) {
        // dt 必须同时钳上下界。只钳上界会出大事：frame(now) 收到的是 rAF
        // 时间戳，而 lastFrame 初值取自 performance.now()，两者同一时钟但
        // 没有先后保证（rAF 时间戳是该帧起始时刻，可能早于刚才取的值，
        // 页面上多个 WebGL 实例争抢调度时尤其容易）。dt 一旦为负，下面的
        // 阻尼系数就是负的，当前值会朝着远离目标的方向无界发散 ——
        // 实测表现为模型自己转到侧面去。
        const dt = Math.max(0, Math.min(0.05, (now - lastFrame) / 1000));
        lastFrame = now;

        // 空闲自转：没有交互一段时间后缓慢转起来，并轻微俯仰摆动
        if (opts.autoRotate && !state.dragging && now - state.lastInteract > opts.idleDelay) {
            state.targetRot.y += dt * 0.28;
            state.targetRot.x = Math.sin(now / 4200) * 0.16;
        }

        // 阻尼跟随：目标值与当前值指数逼近，手感比直接赋值柔和。
        // 用 1-exp(-dt*k) 而不是 dt*k：前者天然落在 [0,1)，帧率抖动或长帧
        // 都不会越界，也不必再套一层 Math.min。
        const follow = 1 - Math.exp(-dt * 6.5);
        state.rot.x += (state.targetRot.x - state.rot.x) * follow;
        state.rot.y += (state.targetRot.y - state.rot.y) * follow;
        root.rotation.x = state.rot.x;
        root.rotation.y = state.rot.y;

        if (!state.manualPulse) {
            if (state.pulseActive) {
                state.pulseHead += dt * state.pulseSpeed;
                if (state.pulseHead > 1.12) {
                    state.pulseActive = false;
                    state.pulseHead = -1;
                    state.pulseIdleAt = now;
                }
            } else if (state.pulseAuto && now - state.pulseIdleAt > state.pulseGap * 1000) {
                emitPulse();
            }
        }
        applyPulse();

        renderer.render(scene, camera);
        if (running) rafId = requestAnimationFrame(frame);
    }

    function play() {
        if (running) return;
        running = true;
        lastFrame = performance.now();
        rafId = requestAnimationFrame(frame);
    }

    function pause() {
        running = false;
        if (rafId) cancelAnimationFrame(rafId);
        rafId = 0;
    }

    // 离开视口或切后台就停帧：一个常驻的 WebGL 循环在手机上很耗电
    const io = new IntersectionObserver((entries) => {
        entries[0].isIntersecting && !document.hidden ? play() : pause();
    }, { threshold: 0.05 });
    io.observe(container);

    function onVisibility() {
        document.hidden ? pause() : play();
    }
    document.addEventListener("visibilitychange", onVisibility);

    play();
    // 先渲一帧再回调，避免调用方拿到一个还是空白的画布
    renderer.render(scene, camera);
    if (opts.onReady) opts.onReady();

    /* ---------- 释放 ---------- */
    function destroy() {
        pause();
        io.disconnect();
        ro.disconnect();
        document.removeEventListener("visibilitychange", onVisibility);
        el.removeEventListener("pointerdown", onPointerDown);
        el.removeEventListener("pointermove", onPointerMove);
        el.removeEventListener("pointerup", onPointerUp);
        el.removeEventListener("pointercancel", onPointerUp);
        el.removeEventListener("click", onClick);

        for (const d of disposables) d.dispose?.();
        envTarget.dispose();
        renderer.dispose();
        // 显式丢弃上下文：移动端 GPU 的并发上下文数很紧，靠 GC 不够及时
        renderer.forceContextLoss?.();
        if (el.parentNode) el.parentNode.removeChild(el);
    }

    return {
        destroy,
        setPulse,
        emitPulse,
        setDeconstruct,
        setAssembly,
        /** 逐层制造各阶段的时间窗，分镜用它对齐文案出现时机 */
        get assemblyStages() { return { ...STAGE }; },
        /** 层信息，供分镜取标签与顺序（自下而上） */
        get layerInfo() {
            return layers.map((l) => ({ name: l.name, label: l.label, explodeZ: l.explodeZ }));
        },
        /**
         * 设置整体姿态（弧度）。会重置空闲计时，所以不会被自转覆盖。
         *
         * immediate=true 时跳过阻尼直接落位。滚动驱动必须用这个模式：
         * 滚动位置是权威值，再加一层阻尼只会让模型滞后于滚动条，
         * 快速滚动时表现为"追不上"。拖拽与空闲自转才需要阻尼。
         */
        setOrientation(pitch, yaw, immediate) {
            state.targetRot.set(pitch, yaw);
            if (immediate) state.rot.set(pitch, yaw);
            markInteract();
        },
        get object3D() { return root; },
        get renderer() { return renderer; },
        get camera() { return camera; },
        traceMeshes,
        padMeshes,
    };
}

/* ==================================================================
   工具
   ================================================================== */

async function resolveSource(source) {
    if (typeof source === "string" && source.trim().startsWith("<svg")) return source;
    const el = document.querySelector(source);
    if (el) return el.outerHTML;
    // 页面里没有内联 SVG 时才退回网络请求
    if (typeof source === "string" && /\.svg(\?|$)/.test(source)) {
        const resp = await fetch(source);
        if (!resp.ok) throw new Error(`取不到会标 SVG：${source} → HTTP ${resp.status}`);
        return resp.text();
    }
    throw new Error(`找不到会标来源：${source}`);
}

/**
 * SVG 坐标 → 场景坐标：整体等比缩放并居中。
 * Y 轴翻转已经在 parseLogo 里对坐标做掉了，所以这里是正定变换 ——
 * 不镜像贴图、不翻转面绕向。
 */
function applyMapping(mesh, map) {
    const m = new THREE.Matrix4().makeScale(map.scale, map.scale, map.scale);
    m.setPosition(-(VIEWBOX / 2) * map.scale, (VIEWBOX / 2) * map.scale, 0);
    mesh.applyMatrix4(m);
}

/**
 * 脉冲链路：把每条走线映射到 [0,1] 的全局时间窗，让多段走线接成一条连续电流。
 *
 * 分组依据是 SVG 里的 data-esta-order：
 *   order 1 (trunk-in)                独占第一段
 *   order 3 (spiral) 与 4 (trunk-out) 都从 pad-mid 出发，属于并联分支，
 *                                     共享同一段时间窗（电流分流，不是排队）
 * 每段的长度按组内最长走线的弧长加权，这样脉冲的视觉速度大致均匀。
 *
 * 注意：这里返回普通对象而不是给 Map 挂方法。曾经写成 `result = spans` 再
 * `result.get = (n) => spans.get(n)`，把 Map.prototype.get 覆盖成了自我递归，
 * 直接爆栈。方法名与容器不要混在一起。
 */
function buildPulseChain(traces, pads) {
    // 每条走线的两端各归属最近的焊盘，于是「三焊盘 + 三走线」变成一张图，
    // 电流从入口焊盘开始按层推进。同一层的走线是并联分支（真实电路里
    // 电流在节点分流），共享同一段时间窗，而不是排队。
    const nearestPad = (pt) => {
        let best = null;
        let bestD = Infinity;
        for (const p of pads) {
            const d = (p.cx - pt.x) ** 2 + (p.cy - pt.y) ** 2;
            if (d < bestD) { bestD = d; best = p; }
        }
        return best ? best.name : null;
    };

    const edges = traces.map((t) => ({
        name: t.name,
        from: nearestPad(t.points[0]),
        to: nearestPad(t.points[t.points.length - 1]),
        length: arcTable(t.points).total,
    }));

    // 入口焊盘 = data-esta-order 最小的那个（SVG 里是 pad-in / order 0）
    const startPad = [...pads].sort((a, b) => a.order - b.order)[0];
    const start = startPad ? startPad.name : (edges[0] && edges[0].from);

    // 逐层展开
    const visited = new Set();
    const layers = [];
    let frontier = new Set([start]);
    const padReachAt = new Map([[start, 0]]);

    while (frontier.size) {
        const layer = edges.filter((e) => !visited.has(e.name) && frontier.has(e.from));
        if (!layer.length) break;
        layers.push(layer);
        layer.forEach((e) => visited.add(e.name));
        frontier = new Set(layer.map((e) => e.to).filter(Boolean));
    }
    // 图里没连上的走线兜底追加一层，避免它永远不亮
    const orphans = edges.filter((e) => !visited.has(e.name));
    if (orphans.length) layers.push(orphans);

    // 每层的时长按层内最长走线加权，脉冲的视觉速度才大致均匀
    const weights = layers.map((layer) => Math.max(...layer.map((e) => e.length)));
    const sum = weights.reduce((a, b) => a + b, 0) || 1;

    const spans = new Map();
    let cursor = 0;
    layers.forEach((layer, i) => {
        const w = weights[i] / sum;
        for (const e of layer) {
            // 并联分支各自把本条走线的 0~1 映射到同一个时间窗：短的先到，
            // 长的后到，正好是电流分流后到达时间不同的样子
            spans.set(e.name, { offset: cursor, scale: w });
        }
        cursor += w;
        for (const e of layer) {
            if (e.to && !padReachAt.has(e.to)) padReachAt.set(e.to, cursor);
        }
    });

    return {
        span(name) {
            return spans.get(name) || { offset: 0, scale: 1 };
        },
        /** 焊盘在全局时间轴上的位置 */
        padAt(padName) {
            const at = padReachAt.get(padName);
            return at === undefined ? 0.5 : at;
        },
        /** 调试用：暴露分层结果 */
        layers: layers.map((l) => l.map((e) => e.name)),
    };
}

/** 圆角矩形轮廓，供基板与阻焊层共用（阻焊层还要在此基础上挖焊盘开窗）。 */
function roundedRectShape(w, h, radius) {
    const shape = new THREE.Shape();
    const x = -w / 2, y = -h / 2;
    const r = Math.min(radius, w / 2, h / 2);
    shape.moveTo(x + r, y);
    shape.lineTo(x + w - r, y);
    shape.quadraticCurveTo(x + w, y, x + w, y + r);
    shape.lineTo(x + w, y + h - r);
    shape.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    shape.lineTo(x + r, y + h);
    shape.quadraticCurveTo(x, y + h, x, y + h - r);
    shape.lineTo(x, y + r);
    shape.quadraticCurveTo(x, y, x + r, y);
    return shape;
}

/** 圆角长方体：基板边缘不该是刀切的直角。 */
function roundedBoxGeometry(w, h, d, radius) {
    const shape = roundedRectShape(w, h, radius);

    const geo = new THREE.ExtrudeGeometry(shape, {
        depth: d,
        bevelEnabled: true,
        bevelThickness: d * 0.12,
        bevelSize: d * 0.1,
        bevelSegments: 2,
        curveSegments: 8,
    });
    geo.translate(0, 0, -d / 2);
    geo.computeBoundingBox();
    // 丝印贴图按外接框归一化 UV，否则 ExtrudeGeometry 的 UV 不可用
    const bb = geo.boundingBox;
    const uv = geo.attributes.uv;
    const pos = geo.attributes.position;
    for (let i = 0; i < uv.count; i++) {
        uv.setXY(
            i,
            (pos.getX(i) - bb.min.x) / (bb.max.x - bb.min.x),
            (pos.getY(i) - bb.min.y) / (bb.max.y - bb.min.y)
        );
    }
    return geo;
}

export default mountLogo3D;
