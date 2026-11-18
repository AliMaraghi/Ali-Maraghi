import { useEffect, useRef, useState } from "react";

// The chat screen's centre: an energy core (an instrument, deliberately not a face) that changes phase with the real voice state
// (idle / listening / thinking / speaking) and, around it, one node per agent that actually
// exists in scripts/orchestrator.py's agent_telemetry(). Nothing here is decorative data:
//   - node colour      = status of that agent's LAST completed run (OK / ERROR / NEVER_RUN)
//   - dot on each link = how far that agent is through its own interval towards its next run
//   - core phase       = the same listening/thinking/speaking flags the voice loop already sets
// There is no live "currently executing" signal in the backend (see agent_telemetry's docstring),
// so no node is ever shown as "processing right now".
const TELEMETRY_ENDPOINT = "/api/agent_telemetry";
const POLL_MS = 5000;
const STATUS_COLOR = { OK: "#7dffb0", ERROR: "#ff6a6a", NEVER_RUN: "#6a7a85" };
const PHASE_COLOR = { idle: "#1f8fb0", listening: "#ff5f6d", thinking: "#b98fff", speaking: "#5fe3ff" };
const NAME_FA = {
  "A-1": "هوش راهبردی", "A-2": "پژوهش علمی", "A-3": "شواهد و راستی‌آزمایی", "A-5": "شغل و صنعت",
  "A-8": "هوش مالی", "A-10": "روابط اجتماعی", "A-15": "سلامت و طول عمر",
};
const COPY = {
  en: { idle: "Ready", listening: "Listening", thinking: "Thinking", speaking: "Speaking", unreachable: "Agent data unreachable",
        OK: "Last run OK", ERROR: "Last run failed", NEVER_RUN: "Not run yet", next: "Next run", now: "due now",
        none: "not scheduled", mins: "min", hours: "h", close: "Close", note: "Colours show each agent's last finished run, not live activity." },
  fa: { idle: "آماده", listening: "در حال شنیدن", thinking: "در حال فکر کردن", speaking: "در حال صحبت", unreachable: "داده عامل‌ها در دسترس نیست",
        OK: "آخرین اجرا موفق", ERROR: "آخرین اجرا ناموفق", NEVER_RUN: "هنوز اجرا نشده", next: "اجرای بعدی", now: "همین حالا",
        none: "زمان‌بندی نشده", mins: "دقیقه", hours: "ساعت", close: "بستن", note: "رنگ‌ها نتیجه آخرین اجرای هر عامل را نشان می‌دهند، نه فعالیت لحظه‌ای." },
};

function dueText(seconds, t) {
  if (seconds == null) return t.none;
  if (seconds <= 0) return t.now;
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `~${minutes} ${t.mins}` : `~${Math.round(minutes / 60)} ${t.hours}`;
}

function layout(count, width, height) {
  const narrow = width < 700;                      // phones: a tall ellipse so labels do not collide
  if (narrow) width -= 40;                         // the collapsed agents rail on the right edge
  const cx = width / 2, cy = height * (narrow ? 0.46 : 0.42);
  const rx = narrow ? width * 0.34 : Math.min(width * 0.38, 430), ry = narrow ? height * 0.27 : Math.min(height * 0.3, 250);
  return { cx, cy, core: Math.max(46, Math.min(width, height) * 0.085),
           points: Array.from({ length: count }, (_, i) => {
             const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(count, 1);
             return { x: cx + rx * Math.cos(angle), y: cy + ry * Math.sin(angle) };
           }) };
}

export default function CoreGraph({ listening, thinking, speaking, mouthIntensityRef, lang }) {
  const t = COPY[lang] || COPY.en;
  const canvasRef = useRef(null);
  const [agents, setAgents] = useState([]);
  const [unreachable, setUnreachable] = useState(false);
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });
  const [selected, setSelected] = useState(null);
  const phase = listening ? "listening" : speaking ? "speaking" : thinking ? "thinking" : "idle";
  const live = useRef({});
  live.current = { agents, phase, size, fetchedAt: live.current.fetchedAt };

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch(TELEMETRY_ENDPOINT);
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();
        if (!cancelled) { live.current.fetchedAt = Date.now(); setAgents(data.agents || []); setUnreachable(false); }
      } catch {
        if (!cancelled) setUnreachable(true);
      }
    };
    poll();
    const timer = setInterval(poll, POLL_MS);
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => { cancelled = true; clearInterval(timer); window.removeEventListener("resize", onResize); };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    const still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0, level = 0;
    const draw = (ms) => {
      const { agents: list, phase: now, size: s, fetchedAt } = live.current;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.width !== s.w * ratio || canvas.height !== s.h * ratio) { canvas.width = s.w * ratio; canvas.height = s.h * ratio; }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, s.w, s.h);
      const time = still ? 0 : ms / 1000;
      const g = layout(list.length, s.w, s.h);
      const color = PHASE_COLOR[now];

      // Links and their progress dots.
      list.forEach((agent, i) => {
        const p = g.points[i], tone = STATUS_COLOR[agent.status] || STATUS_COLOR.NEVER_RUN;
        ctx.save();
        ctx.strokeStyle = tone; ctx.globalAlpha = agent.status === "NEVER_RUN" ? 0.25 : 0.55;
        ctx.lineWidth = 1.4; ctx.shadowColor = tone; ctx.shadowBlur = 10;
        const gap = (g.core * 1.9) / Math.max(1, Math.hypot(p.x - g.cx, p.y - g.cy));   // stop at the outer ring, not inside the face
        const sx = g.cx + (p.x - g.cx) * gap, sy = g.cy + (p.y - g.cy) * gap;
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(p.x, p.y); ctx.stroke();
        if (agent.due_in_seconds != null && agent.interval_seconds) {
          const since = fetchedAt ? (Date.now() - fetchedAt) / 1000 : 0;
          const done = Math.max(0, Math.min(1, 1 - (agent.due_in_seconds - since) / agent.interval_seconds));
          ctx.globalAlpha = 1; ctx.fillStyle = tone; ctx.shadowBlur = 14;
          ctx.beginPath(); ctx.arc(p.x + (sx - p.x) * done, p.y + (sy - p.y) * done, 3.5, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();
      });

      // The core: breathing glow, phase rings, and a voice ring driven by the real mouth level.
      const target = now === "speaking" ? Math.max(0.25, Math.min(1, Number(mouthIntensityRef?.current) || 0.4))
        : now === "listening" ? 0.55 : now === "thinking" ? 0.35 : 0.12;
      level += (target - level) * 0.12;
      const breathe = 1 + Math.sin(time * (now === "idle" ? 1.1 : 3)) * (0.03 + level * 0.06);
      const r = g.core * breathe;
      const glow = ctx.createRadialGradient(g.cx, g.cy, r * 0.1, g.cx, g.cy, r * 2.6);
      glow.addColorStop(0, color + "cc"); glow.addColorStop(0.35, color + "33"); glow.addColorStop(1, color + "00");
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(g.cx, g.cy, r * 2.6, 0, Math.PI * 2); ctx.fill();
      ctx.save();
      ctx.strokeStyle = color; ctx.shadowColor = color; ctx.shadowBlur = 18; ctx.lineWidth = 2;
      ctx.beginPath();
      for (let k = 0; k <= 120; k += 1) {
        const a = (k / 120) * Math.PI * 2;
        const wave = Math.sin(a * 6 + time * 4) * Math.sin(a * 3 - time * 2.3) * level * r * 0.28;
        const x = g.cx + (r + wave) * Math.cos(a), y = g.cy + (r + wave) * Math.sin(a);
        if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath(); ctx.stroke();
      [1.35, 1.7].forEach((scale, index) => {
        const spin = time * (now === "thinking" ? 2.4 : 0.35) * (index ? -1 : 1);
        ctx.globalAlpha = 0.55 - index * 0.2; ctx.lineWidth = 1.5;
        for (let arc = 0; arc < 3; arc += 1) {
          const start = spin + (arc * Math.PI * 2) / 3;
          ctx.beginPath(); ctx.arc(g.cx, g.cy, r * scale, start, start + (now === "thinking" ? 1.1 : 1.7)); ctx.stroke();
        }
      });
      if (now === "listening") {
        const ripple = (time * 0.8) % 1;
        ctx.globalAlpha = 1 - ripple; ctx.beginPath(); ctx.arc(g.cx, g.cy, r * (2.4 - ripple * 1.2), 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();
      // Instrument core, no face: a tick bezel, a radial level meter driven by the real voice
      // level, and a small nucleus with crosshairs.
      ctx.save();
      ctx.strokeStyle = color; ctx.shadowColor = color; ctx.shadowBlur = 8; ctx.lineCap = "butt";
      for (let k = 0; k < 72; k += 1) {
        const a = (k / 72) * Math.PI * 2 + time * 0.08, long = k % 6 === 0;
        ctx.globalAlpha = long ? 0.8 : 0.35; ctx.lineWidth = long ? 1.6 : 1;
        ctx.beginPath();
        ctx.moveTo(g.cx + r * 1.98 * Math.cos(a), g.cy + r * 1.98 * Math.sin(a));
        ctx.lineTo(g.cx + r * (long ? 2.12 : 2.06) * Math.cos(a), g.cy + r * (long ? 2.12 : 2.06) * Math.sin(a));
        ctx.stroke();
      }
      ctx.lineWidth = 2; ctx.shadowBlur = 10;
      for (let k = 0; k < 56; k += 1) {
        const a = (k / 56) * Math.PI * 2 - Math.PI / 2;
        const shape = 0.5 + 0.5 * Math.sin(k * 1.7 + time * 7) * Math.sin(k * 0.6 - time * 3.1);
        const bar = r * (0.05 + level * 0.42 * shape);
        ctx.globalAlpha = 0.35 + level * 0.6;
        ctx.beginPath();
        ctx.moveTo(g.cx + r * 0.52 * Math.cos(a), g.cy + r * 0.52 * Math.sin(a));
        ctx.lineTo(g.cx + (r * 0.52 + bar) * Math.cos(a), g.cy + (r * 0.52 + bar) * Math.sin(a));
        ctx.stroke();
      }
      ctx.globalAlpha = 0.5; ctx.lineWidth = 1;
      [[1, 0], [0, 1]].forEach(([dx, dy]) => {
        ctx.beginPath(); ctx.moveTo(g.cx - dx * r * 0.44, g.cy - dy * r * 0.44); ctx.lineTo(g.cx - dx * r * 0.14, g.cy - dy * r * 0.14);
        ctx.moveTo(g.cx + dx * r * 0.14, g.cy + dy * r * 0.14); ctx.lineTo(g.cx + dx * r * 0.44, g.cy + dy * r * 0.44); ctx.stroke();
      });
      ctx.globalAlpha = 1; ctx.fillStyle = "#eaffff"; ctx.shadowBlur = 22;
      ctx.beginPath(); ctx.arc(g.cx, g.cy, r * (0.07 + level * 0.06), 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      if (!still) frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    const redraw = still ? setInterval(() => requestAnimationFrame(draw), 1000) : null;
    return () => { cancelAnimationFrame(frame); if (redraw) clearInterval(redraw); };
  }, [mouthIntensityRef]);

  const g = layout(agents.length, size.w, size.h);
  const narrow = size.w < 700;
  const chosen = agents.find((agent) => agent.agent_id === selected);
  return (
    <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse at 50% 42%, #071019 0%, #020305 72%)" }}
         dir={lang === "fa" ? "rtl" : "ltr"}>
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
      <div style={{ position: "absolute", left: g.cx, top: g.cy + g.core * 2.45, transform: "translateX(-50%)",
                    fontSize: 11, letterSpacing: lang === "fa" ? 0 : 3, textTransform: "uppercase", fontFamily: "ui-monospace, monospace", color: PHASE_COLOR[phase], textShadow: `0 0 10px ${PHASE_COLOR[phase]}` }}>
        {t[phase]}
      </div>
      {agents.map((agent, i) => {
        const tone = STATUS_COLOR[agent.status] || STATUS_COLOR.NEVER_RUN;
        return (
          <button key={agent.agent_id} onClick={() => setSelected(selected === agent.agent_id ? null : agent.agent_id)}
                  style={{
                    position: "absolute", left: g.points[i].x, top: g.points[i].y, transform: "translate(-50%, -50%)",
                    minWidth: narrow ? 0 : 96, maxWidth: narrow ? 104 : 150, padding: narrow ? "5px 7px" : "8px 10px",
                    borderRadius: 3, cursor: "pointer",
                    background: "rgba(3,7,12,0.9)", color: "#dff6ff", fontSize: narrow ? 10.5 : 12, lineHeight: 1.35,
                    border: `1px solid ${tone}`, boxShadow: `0 0 14px ${tone}55`, fontFamily: "inherit",
                  }}>
            <div style={{ fontWeight: 700 }}>{lang === "fa" ? NAME_FA[agent.agent_id] || agent.name : agent.name}</div>
            <div style={{ color: tone, fontSize: narrow ? 9.5 : 11 }}>{t[agent.status] || agent.status}</div>
          </button>
        );
      })}
      {chosen && (
        <div style={{ position: "absolute", left: "50%", top: narrow ? 150 : 70, zIndex: 3, transform: "translateX(-50%)", width: "min(420px, 88vw)",
                      background: "rgba(5,10,16,0.95)", border: "1px solid #2a6f8a", borderRadius: 12, padding: 14, fontSize: 13, color: "#dff6ff" }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>{lang === "fa" ? NAME_FA[chosen.agent_id] || chosen.name : chosen.name}</div>
          <div style={{ opacity: 0.85, marginTop: 6 }} dir="ltr">{chosen.current_task}</div>
          <div style={{ marginTop: 6 }}>{t.next}: {dueText(chosen.due_in_seconds, t)}</div>
          {chosen.last_error && <div style={{ color: "#ff8a8a", marginTop: 6 }} dir="ltr">{String(chosen.last_error).slice(0, 200)}</div>}
          <button onClick={() => setSelected(null)} style={{ marginTop: 10, padding: "4px 12px", borderRadius: 6, cursor: "pointer",
                                                            background: "transparent", color: "#dff6ff", border: "1px solid #2a6f8a" }}>{t.close}</button>
        </div>
      )}
      <div style={{ position: "absolute", left: "50%", bottom: 8, transform: "translateX(-50%)", width: "90vw", textAlign: "center", fontSize: 10.5, opacity: 0.5 }}>
        {unreachable ? t.unreachable : t.note}
      </div>
    </div>
  );
}
