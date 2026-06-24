// thanatos_intro.js — Cinematic site intro for thanatos.agency
// Vanilla JS, drop into thanatos_intel/public/js/, register via hooks.py:web_include_js
// Plays once per visitor (localStorage gate), dissolves into the existing hero.
// Force replay: append ?intro=1 to the URL; or click the "Replay intro" button.
//
// Brand aligned to thanatos_web.css: --gold:#C8A96E, --gold2:#E0C58A, --navy:#0A0E1A
//
// Author: design handoff — port of the React prototype (see design_handoff_thanatos_intro/intro.jsx)

(function () {
  if (typeof window === 'undefined') return;
  const STORAGE_KEY = 'thanatos_intro_seen';

  // ── gating ───────────────────────────────────────────────
  function shouldPlay() {
    try {
      if (location.search.indexOf('intro=1') !== -1) return true;
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
      if (localStorage.getItem(STORAGE_KEY) === '1') return false;
    } catch (e) {}
    // Only the home (body.thanatos-home set by www/index.py)
    if (!document.body || !document.body.classList.contains('thanatos-home')) return false;
    return true;
  }

  // ── math helpers ─────────────────────────────────────────
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const smoothstep = (e0, e1, x) => {
    const t = clamp((x - e0) / (e1 - e0), 0, 1);
    return t * t * (3 - 2 * t);
  };
  const ease = {
    outCubic: (t) => 1 - Math.pow(1 - t, 3),
    outQuart: (t) => 1 - Math.pow(1 - t, 4),
    inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  };

  // ── brand ────────────────────────────────────────────────
  const GOLD = '#C8A96E';
  const GOLD_BRIGHT = '#E0C58A';
  const GOLD_RGB = '200,169,110';
  const GOLD_BRIGHT_RGB = '224,197,138';

  // ── geometry (logical 1920×1080) ─────────────────────────
  const W = 1920, H = 1080;
  const CX = W / 2;
  const LOGO_Y = 460;
  const INTRO_DURATION = 12.5;
  const TRANSITION_START = 10.5;
  const TRANSITION_END = 12.0;

  // ── stable seeded RNG ────────────────────────────────────
  function seeded(seed) {
    let s = seed;
    return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  }

  // ─────────────────────────────────────────────────────────
  // AUDIO ENGINE
  // ─────────────────────────────────────────────────────────
  class AudioEngine {
    constructor() {
      this.ctx = null; this.master = null; this.muted = false; this.drone = null;
    }
    init() {
      if (this.ctx) return true;
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return false;
        this.ctx = new AC();
        this.master = this.ctx.createGain();
        this.master.gain.value = this.muted ? 0 : 0.85;
        this.master.connect(this.ctx.destination);
        return true;
      } catch (e) { return false; }
    }
    async resume() {
      if (!this.init()) return false;
      try { if (this.ctx.state !== 'running') await this.ctx.resume(); return this.ctx.state === 'running'; }
      catch (e) { return false; }
    }
    setMuted(m) {
      this.muted = m;
      if (this.master) {
        this.master.gain.cancelScheduledValues(this.ctx.currentTime);
        this.master.gain.linearRampToValueAtTime(m ? 0 : 0.85, this.ctx.currentTime + 0.08);
      }
    }
    now() { return this.ctx.currentTime; }
    makeNoise(seconds) {
      const sr = this.ctx.sampleRate;
      const buf = this.ctx.createBuffer(1, sr * seconds, sr);
      const d = buf.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      const src = this.ctx.createBufferSource();
      src.buffer = buf; src.loop = true; return src;
    }
    startDrone() {
      if (!this.ctx || this.drone) return;
      const t0 = this.now(), c = this.ctx;
      const out = c.createGain();
      out.gain.value = 0.0001;
      out.gain.exponentialRampToValueAtTime(0.22, t0 + 2.5);
      const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 320; lp.Q.value = 0.7;
      out.connect(lp); lp.connect(this.master);
      const sub = c.createOscillator(); sub.type = 'sine'; sub.frequency.value = 55;
      const subG = c.createGain(); subG.gain.value = 1.0; sub.connect(subG); subG.connect(out);
      const bass = c.createOscillator(); bass.type = 'sine'; bass.frequency.value = 110;
      const bassG = c.createGain(); bassG.gain.value = 0.4;
      const lfo = c.createOscillator(); lfo.frequency.value = 0.18;
      const lfoG = c.createGain(); lfoG.gain.value = 4; lfo.connect(lfoG); lfoG.connect(bass.frequency);
      bass.connect(bassG); bassG.connect(out);
      const noise = this.makeNoise(2);
      const noiseLp = c.createBiquadFilter(); noiseLp.type = 'lowpass'; noiseLp.frequency.value = 120;
      const noiseG = c.createGain(); noiseG.gain.value = 0.05;
      noise.connect(noiseLp); noiseLp.connect(noiseG); noiseG.connect(out);
      sub.start(t0); bass.start(t0); lfo.start(t0); noise.start(t0);
      this.drone = { out, sub, bass, lfo, noise };
    }
    stopDrone(fade = 1.2) {
      if (!this.drone) return;
      const t0 = this.now(), d = this.drone;
      d.out.gain.cancelScheduledValues(t0);
      d.out.gain.setValueAtTime(d.out.gain.value, t0);
      d.out.gain.exponentialRampToValueAtTime(0.0001, t0 + fade);
      [d.sub, d.bass, d.lfo, d.noise].forEach(n => n.stop(t0 + fade + 0.1));
      this.drone = null;
    }
    shimmer() {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx;
      const out = c.createGain();
      out.gain.setValueAtTime(0.0001, t0);
      out.gain.exponentialRampToValueAtTime(0.18, t0 + 0.4);
      out.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.8);
      out.connect(this.master);
      [1200, 1800, 2700, 3600].forEach((f, i) => {
        const o = c.createOscillator(); o.type = 'sine';
        o.frequency.setValueAtTime(f * 0.95, t0);
        o.frequency.exponentialRampToValueAtTime(f * 1.05, t0 + 1.4);
        const g = c.createGain(); g.gain.value = 0.18 / (i + 1);
        o.connect(g); g.connect(out); o.start(t0); o.stop(t0 + 1.9);
      });
    }
    whoosh() {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx;
      const n = this.makeNoise(2);
      const bp = c.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 1.2;
      bp.frequency.setValueAtTime(200, t0); bp.frequency.exponentialRampToValueAtTime(4000, t0 + 1.4);
      const out = c.createGain();
      out.gain.setValueAtTime(0.0001, t0);
      out.gain.exponentialRampToValueAtTime(0.32, t0 + 0.15);
      out.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.5);
      n.connect(bp); bp.connect(out); out.connect(this.master);
      n.start(t0); n.stop(t0 + 1.6);
    }
    chime() {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx;
      [[880, .35], [1320, .22], [1760, .10], [2640, .05]].forEach(([f, g0]) => {
        const o = c.createOscillator(); o.type = 'sine'; o.frequency.value = f;
        const g = c.createGain();
        g.gain.setValueAtTime(0.0001, t0);
        g.gain.exponentialRampToValueAtTime(g0, t0 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + 3.2);
        o.connect(g); g.connect(this.master); o.start(t0); o.stop(t0 + 3.3);
      });
      const sub = c.createOscillator(); sub.type = 'sine';
      sub.frequency.setValueAtTime(110, t0);
      sub.frequency.exponentialRampToValueAtTime(55, t0 + 0.4);
      const subG = c.createGain();
      subG.gain.setValueAtTime(0.0001, t0);
      subG.gain.exponentialRampToValueAtTime(0.45, t0 + 0.02);
      subG.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.2);
      sub.connect(subG); subG.connect(this.master); sub.start(t0); sub.stop(t0 + 1.3);
    }
    tick(idx) {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx, base = 1500 + idx * 70;
      [base, base * 2].forEach((f, i) => {
        const o = c.createOscillator(); o.type = 'sine'; o.frequency.value = f;
        const g = c.createGain();
        g.gain.setValueAtTime(0.0001, t0);
        g.gain.exponentialRampToValueAtTime(0.16 / (i + 1), t0 + 0.005);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.18);
        o.connect(g); g.connect(this.master); o.start(t0); o.stop(t0 + 0.2);
      });
      const n = this.makeNoise(0.1);
      const hp = c.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 2000;
      const ng = c.createGain();
      ng.gain.setValueAtTime(0.0001, t0);
      ng.gain.exponentialRampToValueAtTime(0.08, t0 + 0.002);
      ng.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.06);
      n.connect(hp); hp.connect(ng); ng.connect(this.master); n.start(t0); n.stop(t0 + 0.1);
    }
    bass() {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx;
      const o = c.createOscillator(); o.type = 'sine';
      o.frequency.setValueAtTime(120, t0);
      o.frequency.exponentialRampToValueAtTime(45, t0 + 0.25);
      const g = c.createGain();
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(0.7, t0 + 0.015);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.4);
      o.connect(g); g.connect(this.master); o.start(t0); o.stop(t0 + 1.5);
      const n = this.makeNoise(0.3);
      const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 600;
      const ng = c.createGain();
      ng.gain.setValueAtTime(0.0001, t0);
      ng.gain.exponentialRampToValueAtTime(0.28, t0 + 0.01);
      ng.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.6);
      n.connect(lp); lp.connect(ng); ng.connect(this.master); n.start(t0); n.stop(t0 + 0.65);
    }
    highSweep() {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx;
      const n = this.makeNoise(1.5);
      const bp = c.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 2.2;
      bp.frequency.setValueAtTime(1500, t0); bp.frequency.exponentialRampToValueAtTime(5500, t0 + 0.9);
      const g = c.createGain();
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(0.18, t0 + 0.18);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.0);
      n.connect(bp); bp.connect(g); g.connect(this.master); n.start(t0); n.stop(t0 + 1.05);
    }
    transitionWhoosh() {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx;
      const n = this.makeNoise(2);
      const bp = c.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = 1.5;
      bp.frequency.setValueAtTime(3500, t0); bp.frequency.exponentialRampToValueAtTime(220, t0 + 1.5);
      const g = c.createGain();
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(0.32, t0 + 0.2);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.6);
      n.connect(bp); bp.connect(g); g.connect(this.master); n.start(t0); n.stop(t0 + 1.7);
      const o = c.createOscillator(); o.type = 'sawtooth';
      o.frequency.setValueAtTime(440, t0); o.frequency.exponentialRampToValueAtTime(80, t0 + 1.4);
      const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 800;
      const og = c.createGain();
      og.gain.setValueAtTime(0.0001, t0);
      og.gain.exponentialRampToValueAtTime(0.12, t0 + 0.15);
      og.gain.exponentialRampToValueAtTime(0.0001, t0 + 1.5);
      o.connect(lp); lp.connect(og); og.connect(this.master); o.start(t0); o.stop(t0 + 1.6);
    }
    settle() {
      if (!this.ctx) return;
      const t0 = this.now(), c = this.ctx;
      const out = c.createGain();
      out.gain.setValueAtTime(0.0001, t0);
      out.gain.exponentialRampToValueAtTime(0.14, t0 + 0.6);
      out.gain.exponentialRampToValueAtTime(0.04, t0 + 3.5);
      out.gain.exponentialRampToValueAtTime(0.0001, t0 + 7.0);
      out.connect(this.master);
      [220, 330, 440].forEach((f, i) => {
        const o = c.createOscillator(); o.type = i === 0 ? 'sine' : 'triangle'; o.frequency.value = f;
        const g = c.createGain(); g.gain.value = 0.4 / (i + 1);
        o.connect(g); g.connect(out); o.start(t0); o.stop(t0 + 7.1);
      });
    }
  }

  const CUES = [
    { t: 0.00, fn: (a) => a.startDrone() },
    { t: 1.60, fn: (a) => a.shimmer() },
    { t: 2.40, fn: (a) => a.whoosh() },
    { t: 3.50, fn: (a) => a.chime() },
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((i) => ({ t: 4.80 + i * 0.13, fn: (a) => a.tick(i) })),
    { t: 6.10, fn: (a) => a.bass() },
    { t: 7.40, fn: (a) => a.highSweep() },
    { t: 10.50, fn: (a) => a.transitionWhoosh() },
    { t: 10.55, fn: (a) => a.stopDrone(1.5) },
    { t: 12.00, fn: (a) => a.settle() },
  ];

  // ─────────────────────────────────────────────────────────
  // SCENES — each returns an update(time) function
  // ─────────────────────────────────────────────────────────

  function addStyle(el, css) { el.style.cssText = css; return el; }
  function makeDiv(parent, css) { const d = document.createElement('div'); d.style.cssText = css; parent.appendChild(d); return d; }
  function svgEl(tag, attrs) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) Object.keys(attrs).forEach(k => e.setAttribute(k, attrs[k]));
    return e;
  }

  function setAttrs(el, attrs) { for (const k in attrs) el.setAttribute(k, attrs[k]); }

  // Particles
  function buildParticleField(stage) {
    const wrap = makeDiv(stage, 'position:absolute;inset:0;pointer-events:none;');
    const r = seeded(2027);
    const ps = [];
    for (let i = 0; i < 110; i++) {
      ps.push({ angle: r() * Math.PI * 2, startDist: r() * 80, speed: 0.18 + r() * 0.4, phase: r() * 4, size: 1 + r() * 2.5 });
    }
    const els = ps.map(() => {
      const d = document.createElement('div');
      d.style.cssText = 'position:absolute;border-radius:50%;background:' + GOLD_BRIGHT + ';will-change:transform,opacity;';
      wrap.appendChild(d); return d;
    });
    return (time) => {
      const reveal = smoothstep(0.6, 3.0, time);
      const fadeOut = 1 - smoothstep(TRANSITION_START, TRANSITION_END, time);
      for (let i = 0; i < ps.length; i++) {
        const p = ps[i];
        const phaseT = ((time * p.speed + p.phase) % 3.5) / 3.5;
        const dist = p.startDist + phaseT * 1100;
        const x = CX + Math.cos(p.angle) * dist;
        const y = LOGO_Y + Math.sin(p.angle) * dist * 0.62;
        const sz = p.size * (0.25 + phaseT * 2.2);
        const dFade = phaseT < 0.08 ? phaseT * 12 : phaseT > 0.85 ? (1 - phaseT) * 6.6 : 1;
        const op = reveal * fadeOut * dFade * 0.85;
        const el = els[i].style;
        el.left = (x - sz / 2) + 'px';
        el.top = (y - sz / 2) + 'px';
        el.width = sz + 'px';
        el.height = sz + 'px';
        el.opacity = op;
        el.boxShadow = '0 0 ' + (sz * 4) + 'px ' + (sz * 0.5) + 'px rgba(' + GOLD_RGB + ',0.55)';
      }
    };
  }

  // Beam
  function buildBeam(stage) {
    const d = makeDiv(stage, 'position:absolute;left:' + (CX - 260) + 'px;top:-80px;width:520px;height:' + (H + 160) + 'px;' +
      'background:radial-gradient(ellipse 260px 620px at 50% 45%, rgba(' + GOLD_RGB + ',0.22), rgba(' + GOLD_RGB + ',0) 70%);' +
      'mix-blend-mode:screen;pointer-events:none;filter:blur(2px);transform-origin:50% 0%;');
    return (time) => {
      const a = smoothstep(2.0, 4.0, time);
      const b = 1 - smoothstep(TRANSITION_START, TRANSITION_END, time);
      const sway = Math.sin(time * 0.5) * 8;
      const pulse = 0.7 + 0.3 * Math.sin(time * 1.4);
      d.style.opacity = a * b * pulse;
      d.style.transform = 'rotate(' + sway + 'deg)';
    };
  }

  // Core glow
  function buildCoreGlow(stage) {
    const d = makeDiv(stage, 'position:absolute;left:' + (CX - 560) + 'px;top:' + (LOGO_Y - 560) + 'px;width:1120px;height:1120px;' +
      'background:radial-gradient(circle at 50% 50%, rgba(' + GOLD_RGB + ',0.55) 0%, rgba(' + GOLD_RGB + ',0.22) 20%, rgba(' + GOLD_RGB + ',0.05) 42%, rgba(' + GOLD_RGB + ',0) 62%);' +
      'mix-blend-mode:screen;pointer-events:none;filter:blur(10px);transform-origin:center;');
    return (time) => {
      const seed = smoothstep(0.4, 1.6, time) * 0.5;
      const main = smoothstep(2.5, 5.0, time);
      const exit = 1 - smoothstep(TRANSITION_START, TRANSITION_END, time);
      const breath = 1 + 0.06 * Math.sin(time * 1.3);
      d.style.opacity = (seed + main) * exit;
      d.style.transform = 'scale(' + breath + ')';
    };
  }

  // Rings + sweep dots
  function buildRings(stage) {
    const svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H });
    svg.style.cssText = 'position:absolute;inset:0;pointer-events:none;';

    const defs = svgEl('defs');
    defs.innerHTML =
      '<linearGradient id="tiRingGrad" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0%" stop-color="' + GOLD + '" stop-opacity="0"/>' +
      '<stop offset="35%" stop-color="' + GOLD_BRIGHT + '" stop-opacity="1"/>' +
      '<stop offset="70%" stop-color="#8a6e3f" stop-opacity="1"/>' +
      '<stop offset="100%" stop-color="' + GOLD + '" stop-opacity="0"/>' +
      '</linearGradient>' +
      '<radialGradient id="tiSweepGrad">' +
      '<stop offset="0%" stop-color="' + GOLD_BRIGHT + '" stop-opacity="1"/>' +
      '<stop offset="100%" stop-color="' + GOLD + '" stop-opacity="0"/>' +
      '</radialGradient>';
    svg.appendChild(defs);

    const outerR = 380, innerR = 310, farR = 460;
    const cOuter = 2 * Math.PI * outerR, cInner = 2 * Math.PI * innerR, cFar = 2 * Math.PI * farR;

    const farRing = svgEl('circle', { cx: CX, cy: LOGO_Y, r: farR, fill: 'none', stroke: 'rgba(' + GOLD_RGB + ',0.18)', 'stroke-width': 0.8, 'stroke-dasharray': '1 6' });
    svg.appendChild(farRing);
    const outerRing = svgEl('circle', { cx: CX, cy: LOGO_Y, r: outerR, fill: 'none', stroke: 'url(#tiRingGrad)', 'stroke-width': 1.4, 'stroke-dasharray': cOuter });
    svg.appendChild(outerRing);
    const innerRing = svgEl('circle', { cx: CX, cy: LOGO_Y, r: innerR, fill: 'none', stroke: 'rgba(' + GOLD_RGB + ',0.55)', 'stroke-width': 1, 'stroke-dasharray': '2 10' });
    svg.appendChild(innerRing);

    // 8 tick marks
    const ticks = [];
    [0, 45, 90, 135, 180, 225, 270, 315].forEach((deg) => {
      const rad = (deg * Math.PI) / 180;
      const x1 = CX + Math.cos(rad) * (outerR - 10), y1 = LOGO_Y + Math.sin(rad) * (outerR - 10);
      const x2 = CX + Math.cos(rad) * (outerR + 12), y2 = LOGO_Y + Math.sin(rad) * (outerR + 12);
      const major = deg % 90 === 0;
      const l = svgEl('line', { x1, y1, x2, y2, stroke: GOLD, 'stroke-width': major ? 1.5 : 0.8 });
      svg.appendChild(l); ticks.push({ el: l, major });
    });

    // Sweep dots
    const sweep1 = svgEl('g');
    sweep1.innerHTML = '<circle cx="' + (CX + outerR) + '" cy="' + LOGO_Y + '" r="14" fill="url(#tiSweepGrad)"/>' +
      '<circle cx="' + (CX + outerR) + '" cy="' + LOGO_Y + '" r="3.5" fill="' + GOLD_BRIGHT + '"/>';
    svg.appendChild(sweep1);
    const sweep2 = svgEl('g');
    sweep2.innerHTML = '<circle cx="' + (CX + innerR) + '" cy="' + LOGO_Y + '" r="9" fill="url(#tiSweepGrad)"/>' +
      '<circle cx="' + (CX + innerR) + '" cy="' + LOGO_Y + '" r="2" fill="' + GOLD_BRIGHT + '"/>';
    svg.appendChild(sweep2);

    stage.appendChild(svg);

    return (time) => {
      const r1 = ease.outQuart(smoothstep(1.6, 3.6, time));
      const r2 = ease.outQuart(smoothstep(2.2, 4.2, time));
      const r3 = smoothstep(3.0, 5.0, time);
      const ticksP = smoothstep(3.6, 5.5, time);
      const exit = 1 - smoothstep(TRANSITION_START, TRANSITION_END, time);
      svg.style.opacity = exit;
      outerRing.setAttribute('stroke-dashoffset', cOuter * (1 - r1));
      outerRing.setAttribute('transform', 'rotate(' + (-90 + time * 5) + ' ' + CX + ' ' + LOGO_Y + ')');
      innerRing.setAttribute('stroke-dashoffset', cInner * (1 - r2));
      innerRing.setAttribute('transform', 'rotate(' + (-time * 18) + ' ' + CX + ' ' + LOGO_Y + ')');
      farRing.setAttribute('stroke-dashoffset', cFar * (1 - r3));
      farRing.setAttribute('transform', 'rotate(' + (-time * 8) + ' ' + CX + ' ' + LOGO_Y + ')');
      ticks.forEach((t) => t.el.setAttribute('opacity', ticksP * (t.major ? 0.85 : 0.4)));
      const sweepAngle = (time * 110) % 360;
      sweep1.setAttribute('transform', 'rotate(' + sweepAngle + ' ' + CX + ' ' + LOGO_Y + ')');
      sweep1.setAttribute('opacity', smoothstep(3.8, 4.6, time) * exit);
      sweep2.setAttribute('transform', 'rotate(' + (-sweepAngle * 0.7 + 180) + ' ' + CX + ' ' + LOGO_Y + ')');
      sweep2.setAttribute('opacity', smoothstep(4.2, 5.0, time) * exit * 0.7);
    };
  }

  // Scan sweep
  function buildScan(stage) {
    const d = makeDiv(stage, 'position:absolute;left:0;width:100%;height:160px;' +
      'background:linear-gradient(180deg, rgba(' + GOLD_RGB + ',0) 0%, rgba(' + GOLD_RGB + ',0.22) 50%, rgba(' + GOLD_RGB + ',0) 100%);' +
      'mix-blend-mode:screen;pointer-events:none;display:none;');
    return (time) => {
      const start = 2.4, dur = 1.4;
      const p = smoothstep(start, start + dur, time);
      const active = time > start && time < start + dur + 0.3;
      if (!active) { d.style.display = 'none'; return; }
      d.style.display = 'block';
      d.style.top = lerp(-60, H + 60, p) + 'px';
      d.style.opacity = (1 - Math.abs(p * 2 - 1)) * 0.55;
    };
  }

  // Logo
  function buildLogo(stage, logoSrc, getMorphTarget) {
    const wrap = makeDiv(stage, 'position:absolute;left:0;top:0;will-change:transform,opacity,left,top,width,height;');
    const img = document.createElement('img');
    img.src = logoSrc;
    img.alt = 'Thanatos';
    img.style.cssText = 'width:100%;height:100%;object-fit:contain;display:block;';
    wrap.appendChild(img);
    return (time) => {
      const introIn = smoothstep(2.8, 4.8, time);
      const breath = 1 + 0.012 * Math.sin(time * 1.2);
      const trans = ease.inOutCubic(smoothstep(TRANSITION_START, TRANSITION_END, time));
      const introCx = CX, introCy = LOGO_Y, introSize = 420;
      const tgt = getMorphTarget();
      const cx = lerp(introCx, tgt.cx, trans);
      const cy = lerp(introCy, tgt.cy, trans);
      let size = lerp(introSize, tgt.size, trans);
      const entryScale = lerp(0.6, 1.0, ease.outCubic(introIn));
      size = size * entryScale;
      const rot = lerp(-18, 0, ease.outCubic(introIn));
      const glow = lerp(1, 0.4, trans);
      const s = wrap.style;
      s.left = (cx - size / 2) + 'px';
      s.top = (cy - size / 2) + 'px';
      s.width = size + 'px';
      s.height = size + 'px';
      s.opacity = introIn;
      s.transform = 'scale(' + breath + ') rotate(' + rot + 'deg)';
      s.filter = 'drop-shadow(0 0 ' + (24 * glow) + 'px rgba(' + GOLD_RGB + ',' + (0.6 * glow) + '))' +
                 ' drop-shadow(0 0 ' + (64 * glow) + 'px rgba(' + GOLD_RGB + ',' + (0.3 * glow) + '))';
    };
  }

  // Wordmark
  function buildWordmark(stage) {
    const wrap = makeDiv(stage, 'position:absolute;inset:0;pointer-events:none;');
    const letters = 'THANATOS'.split('');
    const SIZE = 260, LETTER_W = SIZE * 0.62, totalW = LETTER_W * letters.length;
    const startX = CX - totalW / 2, baselineY = 770;
    const els = letters.map((ch, i) => {
      const d = document.createElement('div');
      d.textContent = ch;
      d.style.cssText =
        'position:absolute;width:' + LETTER_W + 'px;text-align:center;' +
        'font-family:"Cinzel Decorative","Cinzel","Times New Roman",serif;' +
        'font-size:' + SIZE + 'px;font-weight:600;line-height:1;color:transparent;' +
        'background:linear-gradient(180deg,#fff4d2 0%,' + GOLD_BRIGHT + ' 28%,' + GOLD + ' 50%,#8a6e3f 75%,' + GOLD + ' 100%);' +
        '-webkit-background-clip:text;background-clip:text;' +
        'filter:drop-shadow(0 4px 24px rgba(0,0,0,.6)) drop-shadow(0 0 30px rgba(' + GOLD_RGB + ',.18));' +
        'will-change:transform,opacity,top,left;';
      wrap.appendChild(d);
      return d;
    });
    return (time) => {
      const fadeOut = 1 - smoothstep(TRANSITION_START, TRANSITION_END - 0.3, time);
      wrap.style.opacity = fadeOut;
      letters.forEach((ch, i) => {
        const tStart = 4.8 + i * 0.13, tEnd = tStart + 1.0;
        const p = ease.outQuart(smoothstep(tStart, tEnd, time));
        const visible = time > tStart - 0.1;
        const el = els[i];
        if (!visible) { el.style.opacity = 0; return; }
        const fromAbove = i % 2 === 0;
        const startY = baselineY + (fromAbove ? -260 : 260);
        const x = startX + i * LETTER_W;
        const y = lerp(startY, baselineY, p);
        const jitterStart = (i - letters.length / 2 + 0.5) * 28;
        const xJit = lerp(jitterStart, 0, p);
        const scaleY = lerp(0.7, 1, p);
        const s = el.style;
        s.left = (x + xJit) + 'px';
        s.top = y + 'px';
        s.opacity = p;
        s.transform = 'scaleY(' + scaleY + ')';
        s.transformOrigin = 'center bottom';
      });
    };
  }

  // Tagline
  function buildTagline(stage) {
    const wrap = makeDiv(stage, 'position:absolute;left:0;right:0;top:970px;text-align:center;pointer-events:none;');
    const row = makeDiv(wrap, 'display:flex;align-items:center;justify-content:center;gap:28px;');
    makeDiv(row, 'width:120px;height:1px;background:linear-gradient(90deg,rgba(' + GOLD_RGB + ',0) 0%,rgba(' + GOLD_RGB + ',0.85) 100%);');
    const text = makeDiv(row,
      'font-family:"Space Grotesk",system-ui,sans-serif;font-size:30px;font-weight:400;' +
      'color:#f1e3bf;text-transform:uppercase;');
    text.textContent = "We see what others don't";
    makeDiv(row, 'width:120px;height:1px;background:linear-gradient(90deg,rgba(' + GOLD_RGB + ',0.85) 0%,rgba(' + GOLD_RGB + ',0) 100%);');
    return (time) => {
      const t = smoothstep(7.4, 9.0, time);
      const opacity = ease.outCubic(t);
      const exit = 1 - smoothstep(TRANSITION_START, TRANSITION_END - 0.4, time);
      const spacing = lerp(2, 16, t);
      wrap.style.opacity = opacity * exit;
      text.style.letterSpacing = spacing + 'px';
      text.style.paddingLeft = spacing + 'px';
    };
  }

  // Brackets
  function buildBrackets(stage) {
    const svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H });
    svg.style.cssText = 'position:absolute;inset:0;pointer-events:none;';
    const inset = 40, arm = 32;
    const cs = [
      [inset, inset, 1, 1],
      [W - inset, inset, -1, 1],
      [inset, H - inset, 1, -1],
      [W - inset, H - inset, -1, -1],
    ];
    cs.forEach(([x, y, hx, hy]) => {
      const g = svgEl('g', { stroke: GOLD, 'stroke-width': 1.6, fill: 'none', opacity: 0.6 });
      g.innerHTML = '<line x1="' + x + '" y1="' + y + '" x2="' + (x + arm * hx) + '" y2="' + y + '"/>' +
                    '<line x1="' + x + '" y1="' + y + '" x2="' + x + '" y2="' + (y + arm * hy) + '"/>';
      svg.appendChild(g);
    });
    stage.appendChild(svg);
    return (time) => {
      svg.style.opacity = smoothstep(0.9, 2.0, time) * (1 - smoothstep(TRANSITION_START, TRANSITION_END - 0.3, time));
    };
  }

  // HUD
  function buildHud(stage) {
    const tl = makeDiv(stage, 'position:absolute;left:56px;top:48px;font-family:"JetBrains Mono",ui-monospace,monospace;' +
      'font-size:13px;color:' + GOLD + ';letter-spacing:0.22em;line-height:1.7;pointer-events:none;');
    tl.innerHTML = '<div style="display:flex;align-items:center;gap:10px;">' +
      '<div id="ti-dot" style="width:7px;height:7px;background:' + GOLD + ';box-shadow:0 0 8px ' + GOLD + ';"></div>' +
      '<span>THANATOS // SYS_INIT</span></div>' +
      '<div style="color:rgba(' + GOLD_RGB + ',0.55);margin-top:6px;">STATUS:&nbsp;<span id="ti-state" style="color:' + GOLD + '">SCANNING</span></div>';
    const dot = tl.querySelector('#ti-dot'); const stateEl = tl.querySelector('#ti-state');
    const states = ['SCANNING', 'TRACKING', 'DECODING', 'RESOLVING'];

    const br = makeDiv(stage, 'position:absolute;right:56px;bottom:48px;font-family:"JetBrains Mono",ui-monospace,monospace;' +
      'font-size:12px;color:rgba(' + GOLD_RGB + ',0.6);text-align:right;letter-spacing:0.18em;line-height:1.7;pointer-events:none;');
    br.innerHTML = '<div id="ti-frame"></div><div id="ti-time"></div>' +
      '<div style="color:' + GOLD + ';margin-top:6px;">THANATOS.AGENCY</div>';
    const frameEl = br.querySelector('#ti-frame'); const timeEl = br.querySelector('#ti-time');

    return (time) => {
      const op = smoothstep(1.2, 2.6, time) * (1 - smoothstep(TRANSITION_START, TRANSITION_END - 0.3, time));
      tl.style.opacity = op; br.style.opacity = op;
      dot.style.opacity = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(time * 4));
      stateEl.textContent = states[Math.floor(time * 1.5) % 4];
      frameEl.textContent = 'FRAME 0x' + (Math.floor((time * 100) % 99999)).toString(16).toUpperCase().padStart(5, '0');
      timeEl.textContent = 'T+' + time.toFixed(2).padStart(5, '0') + 's';
    };
  }

  // Vignette + grain
  function buildVignetteGrain(stage) {
    makeDiv(stage,
      'position:absolute;inset:0;pointer-events:none;' +
      'background:radial-gradient(ellipse at center, rgba(0,0,0,0) 25%, rgba(0,0,0,0.6) 75%, rgba(0,0,0,0.96) 100%);');
    const grain = makeDiv(stage,
      'position:absolute;inset:0;pointer-events:none;mix-blend-mode:overlay;opacity:0.08;' +
      "background-image:url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.5 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\");" +
      'background-size:160px 160px;');
    return (time) => {
      const shift = Math.floor(time * 60) % 8;
      grain.style.backgroundPosition = (shift * 7) + 'px ' + (shift * 11) + 'px';
    };
  }

  // ─────────────────────────────────────────────────────────
  // BOOT
  // ─────────────────────────────────────────────────────────
  function boot() {
    if (!shouldPlay()) {
      addReplayButton();
      return;
    }

    const LOGO_SRC = '/assets/thanatos_intel/images/thanatos-logo-mark.png';
    let time = 0;
    let lastTs = null;
    let cancelled = false;
    let lastCueIdx = -1;
    const audio = new AudioEngine();

    // Build overlay
    const overlay = document.createElement('div');
    overlay.id = 'thanatos-intro-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;background:#000;overflow:hidden;';
    document.body.appendChild(overlay);

    const stage = document.createElement('div');
    stage.style.cssText = 'position:absolute;width:' + W + 'px;height:' + H + 'px;' +
      'transform-origin:0 0;will-change:transform;' +
      'background:radial-gradient(ellipse at 50% 45%, #050402 0%, #020201 60%, #000 100%);';
    overlay.appendChild(stage);

    // Camera-push wrapper
    const cam = makeDiv(stage, 'position:absolute;inset:0;transform-origin:center;will-change:transform;');

    // Compute morph target from the actual hero logo in DOM
    function getMorphTarget() {
      const heroLogo = document.querySelector('.t-hero-logo img');
      if (!heroLogo) return { cx: CX, cy: 200, size: 220 };
      const r = heroLogo.getBoundingClientRect();
      // Convert viewport coords → stage coords (the stage is scaled and offset)
      const scale = parseFloat(stage.dataset.scale || '1');
      const offX = parseFloat(stage.dataset.offX || '0');
      const offY = parseFloat(stage.dataset.offY || '0');
      const cxScreen = r.left + r.width / 2;
      const cyScreen = r.top + r.height / 2;
      return {
        cx: (cxScreen - offX) / scale,
        cy: (cyScreen - offY) / scale,
        size: r.width / scale,
      };
    }

    // Build scenes
    const updates = [
      buildBeam(cam),
      buildCoreGlow(cam),
      buildParticleField(cam),
      buildRings(cam),
      buildScan(cam),
      buildWordmark(cam),
      buildTagline(cam),
      buildBrackets(cam),
      buildHud(cam),
      buildLogo(cam, LOGO_SRC, getMorphTarget),
      buildVignetteGrain(stage),
    ];

    // Mute button
    const muteBtn = document.createElement('button');
    muteBtn.style.cssText = 'position:absolute;right:24px;top:24px;width:40px;height:40px;' +
      'background:rgba(15,10,3,0.7);border:1px solid rgba(' + GOLD_RGB + ',0.3);border-radius:4px;' +
      'color:' + GOLD + ';font-size:16px;cursor:pointer;z-index:90;backdrop-filter:blur(8px);display:none;';
    muteBtn.textContent = '🔊';
    muteBtn.title = 'Mute';
    overlay.appendChild(muteBtn);

    // Audio gate
    const gate = document.createElement('div');
    gate.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' +
      'background:rgba(0,0,0,0.55);backdrop-filter:blur(6px);cursor:pointer;z-index:200;';
    gate.innerHTML =
      '<div style="display:flex;flex-direction:column;align-items:center;gap:22px;padding:32px 44px;' +
      'border:1px solid rgba(' + GOLD_RGB + ',0.35);background:rgba(15,10,3,0.85);color:' + GOLD + ';' +
      'font-family:\"JetBrains Mono\",ui-monospace,monospace;letter-spacing:0.28em;text-transform:uppercase;">' +
      '<div style="font-size:42px;line-height:1;">♪</div>' +
      '<div style="font-size:14px;">Enter with sound</div>' +
      '<div style="font-size:10px;color:rgba(' + GOLD_RGB + ',0.55);letter-spacing:0.22em;">Click to begin · ESC to skip</div>' +
      '</div>';
    overlay.appendChild(gate);

    // Skip hint (always present)
    const skipHint = document.createElement('div');
    skipHint.style.cssText = 'position:absolute;left:24px;bottom:24px;font-family:"JetBrains Mono",monospace;' +
      'font-size:11px;color:rgba(' + GOLD_RGB + ',0.5);letter-spacing:0.18em;text-transform:uppercase;z-index:90;cursor:pointer;';
    skipHint.textContent = '› Skip intro';
    overlay.appendChild(skipHint);

    function finish() {
      if (cancelled) return;
      cancelled = true;
      try { localStorage.setItem(STORAGE_KEY, '1'); } catch (e) {}
      try { audio.stopDrone(0.4); } catch (e) {}
      // fade out overlay
      overlay.style.transition = 'opacity 600ms ease';
      overlay.style.opacity = '0';
      setTimeout(() => {
        overlay.parentNode && overlay.parentNode.removeChild(overlay);
        try { audio.ctx && audio.ctx.close(); } catch (e) {}
        addReplayButton();
      }, 650);
      window.removeEventListener('resize', fit);
      document.removeEventListener('keydown', onKey);
    }

    function fit() {
      const vw = window.innerWidth, vh = window.innerHeight;
      const s = Math.min(vw / W, vh / H);
      const offX = (vw - W * s) / 2;
      const offY = (vh - H * s) / 2;
      stage.style.transform = 'translate(' + offX + 'px,' + offY + 'px) scale(' + s + ')';
      stage.dataset.scale = String(s);
      stage.dataset.offX = String(offX);
      stage.dataset.offY = String(offY);
    }
    fit();
    window.addEventListener('resize', fit);

    function onKey(e) {
      if (e.code === 'Escape') { e.preventDefault(); finish(); }
    }
    document.addEventListener('keydown', onKey);
    skipHint.addEventListener('click', finish);

    // Mute toggle
    muteBtn.addEventListener('click', () => {
      const m = !audio.muted;
      audio.setMuted(m);
      muteBtn.textContent = m ? '🔇' : '🔊';
    });

    // Start
    let started = false;
    function start() {
      if (started) return;
      started = true;
      // resume audio (synchronous for Safari)
      audio.resume().then((ok) => {
        if (ok) muteBtn.style.display = 'block';
      });
      gate.style.transition = 'opacity 250ms ease';
      gate.style.opacity = '0';
      setTimeout(() => gate.remove(), 280);
      raf();
    }
    gate.addEventListener('click', start);

    // RAF loop
    function raf() {
      if (cancelled) return;
      requestAnimationFrame((ts) => {
        if (cancelled) return;
        if (lastTs == null) lastTs = ts;
        const dt = Math.min(0.1, (ts - lastTs) / 1000);
        lastTs = ts;
        time += dt;

        // camera push
        const push = lerp(1.0, 1.12, ease.inOutCubic(smoothstep(0, INTRO_DURATION - 1.5, time)));
        cam.style.transform = 'scale(' + push + ')';

        // run scene updates
        for (let i = 0; i < updates.length; i++) updates[i](time);

        // fire audio cues
        if (audio.ctx) {
          for (let i = lastCueIdx + 1; i < CUES.length; i++) {
            if (time >= CUES[i].t) { CUES[i].fn(audio); lastCueIdx = i; } else break;
          }
        }

        if (time >= INTRO_DURATION) { finish(); return; }
        raf();
      });
    }
  }

  // ── Replay button on the live home ───────────────────────
  function addReplayButton() {
    if (document.getElementById('ti-replay-btn')) return;
    const b = document.createElement('button');
    b.id = 'ti-replay-btn';
    b.textContent = '▶';
    b.title = 'Replay intro';
    b.setAttribute('aria-label', 'Replay intro');
    b.style.cssText =
      'position:fixed;left:20px;bottom:20px;z-index:9998;' +
      'width:48px;height:48px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;padding-left:3px;' +
      'background:rgba(15,10,3,0.85);border:1px solid rgba(' + GOLD_RGB + ',0.45);' +
      'color:' + GOLD + ';font-size:16px;line-height:1;cursor:pointer;backdrop-filter:blur(8px);' +
      'box-shadow:0 8px 24px rgba(0,0,0,.35);transition:transform .15s,box-shadow .15s;';
    b.onmouseenter = () => { b.style.transform = 'translateY(-2px)'; b.style.boxShadow = '0 12px 30px rgba(' + GOLD_RGB + ',0.30)'; };
    b.onmouseleave = () => { b.style.transform = 'none'; b.style.boxShadow = '0 8px 24px rgba(0,0,0,.35)'; };
    b.onclick = () => {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      b.remove();
      boot();
    };
    document.body.appendChild(b);
  }

  // ── Init ─────────────────────────────────────────────────
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
