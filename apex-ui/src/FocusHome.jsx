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
    secAuto: "کارهای خودکار", autoModel: "مدل", autoModelCloud: "مدل ابری", autoScout: "دیده‌بان فرصت", autoBrief: "گزارش صبح", autoGmail: "هم‌گام‌سازی Gmail", autoBackup: "پشتیبان در Drive", autoNext: "بعدی", autoOn: "روشن", autoOff: "خاموش", autoFail: "خطا", autoLate: "دیر شده", autoEvery4: "هر ۴ ساعت", autoDaily7: "هر روز ۷ صبح", autoDaily: "روزی یک بار", autoNotSet: "راه‌اندازی نشده", foodOver: "سقف هفتگی غذای بیرون رد شد", foodLine: (cur, cap, week) => `هفتهٔ ${week}: ${cur} از سقف ${cap}`, foodThrough: "داده تا", foodOld: "داده قدیمی است؛ صورت‌حساب تازه آپلود کن", secSpend: "خرج‌ها", spendNone: "هنوز صورت‌حسابی آپلود نشده. از «حوزه‌ها ← بانک» فایل CSV بده.", foodAvg: "میانگین ۴ هفتهٔ آخر", reedPh: "کلید Reed را اینجا بچسبان", reedSave: "ذخیره", reedSaved: "کلید ذخیره شد؛ از اجرای بعدی دیده‌بان استفاده می‌شود", tube: "وضعیت مسیر", tubeBad: "اختلال در مسیر تو", tubeGood: "همهٔ خط‌هایت عادی‌اند", spikeTitle: "یک سؤال دربارهٔ خرج", secInsight: "الگوهای پول (فقط از اعداد خودت؛ علتی ادعا نمی‌شود)", insWeeks: "هفته داده", insLinks: "هم‌حرکت‌ها", payLine: (w, hi, a, b) => `در ${w} هفتهٔ دارای داده، میانگین خرج هفته‌های پردرآمد (${hi} هفته) ${a} بود و بقیه ${b}. این فقط مقایسهٔ عددی است، علتی را نشان نمی‌دهد.`, spikePh: "هر چه دربارهٔ آن هفته به ذهنت می‌رسد…", spikeSave: "ثبت", spikeSaved: "ثبت شد", mission: "مأموریت امروز", hAi: "هوش محلی", hDb: "پایگاه داده", hEv: "دیده‌بان رویداد", hWe: "دیده‌بان پول و شغل", hAg: "گزارش روزانه", hOn: "روشن", hOff: "خاموش", hOk: "وصل", hErr: "خطا", hNever: "هنوز اجرا نشده", hCheck: "آزمون کامل سیستم", hRunning: "در حال آزمون… چند دقیقه طول می‌کشد", hStopped: "آزمون قبلی نیمه‌کاره متوقف شد؛ دوباره بزن", hPassed: "آزمون کامل: موفق", hFailed: "آزمون کامل: ناموفق در", secOpen: "صحنهٔ باز و شبانهٔ لندن", openNone: "رویداد عمومی تازه‌ای پیدا نشد.", openBrowse: "خودت باز کن (نیاز به عضویت یا ورود دارند):", secScout: "رویدادها و فرصت‌ها", secBrief: "گزارش صبح", secAreas: "حوزه‌ها", secWhere: "کجا بودم؟",
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
    secAuto: "Runs by itself", autoModel: "Model", autoModelCloud: "Cloud model", autoScout: "Opportunity scout", autoBrief: "Morning briefing", autoGmail: "Gmail sync", autoBackup: "Drive backup", autoNext: "next", autoOn: "on", autoOff: "off", autoFail: "failed", autoLate: "overdue", autoEvery4: "every 4 hours", autoDaily7: "daily at 7am", autoDaily: "once a day", autoNotSet: "not set up", foodOver: "Weekly eating-out and delivery limit exceeded", foodLine: (cur, cap, week) => `Week of ${week}: ${cur} against a limit of ${cap}`, foodThrough: "data to", foodOld: "This data is old; upload a newer statement", secSpend: "Spending", spendNone: "No statement uploaded yet. Use Areas → Banking to upload a CSV.", foodAvg: "Average of the last 4 weeks", reedPh: "Paste your Reed key here", reedSave: "Save", reedSaved: "Key saved; the scout uses it from its next run", tube: "Line status", tubeBad: "Disruption on your route", tubeGood: "All your lines are running normally", spikeTitle: "A question about spending", secInsight: "Money patterns (from your own numbers only; no cause claimed)", insWeeks: "weeks of data", insLinks: "Move together", payLine: (w, hi, a, b) => `Across ${w} weeks with data, the 3 highest-income weeks (${hi}) averaged ${a} going out, the rest ${b}. A plain comparison; it shows no cause.`, spikePh: "Anything you remember about that week…", spikeSave: "Save", spikeSaved: "Saved", mission: "Today\u2019s mission", hAi: "Local AI", hDb: "Database", hEv: "Event scout", hWe: "Wealth scout", hAg: "Daily briefing", hOn: "online", hOff: "offline", hOk: "connected", hErr: "error", hNever: "never run", hCheck: "Run full system test", hRunning: "Testing… this takes a few minutes", hStopped: "The last test was cut off; run it again", hPassed: "Full test: passed", hFailed: "Full test: failed at", secOpen: "London open-minded and night scene", openNone: "No new public events found.", openBrowse: "Open these yourself (membership or sign-in needed):", secScout: "Events and openings", secBrief: "Morning briefing", secAreas: "Areas", secWhere: "Where was I?",
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

const CAT_FA = { "Other / uncategorised": "دسته‌بندی‌نشده", "Food delivery": "سفارش غذا", "Eating out & coffee": "رستوران و قهوه", "Housing & council": "مسکن و شهرداری", "Groceries": "خرید خوراکی", "Health & fitness": "سلامت و ورزش", "Subscriptions & software": "اشتراک‌ها و نرم‌افزار", "Transport": "حمل‌ونقل", "Utilities & telecoms": "قبض‌ها و تلفن", "Shopping": "خرید", "Cash": "نقد", "Interest & bank fees": "بهره و کارمزد بانک" };
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
// When one week of food spending runs well above the four before it, ask - once per week -
// and keep the owner's own answer. The question states figures only; it suggests no reason.
function SpikeCheckin({ spend, t }) {
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  const spike = spend && spend.spike;
  if (!spike || (spend.checkin && spend.checkin.week_start === spike.week_start)) return null;
  const save = () => fetch("/api/spend/checkin", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ week: spike.week_start, note }) })
    .then((r) => { if (r.ok) setSaved(true); }).catch(() => {});
  return (
    <Card style={{ marginTop: 14 }}>
      <div style={{ color: C.accent, fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{t.spikeTitle}</div>
      <div dir="ltr" style={{ lineHeight: 1.6 }}>{spike.question}</div>
      {saved ? <div style={{ color: C.ok, marginTop: 10 }}>{t.spikeSaved}</div> : (
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t.spikePh} maxLength={600} dir="auto"
                 style={{ flex: 1, minWidth: 0, padding: "8px 10px", borderRadius: 10, border: `1px solid ${C.line}`, background: C.bg, color: C.text, fontFamily: FONT }} />
          <button onClick={save} disabled={!note.trim()} style={{ padding: "8px 14px", borderRadius: 10, border: `1px solid ${C.line}`, background: "transparent", color: C.text, cursor: "pointer", fontFamily: FONT }}>{t.spikeSave}</button>
        </div>
      )}
    </Card>
  );
}

const gbp = (pence) => "£" + (pence / 100).toFixed(2);

// The owner's Reed job-search key goes straight from this box to his own server. It is never
// shown again; the box only reports whether a key is set.
function ReedKey({ t }) {
  const [value, setValue] = useState("");
  const [done, setDone] = useState(false);
  const save = () => fetch("/api/settings/reed_key", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: value.trim() }) })
    .then((r) => { if (r.ok) { setDone(true); setValue(""); } }).catch(() => {});
  if (done) return <div style={{ color: C.ok, fontSize: 14 }}>{t.reedSaved}</div>;
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
      <input type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} placeholder={t.reedPh} dir="ltr"
             style={{ flex: 1, minWidth: 0, padding: "8px 10px", borderRadius: 10, border: `1px solid ${C.line}`, background: C.bg, color: C.text }} />
      <button onClick={save} disabled={!value.trim()} style={{ padding: "8px 14px", borderRadius: 10, border: `1px solid ${C.line}`, background: "transparent", color: C.text, cursor: "pointer", fontFamily: FONT }}>{t.reedSave}</button>
    </div>
  );
}

function pickNow(data, unreachable, t) {
  if (unreachable && !data) return { tone: "bad", title: t.offline, body: t.offlineBody };
  const budget = data && data.budget, briefing = data && data.briefing, scout = data && data.scout;
  if (budget && budget.exhausted) return { tone: "need", title: t.budgetOut, body: t.budgetOutBody };
  const pending = briefing && Array.isArray(briefing.proposals) ? briefing.proposals.length : 0;
  if (pending > 0) return { tone: "need", title: t.approvals(pending), body: t.approvalsBody, href: "https://console.apexcorelab.uk/", action: t.approvalsBtn };
  if (budget && budget.warning) return { tone: "need", title: t.budgetWarn, body: t.budgetWarnBody };
  const tube = scout && scout.commute;
  const tubeFresh = tube && tube.generated_at && Date.now() / 1000 - tube.generated_at < 5 * 3600;
  if (tubeFresh && tube.lines && tube.lines.some((l) => !l.good)) return { tone: "need", title: t.tubeBad, ltr: true,
    body: tube.lines.filter((l) => !l.good).map((l) => `${l.name}: ${l.state}`).join(" · "),
    quote: (tube.lines.find((l) => !l.good && l.reason) || {}).reason || null };
  const food = scout && scout.spend && scout.spend.food_alert;
  if (food && food.exceeded && !food.stale) return { tone: "need", title: t.foodOver, ltr: true,
    body: `${t.foodLine(gbp(food.current_pence), gbp(food.cap_pence), food.week_start)} · ${t.foodThrough} ${food.data_through}` };
  const mission = scout && scout.mission && scout.mission.event;
  if (mission) return { tone: "ok", title: t.mission, body: [mission.title, mission.start, mission.location].filter(Boolean).join(" · "),
                        quote: scout.mission.ice_breaker || null,
                        href: mission.url && /^https:\/\//.test(mission.url) ? mission.url : null, action: t.eventBtn, ltr: true };
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

// The heartbeat: five parts, each green only on evidence (a live probe or a recent record).
// Polls every 10 seconds; if the health endpoint itself cannot be reached every dot is red.
function Health({ t, lang }) {
  const [health, setHealth] = useState(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const poll = () => fetch("/api/system_health", { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then((j) => { if (!cancelled) { setHealth(j); setDown(false); } })
      .catch(() => { if (!cancelled) setDown(true); });
    poll();
    const timer = setInterval(poll, 10000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);
  const checks = (!down && health && health.checks) || {};
  const run = (c) => (c && c.last_run ? ago(c.last_run, lang) : t.hNever);
  const items = [
    [t.hAi, checks.local_ai, (c) => (c && c.ok ? t.hOn : t.hOff)],
    [t.hDb, checks.database, (c) => (c && c.ok ? t.hOk : t.hErr)],
    [t.hEv, checks.event_scout, run], [t.hWe, checks.wealth_scout, run], [t.hAg, checks.agent_loop, run],
  ];
  const e2e = !down && health && health.e2e;
  const failedStep = e2e && e2e.state === "failed" && e2e.steps && e2e.steps.find((s) => !s.ok);
  const start = () => fetch("/api/system_check", { method: "POST" }).then(() => setHealth((h) => (h ? { ...h, e2e: { state: "running" } } : h))).catch(() => {});
  return (
    <div style={{ marginTop: 16, padding: "12px 14px", border: `1px solid ${C.line}`, borderRadius: 14, background: C.card }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 18px", fontSize: 14 }}>
        {items.map(([label, check, text]) => (
          <span key={label} title={(check && check.detail) || ""} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 9, height: 9, borderRadius: 9, background: check && check.ok ? C.ok : C.bad, display: "inline-block" }} />
            <span style={{ color: C.muted }}>{label}:</span> <span>{text(check)}</span>
          </span>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginTop: 10, fontSize: 13 }}>
        <button onClick={start} disabled={!!(e2e && e2e.state === "running")}
                style={{ padding: "6px 12px", borderRadius: 10, border: `1px solid ${C.line}`, background: "transparent", color: C.text, cursor: "pointer", fontFamily: FONT }}>
          {t.hCheck}
        </button>
        {e2e && e2e.state === "running" && <span style={{ color: C.need }}>{t.hRunning}</span>}
        {e2e && e2e.state === "passed" && <span style={{ color: C.ok }}>{t.hPassed} · {ago(e2e.finished, lang)}</span>}
        {failedStep && <span dir="auto" style={{ color: C.bad }}>{t.hFailed} {failedStep.name}: {failedStep.detail}</span>}
        {e2e && e2e.state === "interrupted" && <span style={{ color: C.need }}>{t.hStopped}</span>}
      </div>
    </div>
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
  const budget = data && data.budget, scout = data && data.scout, briefing = data && data.briefing, osd = data && data.os;
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

        <Health t={t} lang={lang} />

        <h1 style={{ fontSize: 34, fontWeight: 700, margin: "26px 0 18px", lineHeight: 1.3 }}>{hello}</h1>

        <Card tone={now.tone}>
          <div style={{ color: now.tone === "need" ? C.need : now.tone === "bad" ? C.bad : C.accent, fontSize: 14, fontWeight: 700, marginBottom: 6 }}>{t.now}</div>
          <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.45 }}>{now.title}</div>
          <div dir={now.ltr ? "auto" : undefined} style={{ color: C.muted, marginTop: 8 }}>{now.body}</div>
          {now.quote ? <div dir="auto" style={{ marginTop: 10, fontSize: 17 }}>“{now.quote}”</div> : null}
          {now.href && (
            <a href={now.href} target="_blank" rel="noopener noreferrer" style={{
              display: "inline-block", marginTop: 16, padding: "12px 22px", borderRadius: 14, background: now.tone === "need" ? C.need : C.accent,
              color: "#06202c", fontWeight: 700, textDecoration: "none",
            }}>{now.action}</a>
          )}
        </Card>

        <SpikeCheckin spend={scout && scout.spend} t={t} />
        {scout && scout.spend && scout.spend.payday && (
          <div style={{ marginTop: 10, color: C.muted, fontSize: 13, lineHeight: 1.6 }}>
            {t.payLine(scout.spend.payday.weeks, scout.spend.payday.high_income_weeks, gbp(scout.spend.payday.avg_out_high_income_pence), gbp(scout.spend.payday.avg_out_other_pence))}
          </div>
        )}
        {scout && scout.spend && scout.spend.insight && (scout.spend.insight.behaviour || []).length > 0 && (
          <div dir="ltr" style={{ marginTop: 14, fontSize: 13, lineHeight: 1.6 }}>
            <div style={{ color: C.muted, marginBottom: 4 }}>{t.secInsight}{scout.spend.insight.economics ? ` · ${scout.spend.insight.economics.weeks} ${t.insWeeks}` : ""}</div>
            {scout.spend.insight.behaviour.map((b) => (
              <div key={b.name} style={{ marginBottom: 6 }}><b>{b.name}</b> <span style={{ color: C.muted }}>({b.strength})</span><br />{b.evidence}</div>
            ))}
            {scout.spend.insight.graph && scout.spend.insight.graph.edges.length > 0 && (
              <div style={{ color: C.muted }}>{t.insLinks}: {scout.spend.insight.graph.edges.slice(0, 5).map((e) => `${e.a} ↔ ${e.b} (${e.r})`).join(" · ")}</div>
            )}
          </div>
        )}
        {scout && scout.commute && scout.commute.lines && scout.commute.lines.length > 0 && (
          <div dir="ltr" style={{ marginTop: 12, color: C.muted, fontSize: 14, display: "flex", flexWrap: "wrap", gap: "4px 14px" }}>
            <span>{t.tube} · {ago(scout.commute.generated_at, lang)}:</span>
            {scout.commute.lines.map((l) => <span key={l.id} style={{ color: l.good ? C.ok : C.need }}>{l.name}: {l.state}</span>)}
          </div>
        )}
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
                  {e.opener ? <div style={{ fontSize: 14, marginTop: 4 }}><span style={{ color: C.muted, fontSize: 12 }}>{lang === "fa" ? "جمله شروع (انگلیسی؛ همان که در محل می‌گویی): " : "Opener: "}</span>“{e.opener}”</div> : null}
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
                  ) : <div style={{ color: C.muted, marginBottom: 12 }}>{wealth.job_status === "NEEDS_REED_KEY" ? t.needsReed : "—"}
                      {wealth.job_status === "NEEDS_REED_KEY" && <ReedKey t={t} />}</div>}
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

            {osd && osd.cycle && (
              <Section id="os" title={lang === "fa" ? "وضعیت واقعی سیستم‌عامل" : "OS: real state"} hint={ago(osd.cycle.generated_at, lang)}>
                <div dir="ltr" style={{ fontSize: 13, lineHeight: 1.7 }}>
                  {osd.cycle.agents.map((a) => (
                    <div key={a.agent_id} style={{ display: "flex", gap: 8, padding: "4px 0", borderBottom: `1px solid ${C.line}` }}>
                      <span style={{ minWidth: 44, color: C.muted }}>{a.agent_id}</span>
                      <span style={{ minWidth: 190, color: a.state === "AUTONOMOUS_SCAN" ? C.ok : a.state === "PENDING_APPROVAL" ? C.accent || C.ok : C.need }}>{a.state}</span>
                      <span style={{ color: C.muted }}>{a.name}: {a.reason}</span>
                    </div>
                  ))}
                  {(osd.cycle.actions || []).map((a, i) => <div key={i} style={{ marginTop: 6 }}>▸ {a.task}: <b>{a.result}</b> <span style={{ color: C.muted }}>{a.detail}</span></div>)}
                  {osd.trends && osd.trends.top && osd.trends.top.length > 0 && (
                    <div style={{ marginTop: 10 }}><span style={{ color: C.muted }}>Trends ({ago(osd.trends.generated_at, lang)}): </span>
                      {osd.trends.top.slice(0, 8).map((x) => `${x.term} [${x.geos.join(",")}]`).join(" · ")}</div>
                  )}
                  {osd.people && (
                    <div style={{ marginTop: 10 }}>
                      <div><span style={{ color: C.muted }}>People graph (LinkedIn): </span>{osd.people.people} people · {osd.people.companies} companies · {osd.people.top_companies.map((c) => `${c[0]} (${c[1]})`).join(" · ")}</div>
                      {osd.people.warm_jobs.map((j, i) => <div key={i}>★ <a href={j.url} target="_blank" rel="noopener noreferrer" style={link}>{j.title}</a> — {j.company}: {j.you_know.join(", ")}</div>)}
                    </div>
                  )}
                  {osd.drafts && (osd.drafts.drafts || []).map((d, i) => (
                    <div key={i} style={{ marginTop: 8, padding: 8, border: `1px solid ${C.line}`, borderRadius: 8 }}>
                      <div style={{ color: C.muted }}>{d.state} · {d.platform} · {d.lang} · {d.angle} · {d.term}</div>
                      <div>{d.hook}</div>
                      <div style={{ color: C.muted }}>{d.beats.join(" / ")}</div>
                    </div>
                  ))}
                </div>
              </Section>
            )}
            <Section id="spend" title={t.secSpend} hint={scout && scout.spend ? scout.spend.last_date : null}>
              {(!scout || !scout.spend) && <div style={{ color: C.muted }}>{t.spendNone}</div>}
              {scout && scout.spend && scout.spend.food_alert && (() => {
                const f = scout.spend.food_alert;
                return (
                  <div dir="auto" style={{ marginBottom: 12 }}>
                    <div style={{ color: f.exceeded ? C.need : C.text, fontWeight: 700 }}>{t.foodLine(gbp(f.current_pence), gbp(f.cap_pence), f.week_start)}</div>
                    <div style={{ color: C.muted, fontSize: 14 }}>{t.foodAvg}: {gbp(f.four_week_average_pence)} · {t.foodThrough} {f.data_through}{f.stale ? ` · ${t.foodOld}` : ""}</div>
                  </div>
                );
              })()}
              {scout && scout.spend && scout.spend.totals && Object.entries(scout.spend.totals)
                .filter(([name, v]) => v.out_pence > 0 && !/^(Card payment|Failed card)/.test(name))
                .sort((a, b) => b[1].out_pence - a[1].out_pence).slice(0, 8).map(([name, v]) => (
                  <div key={name} dir="ltr" style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${C.line}` }}>
                    <span>{lang === "fa" && CAT_FA[name] ? CAT_FA[name] : name}</span><span>{gbp(v.out_pence)}</span>
                  </div>
                ))}
            </Section>

            <Section id="open" title={t.secOpen} hint={scout && scout.adult ? ago(scout.adult.generated_at, lang) : null}>
              {(!scout || !scout.adult || !scout.adult.picked || scout.adult.picked.length === 0) && <div style={{ color: C.muted }}>{t.openNone}</div>}
              {scout && scout.adult && scout.adult.picked && scout.adult.picked.map((e, i) => (
                <div key={i} dir="auto" style={{ marginBottom: 14 }}>
                  {/^https:\/\/events\.humanitix\.com\//.test(e.url || "") ? <a href={e.url} target="_blank" rel="noopener noreferrer" style={link}>{e.title}</a> : e.title}
                  <div style={{ color: C.muted, fontSize: 14 }}>{[e.start, e.location, e.address].filter(Boolean).join(" · ")}</div>
                </div>
              ))}
              <div style={{ color: C.muted, fontSize: 14, marginTop: 6 }}>{t.openBrowse}</div>
              <div dir="ltr" style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 4 }}>
                <a href="https://www.killingkittens.com/sex-parties/london-parties" target="_blank" rel="noopener noreferrer" style={link}>Killing Kittens</a>
                <a href="https://fetlife.com/events/near" target="_blank" rel="noopener noreferrer" style={link}>FetLife</a>
                <a href="https://www.fabswingers.com/" target="_blank" rel="noopener noreferrer" style={link}>FabSwingers</a>
              </div>
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
