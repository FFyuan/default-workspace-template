// Sample data and small drawing helpers shared by every mock. The numbers describe one plausible
// workspace: the default 8 GiB machine with a 28 GB disk and 4 vCPUs, three chats open (one
// working), two user-built apps, and one program stopped by the memory guard this morning.
(() => {
  const GiB = 2 ** 30, MiB = 2 ** 20, GB = 1e9;
  const now = Date.now();
  const todayAt = (h, m) => { const d = new Date(now); d.setHours(h, m, 0, 0); return d; };
  const yesterdayAt = (h, m) => { const d = todayAt(h, m); d.setDate(d.getDate() - 1); return d; };

  // A deterministic random walk so every page shows the same history.
  function seeded(seed) {
    let s = seed >>> 0;
    return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 2 ** 32; };
  }
  function walk(seed, count, base, amplitude, stepMs, { spikes = 0, lo = 0.02, hi = 0.98 } = {}) {
    const rand = seeded(seed);
    const out = [];
    let v = base;
    for (let i = 0; i < count; i++) {
      v += (rand() - 0.5) * amplitude + (base - v) * 0.05;
      if (spikes && rand() < spikes) v += amplitude * 4 * rand();
      v = Math.min(hi, Math.max(lo, v));
      out.push({ t: now - (count - 1 - i) * stepMs, v });
    }
    return out;
  }

  const chats = [
    { name: "Website redesign", mem: 1.38 * GiB, cpu: 23.6, state: "working", since: "2 h", model: "Claude Opus 5.5" },
    { name: "Budget tracker", mem: 622 * MiB, cpu: 0.8, state: "idle", since: "40 min", model: "Claude Sonnet 5.5" },
    { name: "Fix login bug", mem: 418 * MiB, cpu: 0.0, state: "idle", since: "3 h", model: "Claude Opus 5.5" },
  ];
  const checkers = [{ name: "Website redesign", mem: 534 * MiB, cpu: 5.9 }];
  const apps = [
    { name: "Recipe box", mem: 192 * MiB, cpu: 0.4 },
    { name: "Habit tracker", mem: 118 * MiB, cpu: 0.1 },
  ];
  const memory = { total: 8 * GiB, used: 5.1 * GiB };
  memory.available = memory.total - memory.used;
  const sum = (xs, k) => xs.reduce((a, x) => a + x[k], 0);
  const groups = [
    { id: "chats", label: "Chats", items: chats, mem: sum(chats, "mem"), cpu: sum(chats, "cpu") },
    { id: "checkers", label: "Code checkers", items: checkers, mem: sum(checkers, "mem"), cpu: sum(checkers, "cpu") },
    { id: "workspace", label: "Workspace", hint: "chat app, desktop, built-in apps, background services", items: [], mem: 880 * MiB, cpu: 3.9 },
    { id: "apps", label: "Your apps", items: apps, mem: sum(apps, "mem"), cpu: sum(apps, "cpu") },
    { id: "shared", label: "Shared", hint: "by chats, apps and services", items: [], mem: 612 * MiB, cpu: null },
    { id: "scratch", label: "Temporary files", items: [], mem: 241 * MiB, cpu: null, limit: 1.9 * GiB },
  ];
  groups.push({ id: "system", label: "System", items: [], mem: memory.used - sum(groups, "mem"), cpu: 2.5 });

  const cpu = { cores: 4, pct: 36.7, perCore: [61, 44, 19, 23], load: [1.48, 0.92, 0.71], uptime: "2 d 6 h", processes: 142, threads: 611 };
  const disk = { total: 28 * GB, used: 11.4 * GB };
  disk.free = disk.total - disk.used;
  const diskBreakdown = [
    { name: "Workspace files", bytes: 3.1 * GB, hint: "data/, documents, project folders" },
    { name: "Package caches", bytes: 2.4 * GB, hint: "uv, npm, pip" },
    { name: "Uploads", bytes: 1.2 * GB },
    { name: "App data", bytes: 0.9 * GB, hint: "data/.apps/" },
    { name: "System", bytes: 3.8 * GB, hint: "the workspace's own programs and tools" },
  ];
  const stops = [
    { at: todayAt(9, 42), what: "the Budget tracker chat's code checker", command: "/home/user/.local/share/pnpm/node /home/user/workspace/node_modules/typescript/lib/tsserver.js --serverMode partialSemantic" },
    { at: yesterdayAt(22, 15), what: "a test browser a chat was using to check an app", command: "/home/user/.cache/ms-playwright/chromium-1181/chrome-linux/chrome --headless=new --remote-debugging-pipe" },
  ];
  const tokens = {
    today: { input: 1_240_000, output: 84_300, cacheRead: 9_800_000, cost: 6.42, turns: 118 },
    week: { cost: 31.8 },
    windows: [
      { label: "5-hour window", used: 42, resetsIn: "2 h 10 min" },
      { label: "7-day window", used: 61, resetsIn: "3 d 4 h" },
    ],
    budget: { monthlyUsd: 100, spentUsd: 57.3, daysLeft: 11 },
    perChat: [
      { name: "Website redesign", cost: 4.11, tokens: 7_900_000, turns: 71 },
      { name: "Budget tracker", cost: 1.65, tokens: 2_600_000, turns: 32 },
      { name: "Fix login bug", cost: 0.66, tokens: 1_100_000, turns: 15 },
    ],
    hourly: walk(7, 24, 0.3, 0.25, 3600e3, { lo: 0, hi: 1 }).map((p, i) => ({ ...p, v: i < 8 ? p.v * 0.15 : p.v })),
  };

  // Histories: 10 minutes at 5 s (the current app's), 60 minutes at 10 s, and 24 hours at 5 min.
  const history = {
    mem10: walk(11, 120, 0.62, 0.02, 5000),
    cpu10: walk(23, 120, 0.35, 0.12, 5000, { spikes: 0.04 }),
    mem60: walk(31, 360, 0.6, 0.03, 10000),
    cpu60: walk(37, 360, 0.3, 0.14, 10000, { spikes: 0.03 }),
    disk60: walk(41, 360, 0.405, 0.002, 10000, { lo: 0.39, hi: 0.42 }),
    mem24: walk(53, 288, 0.55, 0.05, 300e3),
    cpu24: walk(59, 288, 0.25, 0.15, 300e3, { spikes: 0.05 }),
    cores60: [61, 44, 19, 23].map((base, i) => walk(70 + i, 360, base / 100, 0.2, 10000, { spikes: 0.03 })),
  };
  // Leave a gap in the 60-minute line where the machine was paused, as the real app does.
  for (const key of ["mem60", "cpu60", "disk60"]) history[key] = history[key].filter((p) => !(p.t < now - 38 * 60e3 && p.t > now - 41 * 60e3));

  function size(bytes) {
    const gb = bytes / GiB;
    if (gb >= 10) return `${gb.toFixed(0)} GB`;
    if (gb >= 1) return `${gb.toFixed(1)} GB`;
    return `${Math.round(bytes / MiB)} MB`;
  }
  function sizeDecimal(bytes) {
    const gb = bytes / GB;
    if (gb >= 10) return `${gb.toFixed(0)} GB`;
    if (gb >= 1) return `${gb.toFixed(1)} GB`;
    return `${Math.round(bytes / 1e6)} MB`;
  }
  const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);
  const level = (p, warn, bad) => (p >= bad ? "bad" : p >= warn ? "warn" : "ok");
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const cap = (t) => (t ? t[0].toUpperCase() + t.slice(1) : t);
  const tokensShort = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
  const clock = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  // A line (and optional area) for samples over the last windowMs, in a viewBox of w x h. y runs
  // from 0 (full) to h (empty). Gaps longer than gapMs break the line.
  function sparkPath(samples, { w = 300, h = 100, windowMs, gapMs = Infinity, area = false, end = now } = {}) {
    if (!samples.length) return "";
    const pts = samples.map((p) => ({ x: w - ((end - p.t) / windowMs) * w, y: (1 - p.v) * h }));
    let d = "", segStart = null;
    pts.forEach((pt, i) => {
      const gap = i === 0 || samples[i].t - samples[i - 1].t > gapMs;
      if (gap) {
        if (area && segStart !== null) d += ` L${pts[i - 1].x.toFixed(1)} ${h} L${segStart.toFixed(1)} ${h} Z`;
        segStart = pt.x;
        d += `${area ? " M" + pt.x.toFixed(1) + " " + h + " L" : " M"}${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
      } else d += ` L${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`;
    });
    if (area && segStart !== null) d += ` L${pts[pts.length - 1].x.toFixed(1)} ${h} L${segStart.toFixed(1)} ${h} Z`;
    return d.trim();
  }

  // Draws one or more series into an svg.spark: faint grid, a dashed "full" line, then each series
  // as an area plus a line, and a hover readout naming the time and every series' value.
  function drawSpark(svg, series, { windowMs, h = 100, grid = [25, 50, 75], full = true, gapMs = Infinity, labels = true } = {}) {
    const w = 300;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("preserveAspectRatio", "none");
    let inner = grid.map((g) => `<path d="M0 ${(h * (1 - g / 100)).toFixed(1)} H${w}" stroke="var(--c-border)" stroke-width="1" vector-effect="non-scaling-stroke"/>`).join("");
    inner += `<path d="M0 ${h} H${w}" stroke="var(--c-border-strong)" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
    if (full) inner += `<path d="M0 0.5 H${w}" stroke="var(--c-danger)" stroke-dasharray="3 3" stroke-width="1" opacity=".6" vector-effect="non-scaling-stroke"/>`;
    for (const s of series) {
      if (s.area !== false) inner += `<path d="${sparkPath(s.samples, { w, h, windowMs, gapMs, area: true })}" fill="${s.color}" opacity="${s.areaOpacity ?? 0.08}"/>`;
      inner += `<path d="${sparkPath(s.samples, { w, h, windowMs, gapMs })}" fill="none" stroke="${s.color}" stroke-width="${s.width ?? 1.6}" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>`;
    }
    inner += `<line class="cursor" x1="0" x2="0" y1="0" y2="${h}" stroke="var(--c-text-faint)" stroke-width="1" vector-effect="non-scaling-stroke" opacity="0"/>`;
    svg.innerHTML = inner;
    if (!labels) return;
    // Hover: the nearest reading of each series at the pointer's time.
    const host = svg.parentElement;
    host.classList.add("has-tip");
    let tip = host.querySelector(".spark-tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "spark-tip"; tip.hidden = true; host.appendChild(tip); }
    const cursor = svg.querySelector(".cursor");
    svg.addEventListener("pointermove", (e) => {
      const box = svg.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
      const t = now - (1 - frac) * windowMs;
      const parts = series.map((s) => {
        let best = null;
        for (const p of s.samples) if (!best || Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
        return best ? `${s.name}: ${s.format ? s.format(best.v) : Math.round(best.v * 100) + "%"}` : null;
      }).filter(Boolean);
      tip.textContent = `${clock(new Date(t))} · ${parts.join(" · ")}`;
      tip.hidden = false;
      tip.style.left = `${e.clientX - host.getBoundingClientRect().left}px`;
      tip.style.top = `${box.top - host.getBoundingClientRect().top}px`;
      cursor.setAttribute("x1", (frac * w).toFixed(1));
      cursor.setAttribute("x2", (frac * w).toFixed(1));
      cursor.setAttribute("opacity", "1");
    });
    svg.addEventListener("pointerleave", () => { tip.hidden = true; cursor.setAttribute("opacity", "0"); });
  }

  // A compact single-series sparkline with no grid: for tiles and widgets.
  function drawMiniSpark(svg, samples, { windowMs, color, h = 40 } = {}) {
    const w = 300;
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.innerHTML = `<path d="${sparkPath(samples, { w, h, windowMs, area: true })}" fill="${color}" opacity="0.1"/>`
      + `<path d="${sparkPath(samples, { w, h, windowMs })}" fill="none" stroke="${color}" stroke-width="1.5" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>`;
  }

  function bar(el, segments) {
    el.innerHTML = segments.map((s) => `<span class="${s.cls}" style="width:${s.pct}%" title="${esc(s.title || "")}"></span>`).join("");
  }

  window.MOCK = { GiB, MiB, GB, now, chats, checkers, apps, groups, memory, cpu, disk, diskBreakdown, stops, tokens, history, size, sizeDecimal, pct, level, esc, cap, tokensShort, clock, sparkPath, drawSpark, drawMiniSpark, bar, todayAt, yesterdayAt };
})();
