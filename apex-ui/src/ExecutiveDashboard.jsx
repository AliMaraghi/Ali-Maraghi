import { useEffect, useState } from "react";

// Reads GET /api/dashboard - a cheap re-shaping of the real agent_telemetry data (see
// scripts/orchestrator.py's dashboard_payload()). No fabricated scores anywhere: "status" and
// "metric" are either a real file-existence check, a real stored count, or an honest
// "needs setup" / "never run" default. Each domain's single action button just opens the
// Swarm Command Center panel (the one place real detail already lives) rather than duplicating
// that detail here - the whole point of this view is LOW cognitive load, not a second copy of
// the same information.
const DASHBOARD_ENDPOINT = "https://api.apexcorelab.uk/api/dashboard";
const POLL_MS = 5000;

const DOMAIN_COLOR = { finance: "#7dffb0", academic: "#5fe3ff", dating: "#b98fff" };
const DOMAIN_ICON = { finance: "\u{1F4B0}", academic: "\u{1F4D6}", dating: "\u{1F49C}" };
const COPY = {
  en: { title: "Executive Dashboard", whereWasI: "Where was I?", finance: "Finance", academic: "Academic",
        dating: "Dating", lastThing: "Last thing you did:", nothingYet: "Nothing yet this session." },
  fa: { title: "داشبورد مدیریتی", whereWasI: "کجا بودیم؟", finance: "مالی", academic: "آکادمیک",
        dating: "دیتینگ", lastThing: "آخرین کاری که کردید:", nothingYet: "هنوز در این جلسه کاری نشده." },
};

function DomainCard({ domain, data, lang, onAction }) {
  if (!data) return null;
  const color = DOMAIN_COLOR[domain];
  return (
    <div style={{
      border: `1px solid ${color}55`, borderRadius: 12, padding: 20, flex: 1, minWidth: 220,
      background: "rgba(255,255,255,0.03)", display: "flex", flexDirection: "column", gap: 10,
    }}>
      <div style={{ fontSize: 28 }}>{DOMAIN_ICON[domain]}</div>
      <div style={{ fontSize: 18, fontWeight: 700 }}>{COPY[lang][domain]}</div>
      <div style={{
        fontSize: 13, padding: "2px 8px", borderRadius: 999, alignSelf: lang === "fa" ? "flex-end" : "flex-start",
        background: `${color}22`, color,
      }}>
        {data.status}
      </div>
      <div style={{ fontSize: 16, opacity: 0.9, minHeight: 40 }}>
        {lang === "fa" ? data.metric_fa : data.metric_en}
      </div>
      <button
        onClick={() => onAction(domain)}
        style={{
          marginTop: "auto", fontSize: 16, fontWeight: 700, padding: "12px 16px", borderRadius: 8,
          border: "none", background: color, color: "#05060a", cursor: "pointer",
        }}
      >
        {lang === "fa" ? data.action_fa : data.action_en}
      </button>
    </div>
  );
}

export default function ExecutiveDashboard({ onOpenSwarmPanel, lastAction }) {
  const [lang, setLang] = useState("en");
  const [data, setData] = useState(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(DASHBOARD_ENDPOINT);
        if (!res.ok) throw new Error(String(res.status));
        const json = await res.json();
        if (!cancelled) { setData(json); setUnreachable(false); }
      } catch {
        if (!cancelled) setUnreachable(true);
      }
    };
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  const t = COPY[lang];
  const dir = lang === "fa" ? "rtl" : "ltr";

  return (
    <div dir={dir} style={{
      position: "absolute", inset: 0, background: "#0a0e1a", color: "#ffffff",
      fontFamily: "system-ui, sans-serif", padding: 24, overflowY: "auto", fontSize: 16,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <h1 style={{ fontSize: 22, margin: 0 }}>{t.title}</h1>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onOpenSwarmPanel} style={{
            fontSize: 14, padding: "8px 14px", borderRadius: 8, border: "1px solid #3a7a90",
            background: "transparent", color: "#fff", cursor: "pointer",
          }}>
            {t.whereWasI}
          </button>
          <button onClick={() => setLang(lang === "en" ? "fa" : "en")} style={{
            fontSize: 14, padding: "8px 14px", borderRadius: 8, border: "1px solid #3a7a90",
            background: "transparent", color: "#fff", cursor: "pointer",
          }}>
            {lang === "en" ? "فارسی" : "English"}
          </button>
        </div>
      </div>

      {lastAction && (
        <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 16 }}>
          {t.lastThing} {lastAction}
        </div>
      )}
      {!lastAction && (
        <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>{t.nothingYet}</div>
      )}

      {unreachable && (
        <div style={{ color: "#ff8a8a", marginBottom: 16 }}>
          {lang === "fa" ? "داشبورد در دسترس نیست." : "Dashboard unreachable."}
        </div>
      )}

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {data && (["finance", "academic", "dating"]).map((domain) => (
          <DomainCard key={domain} domain={domain} data={data[domain]} lang={lang} onAction={onOpenSwarmPanel} />
        ))}
      </div>
    </div>
  );
}
