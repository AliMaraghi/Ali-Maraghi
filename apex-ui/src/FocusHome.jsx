// Focus home: the dashboard's main screen, designed around one rule - show ONE next thing.
//
// Why it looks like this (deliberate choices for an ADHD brain, not decoration):
//  - "الان" card: a single next action picked by fixed priority rules below, with one button.
//    No list to choose from means no choice paralysis.
//  - Brain-dump box: a thought can be parked the second it appears, so it stops circling.
//  - Everything else is folded shut and remembers how you left it. Nothing moves on its own.
//  - Focus mode hides all of it except the one card.
//  - Time is always shown as "how long ago", and a waiting answer shows a running clock,
//    because "about a minute" is invisible without one.
//  - One column, large type, one accent colour. Amber is used only when something needs you.
// Every number on this screen comes from /api/dashboard; nothing here is invented or estimated.
import { useEffect, useRef, useState } from "react";

const C = { bg: "#0b0f17", card: "#121a29", line: "#22304a", text: "#eef2f8", muted: "#93a1b8",
            accent: "#7dd3fc", need: "#fbbf24", ok: "#86efac", bad: "#fca5a5" };
const FONT = 'Vazirmatn, "Segoe UI", Tahoma, system-ui, sans-serif';

const T = {
  fa: {
    morning: "صبح بخیر", noon: "ظهر بخیر", evening: "عصر بخیر", night: "شب بخیر",
    now: "الان", calm: "چیزی فوری نیست", calmBody: "هیچ‌چیز منتظر تصمیم تو نیست. اگر فکری در سرت می‌چرخد، همین پایین بنویسش.",
    approvals: (n) => `${n.toLocaleString("fa-IR")} پیش‌نویس منتظر تأیید توست`, approvalsBody: "تا تأیید نکنی هیچ‌چیز فرستاده یا اجرا نمی‌شود.", approvalsBtn: "دیدن و تصمیم‌گیری",
    budgetOut: "بودجهٔ این ماه تمام شد", budgetOutBody: "تا اول ماه بعد هیچ هزینه‌ای انجام نمی‌شود. مدل محلی همچنان رایگان کار می‌کند.",
    budgetWarn: "بیش از ۸۰٪ بودجهٔ ماه خرج شده", budgetWarnBody: "هنوز کار می‌کند؛ فقط خواستم بدانی.",
    event: "یک رویداد برایت پیدا شد", eventBtn: "دیدن رویداد",
    offline: "به سرور وصل نیستم", offlineBody: "داده‌ها تازه نیستند. چند ثانیهٔ دیگر خودم دوباره امتحان می‌کنم.",
    capturePh: "هر چه در ذهنت است بنویس… بعد رهایش کن", send: "بفرست", thinking: "دارم فکر می‌کنم", thinkingHint: "مدل روی سرور خودت اجرا می‌شود؛ معمولاً حدود یک دقیقه.",
    captureErr: "جواب نیامد. نوشته‌ات از بین نرفته؛ دوباره بفرست.",
    waiting: "منتظر تو", budget: "بودجهٔ ماه", scout: "دیده‌بان", none: "هیچ", of: "از", events: "رویداد", never: "هنوز اجرا نشده",
    focusOn: "حالت تمرکز", focusOff: "نمایش همه", chat: "گفت‌وگو", lang: "English",
    secAuto: "کارهای خودکار", autoModel: "مدل", autoModelCloud: "مدل ابری", autoScout: "دیده‌بان فرصت", autoBrief: "گزارش صبح", autoGmail: "هم‌گام‌سازی Gmail", autoBackup: "پشتیبان در Drive", autoNext: "بعدی", autoOn: "روشن", autoOff: "خاموش", autoFail: "خطا", autoLate: "دیر شده", autoEvery4: "هر ۴ ساعت", autoDaily7: "هر روز ۷ صبح", autoDaily: "روزی یک بار", autoNotSet: "راه‌اندازی نشده", secScout: "رویدادها و فرصت‌ها", secBrief: "گزارش صبح", secAreas: "حوزه‌ها", secWhere: "کجا بودم؟",
    noBrief: "هنوز گزارشی ساخته نشده. هر روز ساعت ۷ صبح ساخته می‌شود.", nothingYet: "در این نشست هنوز کاری نکرده‌ای.",
    job: "شغل", market: "بازار", noEvents: "در گروه‌های تو رویدادی پیدا نشد.", needsReed: "جست‌وجوی شغل به کلید رایگان Reed نیاز دارد.",
    info: "اطلاع‌رسانی است، نه توصیهٔ مالی", free: "مدل محلی: بدون هزینه", ago: "پیش", open: "باز کردن", agents: "وضعیت عامل‌ها",
  },
  en: {
    morning: "Good morning", noon: "Good afternoon", evening: "Good evening", night: "Good evening",
    now: "Now", calm: "Nothing urgent", calmBody: "Nothing is waiting on a decision from you. If a thought is circling, park it below.",
    approvals: (n) => `${n} draft${n === 1 ? "" : "s"} waiting for your approval`, approvalsBody: "Nothing is sent or run until you approve it.", approvalsBtn: "Review and decide",
    budgetOut: "This month's budget is used up", budgetOutBody: "No spending until next month. The local model still works for free.",
    budgetWarn: "Over 80% of this month's budget is used", budgetWarnBody: "Still working; just so you know.",
    event: "An event was found for you", eventBtn: "See the event",
    offline: "Can't reach the server", offlineBody: "The figures are not fresh. I'll retry by myself in a few seconds.",
    capturePh: "Write whatever is on your mind… then let it go", send: "Send", thinking: "Thinking", thinkingHint: "The model runs on your own server; usually about a minute.",
    captureErr: "No answer came back. Your text is still here; send it again.",
    waiting: "Waiting on you", budget: "Month's budget", scout: "Scout", none: "None", of: "of", events: "events", never: "not run yet",
    focusOn: "Focus mode", focusOff: "Show everything", chat: "Chat", lang: "فارسی",
    secAuto: "Runs by itself", autoModel: "Model", autoModelCloud: "Cloud model", autoScout: "Opportunity scout", autoBrief: "Morning briefing", autoGmail: "Gmail sync", autoBackup: "Drive backup", autoNext: "next", autoOn: "on", autoOff: "off", autoFail: "failed", autoLate: "overdue", autoEvery4: "every 4 hours", autoDaily7: "daily at 7am", autoDaily: "once a day", autoNotSet: "not set up", secScout: "Events and openings", secBrief: "Morning briefing", secAreas: "Areas", secWhere: "Where was I?",
    noBrief: "No briefing yet. One is written every day at 7am.", nothingYet: "Nothing done yet this session.",
    job: "Job", market: "Market", noEvents: "No upcoming events found in your groups.", needsReed: "Job search needs a free Reed API key.",
    info: "Information, not financial advice", free: "Local model: no cost", ago: "ago", open: "Open", agents: "Agent status",
  },
};

function remember(key, fallback) {
  try { const v = window.localStorage.getItem("apex." + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
}
function store(key, value) { try { window.localStorage.setItem("apex." + key, JSON.stringify(value)); } catch { /* private mode: fine */ } }

export function useRemembered(key, fallback) {
  const [value, setValue] = useState(() => remember(key, fallback));
  return [value, (next) => { setValue(next); store(key, next); }];
}

function num(n, lang) { return Number(n).toLocaleString(lang === "fa" ? "fa-IR" : "en-GB"); }
function pounds(pence, lang) {
  return (pence / 100).toLocaleString(lang === "fa" ? "fa-IR" : "en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (lang === "fa" ? " پوند" : " GBP");
}
function ago(seconds, lang) {
  if (!seconds) return "";
  const diff = Math.max(0, Date.now() / 1000 - seconds);
  const rtf = new Intl.RelativeTimeFormat(lang === "fa" ? "fa" : "en", { numeric: "auto" });
  if (diff < 3600) return rtf.format(-Math.max(1, Math.round(diff / 60)), "minute");
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), "hour");
  return rtf.format(-Math.round(diff / 86400), "day");
}

// The ONE thing. Fixed priority, top wins; no scoring, no model.
function pickNow(data, unreachable, t) {
  if (unreachable && !data) return { tone: "bad", title: t.offline, body: t.offlineBody };
  const budget = data && data.budget, briefing = data && data.briefing, scout = data && data.scout;
  if (budget && budget.exhausted) return { tone: "need", title: t.budgetOut, body: t.budgetOutBody };
  const pending = briefing && Array.isArray(briefing.proposals) ? briefing.proposals.length : 0;
  if (pending > 0) return { tone: "need", title: t.approvals(pending), body: t.approvalsBody, href: "https://console.apexcorelab.uk/", action: t.approvalsBtn };
  if (budget && budget.warning) return { tone: "need", title: t.budgetWarn, body: t.budgetWarnBody };
  const event = scout && scout.events && scout.events.picked && scout.events.picked[0];
  if (event) return { tone: "ok", title: t.event, body: [event.title, event.start, event.location].filter(Boolean).join(" · "),
                      href: event.url && /^https:\/\//.test(event.url) ? event.url : null, action: t.eventBtn, ltr: true };
  return { tone: "ok", title: t.calm, body: t.calmBody };
}

function Card({ children, tone, style }) {
  const edge = tone === "need" ? C.need : tone === "bad" ? C.bad : C.line;
  return <div style={{ background: C.card, border: `1px solid ${edge}`, borderRadius: 20, padding: 22, ...style }}>{children}</div>;
}

function Section({ id, title, hint, children }) {
  const [open, setOpen] = useRemembered("open." + id, false);
  return (
    <div style={{ borderTop: `1px solid ${C.line}` }}>
      <button onClick={() => setOpen(!open)} aria-expanded={open} style={{
        width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, padding: "18px 4px",
        background: "none", border: "none", color: C.text, fontFamily: FONT, fontSize: 18, fontWeight: 600, cursor: "pointer", textAlign: "start",
      }}>
        <span>{title}{hint ? <span style={{ color: C.muted, fontWeight: 400, fontSize: 14, marginInlineStart: 10 }}>{hint}</span> : null}</span>
        <span aria-hidden="true" style={{ color: C.muted, transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}>‹</span>
      </button>
      {open && <div style={{ padding: "0 4px 20px" }}>{children}</div>}
    </div>
  );
}

function Capture({ lang, t }) {
  const [text, setText] = useState("");
  const [state, setState] = useState("idle");            // idle | waiting | error
  const [reply, setReply] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const timer = useRef(null);
  useEffect(() => () => clearInterval(timer.current), []);
  const send = async () => {
    const body = text.trim();
    if (!body || state === "waiting") return;
    setState("waiting"); setReply(""); setElapsed(0);
    const started = Date.now();
    timer.current = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
                                              body: JSON.stringify({ text: body.slice(0, 1200), session_id: "focus-home" }) });
      if (!res.ok) throw new Error(String(res.status));
      const json = await res.json();
      setReply(String(json.reply || "")); setText(""); setState("idle");
    } catch { setState("error"); }
    clearInterval(timer.current);
  };
  return (
    <Card style={{ padding: 16 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} dir="auto" placeholder={t.capturePh}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }}
                  style={{ flex: 1, resize: "vertical", minHeight: 52, background: "transparent", color: C.text, border: "none", outline: "none",
                           fontFamily: FONT, fontSize: 17, lineHeight: 1.7 }} />
        <button onClick={send} disabled={state === "waiting" || !text.trim()} style={{
          padding: "12px 20px", borderRadius: 14, border: "none", fontFamily: FONT, fontSize: 16, fontWeight: 700,
          background: state === "waiting" || !text.trim() ? C.line : C.accent, color: "#06202c", cursor: state === "waiting" ? "wait" : "pointer",
        }}>{t.send}</button>
      </div>
      {state === "waiting" && (
        <div style={{ marginTop: 12, color: C.muted, fontSize: 15 }} role="status">
          {t.thinking} · {num(elapsed, lang)}″ <span style={{ opacity: 0.7 }}>— {t.thinkingHint}</span>
        </div>
      )}
      {state === "error" && <div style={{ marginTop: 12, color: C.bad, fontSize: 15 }}>{t.captureErr}</div>}
      {reply && <div dir="auto" style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${C.line}`, whiteSpace: "pre-wrap", lineHeight: 1.8 }}>{reply}</div>}
    </Card>
  );
}

// One line per job that runs without the owner: when it last recorded something, and whether
// that is later than its own schedule allows. Times come from the journal, never from a guess.
function AutoRows({ auto, t, lang }) {
  if (!auto) return <div style={{ color: C.muted }}>—</div>;
  const nowS = Date.now() / 1000;
  const late = (last, every) => last && nowS - last > every * 1.5;
  const rows = [
    [t.autoModel, auto.local_model ? auto.model : t.autoModelCloud, null, false],
    [t.autoScout, auto.scout_last ? ago(auto.scout_last, lang) : t.never, t.autoEvery4, late(auto.scout_last, auto.scout_interval || 14400)],
    [t.autoBrief, auto.briefing_last ? ago(auto.briefing_last, lang) : t.never, t.autoDaily7, late(auto.briefing_last, 86400)],
    [t.autoGmail, !auto.gmail ? t.autoNotSet : !auto.gmail.enabled ? t.autoOff
      : auto.gmail.failures ? `${t.autoFail} ×${num(auto.gmail.failures, lang)}` : t.autoOn, null, !!(auto.gmail && auto.gmail.failures)],
    [t.autoBackup, !auto.backup ? t.autoNotSet : auto.backup.last_success ? ago(auto.backup.last_success, lang) : t.autoFail,
      t.autoDaily, !!(auto.backup && (auto.backup.state !== "UPLOADED" || late(auto.backup.last_success, 86400)))],
  ];
  return rows.map(([label, value, hint, warn]) => (
    <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "9px 0", borderBottom: `1px solid ${C.line}` }}>
      <div>{label}{hint ? <span style={{ color: C.muted, fontSize: 13 }}> · {hint}</span> : null}</div>
      <div dir="auto" style={{ color: warn ? C.need : C.text, fontWeight: 600 }}>{value}{warn && value !== t.autoFail ? ` · ${t.autoLate}` : ""}</div>
    </div>
  ));
}

function Stat({ label, value, sub, tone }) {
  return (
    <div style={{ flex: "1 1 150px", background: C.card, border: `1px solid ${C.line}`, borderRadius: 16, padding: "14px 16px" }}>
      <div style={{ color: C.muted, fontSize: 14 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: tone === "need" ? C.need : C.text }}>{value}</div>
      {sub ? <div style={{ color: C.muted, fontSize: 13, marginTop: 4 }}>{sub}</div> : null}
    </div>
  );
}

export default function FocusHome({ lang, setLang, data, unreachable, lastAction, areas, onOpenChat, onOpenAgents }) {
  const t = T[lang];
  const [focus, setFocus] = useRemembered("focus", false);
  const now = pickNow(data, unreachable, t);
  const hour = new Date().getHours();
  const hello = hour < 5 ? t.night : hour < 12 ? t.morning : hour < 17 ? t.noon : hour < 21 ? t.evening : t.night;
  const gregorian = new Date().toLocaleDateString("en-GB", { weekday: lang === "fa" ? undefined : "long", day: "numeric", month: "long" });
  const today = lang === "fa"
    ? new Date().toLocaleDateString("fa-IR", { weekday: "long", day: "numeric", month: "long" }) + " (" + gregorian + ")"
    : gregorian;
  const budget = data && data.budget, scout = data && data.scout, briefing = data && data.briefing;
  const pending = briefing && Array.isArray(briefing.proposals) ? briefing.proposals.length : 0;
  const events = scout && scout.events, wealth = scout && scout.wealth;
  const eventCount = events && events.picked ? events.picked.length : 0;
  const pill = { padding: "9px 14px", borderRadius: 999, border: `1px solid ${C.line}`, background: "transparent", color: C.text,
                 fontFamily: FONT, fontSize: 14, cursor: "pointer" };
  const link = { color: C.accent, textDecoration: "none" };

  return (
    <div dir={lang === "fa" ? "rtl" : "ltr"} lang={lang} style={{
      position: "absolute", inset: 0, overflowY: "auto", background: C.bg, color: C.text, fontFamily: FONT, fontSize: 17, lineHeight: 1.7,
    }}>
      <div style={{ maxWidth: 760, margin: "0 auto", padding: "22px 18px 60px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ color: C.muted, fontSize: 14, letterSpacing: lang === "fa" ? 0 : 1 }}>APEX · {today}</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button style={{ ...pill, borderColor: focus ? C.accent : C.line, color: focus ? C.accent : C.text }} onClick={() => setFocus(!focus)} aria-pressed={focus}>
              {focus ? t.focusOff : t.focusOn}
            </button>
            <button style={pill} onClick={onOpenChat}>{t.chat}</button>
            <button style={pill} onClick={() => setLang(lang === "fa" ? "en" : "fa")}>{t.lang}</button>
          </div>
        </div>

        <h1 style={{ fontSize: 34, fontWeight: 700, margin: "26px 0 18px", lineHeight: 1.3 }}>{hello}</h1>

        <Card tone={now.tone}>
          <div style={{ color: now.tone === "need" ? C.need : now.tone === "bad" ? C.bad : C.accent, fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{t.now}</div>
          <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.45 }}>{now.title}</div>
          <div dir={now.ltr ? "auto" : undefined} style={{ color: C.muted, marginTop: 8 }}>{now.body}</div>
          {now.href && (
            <a href={now.href} target="_blank" rel="noopener noreferrer" style={{
              display: "inline-block", marginTop: 16, padding: "12px 22px", borderRadius: 14, background: now.tone === "need" ? C.need : C.accent,
              color: "#06202c", fontWeight: 700, textDecoration: "none",
            }}>{now.action}</a>
          )}
        </Card>

        <div style={{ height: 14 }} />
        <Capture lang={lang} t={t} />

        {!focus && (
          <>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "18px 0 26px" }}>
              <Stat label={t.waiting} value={pending ? num(pending, lang) : t.none} tone={pending ? "need" : null} />
              <Stat label={t.budget} tone={budget && (budget.exhausted || budget.warning) ? "need" : null}
                    value={budget ? pounds(budget.spent_pence, lang) : "—"}
                    sub={budget ? `${t.of} ${pounds(budget.cap_pence, lang)}${budget.local_model ? " · " + t.free : ""}` : null} />
              <Stat label={t.scout} value={events ? `${num(eventCount, lang)} ${t.events}` : "—"}
                    sub={events ? ago(events.generated_at, lang) : t.never} />
            </div>

            <Section id="auto" title={t.secAuto}>
              <AutoRows auto={data && data.automation} t={t} lang={lang} />
            </Section>

            <Section id="scout" title={t.secScout} hint={events ? ago(events.generated_at, lang) : null}>
              {eventCount === 0 && <div style={{ color: C.muted }}>{t.noEvents}</div>}
              {events && events.picked && events.picked.map((e, i) => (
                <div key={i} dir="auto" style={{ marginBottom: 14 }}>
                  {e.url && /^https:\/\//.test(e.url) ? <a href={e.url} target="_blank" rel="noopener noreferrer" style={link}>{e.title}</a> : e.title}
                  <div style={{ color: C.muted, fontSize: 14 }}>{[e.start, e.location, e.why].filter(Boolean).join(" · ")}</div>
                  {e.opener ? <div style={{ fontSize: 14, marginTop: 4 }}>“{e.opener}”</div> : null}
                </div>
              ))}
              {wealth && (
                <div dir="auto" style={{ marginTop: 6 }}>
                  <div style={{ color: C.muted, fontSize: 14 }}>{t.job}</div>
                  {wealth.job ? (
                    <div style={{ marginBottom: 12 }}>
                      {wealth.job.url && /^https:\/\//.test(wealth.job.url) ? <a href={wealth.job.url} target="_blank" rel="noopener noreferrer" style={link}>{wealth.job.title}</a> : wealth.job.title}
                      <div style={{ color: C.muted, fontSize: 14 }}>{[wealth.job.employer, wealth.job.location].filter(Boolean).join(" · ")}</div>
                    </div>
                  ) : <div style={{ color: C.muted, marginBottom: 12 }}>{wealth.job_status === "NEEDS_REED_KEY" ? t.needsReed : "—"}</div>}
                  {wealth.alert && (
                    <>
                      <div style={{ color: C.muted, fontSize: 14 }}>{t.market}</div>
                      {/^https:\/\//.test(wealth.alert.url || "") ? <a href={wealth.alert.url} target="_blank" rel="noopener noreferrer" style={link}>{wealth.alert.headline}</a> : wealth.alert.headline}
                      <div style={{ color: C.muted, fontSize: 14 }}>{[wealth.alert.note, wealth.alert.source, t.info].filter(Boolean).join(" · ")}</div>
                    </>
                  )}
                </div>
              )}
            </Section>

            <Section id="brief" title={t.secBrief} hint={briefing && briefing.generated_at ? ago(briefing.generated_at, lang) : null}>
              {briefing && briefing.report
                ? <div dir="auto" style={{ whiteSpace: "pre-wrap" }}>{briefing.report}</div>
                : <div style={{ color: C.muted }}>{t.noBrief}</div>}
            </Section>

            <Section id="areas" title={t.secAreas}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
                {areas.map((a) => (
                  <button key={a.id} onClick={a.onOpen} style={{
                    textAlign: "start", background: C.card, border: `1px solid ${C.line}`, borderRadius: 16, padding: 16, color: C.text,
                    fontFamily: FONT, fontSize: 16, cursor: "pointer",
                  }}>
                    <div style={{ fontSize: 24 }} aria-hidden="true">{a.icon}</div>
                    <div style={{ fontWeight: 700, marginTop: 6 }}>{a.label}</div>
                    {a.status ? <div style={{ color: C.muted, fontSize: 13, marginTop: 4 }}>{a.status}</div> : null}
                  </button>
                ))}
              </div>
            </Section>

            <Section id="where" title={t.secWhere}>
              <div dir="auto" style={{ color: lastAction ? C.text : C.muted }}>{lastAction || t.nothingYet}</div>
              <button style={{ ...pill, marginTop: 14 }} onClick={onOpenAgents}>{t.agents}</button>
            </Section>
            <div style={{ borderTop: `1px solid ${C.line}` }} />
          </>
        )}
        {unreachable && data && <div style={{ color: C.bad, fontSize: 14, marginTop: 18 }}>{t.offline}</div>}
      </div>
    </div>
  );
}
