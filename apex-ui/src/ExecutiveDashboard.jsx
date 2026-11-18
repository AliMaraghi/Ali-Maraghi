import { useEffect, useState } from "react";
import FocusHome, { useRemembered } from "./FocusHome.jsx";

// Reads GET /api/dashboard - a cheap re-shaping of the real agent_telemetry data (see
// scripts/orchestrator.py's dashboard_payload()). No fabricated scores anywhere: "status" and
// "metric" are either a real file-existence check, a real stored count, or an honest
// "needs setup" / "never run" default. Each domain card opens a modal with real detail or a
// real action - no second parallel "Swarm Command Center" copy of the same information.
const DASHBOARD_ENDPOINT = "/api/dashboard";
const ACADEMIC_ENDPOINT = "/api/academic/latest";
const DATING_DRAFT_ENDPOINT = "/api/dating/draft";
const DATING_BULK_ENDPOINT = "/api/dating/bulk_queue";
const BANKING_PARSE_ENDPOINT = "/api/banking/parse";
const WEALTH_ANALYZE_ENDPOINT = "/api/wealth/analyze";
// Google OAuth is deliberately mounted ONLY on console.apexcorelab.uk (the one domain with a
// real Cloudflare Access gate), never on this public dashboard - see
// docs/apex_status/ for why. This is a link to that already-working page, not a second,
// unauthenticated way to start the same OAuth flow.
const GOOGLE_CONSOLE_URL = "https://console.apexcorelab.uk/connections/google";
const POLL_MS = 5000;

const DOMAINS = ["finance", "academic", "dating", "banking"];
const DOMAIN_COLOR = { finance: "#7dffb0", academic: "#5fe3ff", dating: "#b98fff", banking: "#ffd166" };
const DOMAIN_ICON = { finance: "\u{1F4B0}", academic: "\u{1F4D6}", dating: "\u{1F49C}", banking: "\u{1F3E6}" };
const COPY = {
  en: { title: "Executive Dashboard", whereWasI: "Where was I?", finance: "Finance", academic: "Academic",
        dating: "Dating", banking: "Banking", lastThing: "Last thing you did:", nothingYet: "Nothing yet this session.",
        howItWorks: "How it works", howItJudges: "How it judges (read this before trusting any number)",
        close: "Close",
        datingBioLabel: "Paste a profile bio (nothing is stored or sent anywhere):",
        datingGenerate: "Generate Drafts", datingGenerating: "Generating...", datingEmpty: "Paste some text first.",
        bankingExplain: "Open Banking needs real owner consent via a reviewed account-information provider (e.g. TrueLayer). "
          + "No aggregator is configured yet, so there is nothing to connect to - this button is a preview of the setup step, not a live connection.",
        bankingConnect: "Connect TrueLayer", bankingAlert: "Not connected: no aggregator API key is configured on this server yet. See docs/apex_status/BANKING_SCAFFOLD_REPORT.md.",
        academicFetching: "Fetching live titles now...", academicNone: "No feed responded just now.",
        academicNote: "Fetched live just now - there is no stored history of past titles to show instead.",
        financeNote: "This is the same real figure already shown on the card, just with the full detail.",
        errorGeneric: "Something went wrong - nothing was lost, try again.",
        copy: "Copy", copied: "Copied",
        csvLabel: "Or upload your own bank CSV export (nothing is stored; parsed once and discarded):",
        csvUpload: "Upload CSV", csvParsing: "Categorizing...", csvNone: "No breakdown yet.",
        csvUncategorized: "uncategorized as \"Other\"",
        googleLabel: "Google Workspace (Gmail metadata only - never Calendar, never message bodies)",
        googleExplain: "This is mounted and gated on the real Access-protected console, not on this public "
          + "dashboard - connecting here would mean anyone reaching this page, not just the owner, could "
          + "start linking a Google account. Manage the real connection on the console instead.",
        googleOpenConsole: "Open on console.apexcorelab.uk",
        bulkTab: "One at a time", bulkTabBulk: "Bulk (up to 10)",
        bulkLabel: "Paste up to 10 bios, separated by a blank line between each:",
        bulkGenerate: "Generate All", bulkGenerating: "Generating all...",
        bulkEmpty: "Paste at least one profile first.", bulkProfile: "Profile",
        wealthButton: "Run Wealth Engine (read-only)",
        wealthLabel: "Paste your portfolio/savings in plain text (e.g. \"£10,000 in savings, no ISA used this year\"):",
        wealthRunning: "Analyzing...", wealthEmpty: "Describe your savings/portfolio first.",
        wealthReasoning: "Why:", wealthDisclaimerLabel: "Important:",
      },
  fa: { title: "داشبورد مدیریتی", whereWasI: "کجا بودیم؟", finance: "مالی", academic: "آکادمیک",
        dating: "دیتینگ", banking: "بانکداری", lastThing: "آخرین کاری که کردید:", nothingYet: "هنوز در این جلسه کاری نشده.",
        howItWorks: "نحوه کار", howItJudges: "نحوه قضاوت (قبل از اعتماد به هر عدد، این را بخوانید)",
        close: "بستن",
        datingBioLabel: "متن پروفایل را اینجا بچسبانید (چیزی ذخیره یا جایی ارسال نمی‌شود):",
        datingGenerate: "تولید پیش‌نویس‌ها", datingGenerating: "در حال تولید...", datingEmpty: "ابتدا متنی وارد کنید.",
        bankingExplain: "بانکداری باز نیاز به رضایت واقعی مالک از طریق یک ارائه‌دهنده اطلاعات حساب بررسی‌شده دارد (مثل TrueLayer). "
          + "هنوز هیچ تجمیع‌کننده‌ای تنظیم نشده، پس چیزی برای اتصال وجود ندارد - این دکمه فقط پیش‌نمایش مرحله راه‌اندازی است، نه یک اتصال واقعی.",
        bankingConnect: "اتصال به TrueLayer", bankingAlert: "متصل نشد: هنوز هیچ کلید API تجمیع‌کننده‌ای روی این سرور تنظیم نشده است.",
        academicFetching: "در حال دریافت زنده عناوین...", academicNone: "هیچ فیدی در این لحظه پاسخ نداد.",
        academicNote: "همین الان به‌صورت زنده دریافت شد - تاریخچه ذخیره‌شده‌ای از عناوین قبلی وجود ندارد.",
        financeNote: "این همان رقم واقعی نشان‌داده‌شده روی کارت است، فقط با جزئیات کامل.",
        errorGeneric: "مشکلی پیش آمد - چیزی از دست نرفت، دوباره امتحان کنید.",
        copy: "کپی", copied: "کپی شد",
        csvLabel: "یا فایل CSV بانکی خودتان را آپلود کنید (چیزی ذخیره نمی‌شود؛ فقط یک‌بار پردازش و حذف می‌شود):",
        csvUpload: "آپلود CSV", csvParsing: "در حال دسته‌بندی...", csvNone: "هنوز تفکیکی وجود ندارد.",
        csvUncategorized: "دسته‌بندی‌نشده (در «سایر»)",
        googleLabel: "گوگل ورک‌اسپیس (فقط اطلاعات ایمیل - هرگز تقویم، هرگز متن پیام)",
        googleExplain: "این اتصال فقط روی کنسول واقعی محافظت‌شده نصب شده، نه روی این داشبورد عمومی - "
          + "اتصال از اینجا یعنی هر کسی که به این صفحه برسد، نه فقط مالک، می‌تواند شروع به اتصال حساب گوگل کند. "
          + "اتصال واقعی را از کنسول مدیریت کنید.",
        googleOpenConsole: "باز کردن در console.apexcorelab.uk",
        bulkTab: "یکی‌یکی", bulkTabBulk: "دسته‌ای (تا ۱۰ مورد)",
        bulkLabel: "تا ۱۰ پروفایل را بچسبانید، بین هر کدام یک خط خالی بگذارید:",
        bulkGenerate: "تولید همه", bulkGenerating: "در حال تولید همه...",
        bulkEmpty: "ابتدا حداقل یک پروفایل وارد کنید.", bulkProfile: "پروفایل",
        wealthButton: "اجرای موتور ثروت (فقط خواندنی)",
        wealthLabel: "پس‌انداز یا پرتفوی خود را به‌صورت متن ساده بنویسید (مثال: «۱۰,۰۰۰ پوند پس‌انداز، امسال ISA استفاده نشده»):",
        wealthRunning: "در حال تحلیل...", wealthEmpty: "ابتدا پس‌انداز یا پرتفوی خود را توصیف کنید.",
        wealthReasoning: "دلیل:", wealthDisclaimerLabel: "مهم:",
      },
};

// Deliberately NOT a progress bar / numeric score: nothing in the real pipeline computes a
// "respect score", "relevance %" or "tax efficiency %" as a genuine measurement (see
// judgement_logic_en/fa below, and dating_draft_reply's own comment in scripts/orchestrator.py
// about never presenting a self-rating as ground truth). A fake percentage bar would be exactly
// the kind of fabricated precision this whole project has repeatedly refused to ship.
function Workflow({ steps, lang }) {
  if (!steps || !steps.length) return null;
  return (
    <ol style={{ margin: "4px 0 0", padding: lang === "fa" ? "0 20px 0 0" : "0 0 0 20px", fontSize: 13, opacity: 0.85, lineHeight: 1.5 }}>
      {steps.map((step, i) => (<li key={i} style={{ marginBottom: 4 }}>{step}</li>))}
    </ol>
  );
}

function JudgementLogic({ text, color }) {
  if (!text) return null;
  return (
    <div style={{
      fontSize: 12.5, lineHeight: 1.5, padding: 10, borderRadius: 8,
      background: "rgba(255,255,255,0.04)", borderLeft: `3px solid ${color}`, opacity: 0.9,
    }}>
      {text}
    </div>
  );
}

function Modal({ title, color, lang, onClose, children }) {
  const dir = lang === "fa" ? "rtl" : "ltr";
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 50,
        display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
      }}
    >
      <div
        dir={dir}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0f1420", border: `1px solid ${color}55`, borderRadius: 14, padding: 24,
          maxWidth: 480, width: "100%", maxHeight: "80vh", overflowY: "auto", color: "#fff",
          display: "flex", flexDirection: "column", gap: 14,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 18, color }}>{title}</h2>
          <button onClick={onClose} style={{
            background: "transparent", border: "none", color: "#fff", fontSize: 20, cursor: "pointer", opacity: 0.7,
          }}>
            {"×"}
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// Splits the model's raw "1. ...\n2. ...\n3. ..." reply into separate copyable drafts. Falls
// back to showing the whole raw reply as one block if the numbered format isn't found - never
// hides or drops the real text just because it didn't parse the way we expected.
function splitDrafts(raw) {
  const lines = String(raw || "").split(/\r?\n/).filter((l) => l.trim());
  const items = lines
    .map((l) => l.replace(/^\s*\d+[.)]\s*/, "").trim())
    .filter(Boolean);
  return items.length > 1 ? items : [String(raw || "").trim()].filter(Boolean);
}

function CopyButton({ text, label, copiedLabel }) {
  const [copied, setCopied] = useState(false);
  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard API can be blocked (permissions, insecure context); fail silently - the
      // text is still fully visible and selectable by hand either way.
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button onClick={doCopy} style={{
      fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #3a3a55",
      background: "transparent", color: "#fff", cursor: "pointer", opacity: 0.85,
    }}>
      {copied ? copiedLabel : label}
    </button>
  );
}

function BulkDatingSection({ lang, color, t }) {
  const [text, setText] = useState("");
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [results, setResults] = useState([]);
  const [errorMsg, setErrorMsg] = useState("");

  const generateAll = async () => {
    const bios = text.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean).slice(0, 10);
    if (!bios.length) { setState("error"); setErrorMsg(t.bulkEmpty); return; }
    setState("loading");
    try {
      const res = await fetch(DATING_BULK_ENDPOINT, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bios }),
      });
      const json = await res.json();
      if (!res.ok) { setErrorMsg(t.errorGeneric); setState("error"); return; }
      setResults(json.results || []);
      setState("done");
    } catch {
      setErrorMsg(t.errorGeneric);
      setState("error");
    }
  };

  return (
    <>
      <label style={{ fontSize: 13, opacity: 0.85 }}>{t.bulkLabel}</label>
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={8} maxLength={20000}
        style={{
          width: "100%", boxSizing: "border-box", borderRadius: 8, border: "1px solid #3a3a55",
          background: "#05060a", color: "#fff", padding: 10, fontSize: 14, resize: "vertical",
        }}
      />
      <button
        onClick={generateAll} disabled={state === "loading"}
        style={{
          fontSize: 15, fontWeight: 700, padding: "10px 14px", borderRadius: 8, border: "none",
          background: color, color: "#05060a", cursor: state === "loading" ? "default" : "pointer",
          opacity: state === "loading" ? 0.6 : 1,
        }}
      >
        {state === "loading" ? t.bulkGenerating : t.bulkGenerate}
      </button>
      {state === "error" && <div style={{ color: "#ff8a8a", fontSize: 13 }}>{errorMsg}</div>}
      {state === "done" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {results.map((r) => (
            <div key={r.bio_index}>
              <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 4 }}>{t.bulkProfile} {r.bio_index + 1}</div>
              {r.error ? (
                <div style={{ color: "#ff8a8a", fontSize: 13 }}>{r.error}</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {splitDrafts(r.drafts).map((draft, i) => (
                    <div key={i} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10,
                      fontSize: 14, background: "rgba(255,255,255,0.04)", padding: 12, borderRadius: 8,
                    }}>
                      <div style={{ whiteSpace: "pre-wrap", flex: 1 }}>{draft}</div>
                      <CopyButton text={draft} label={t.copy} copiedLabel={t.copied} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function DatingModal({ lang, color, onClose }) {
  const t = COPY[lang];
  const [tab, setTab] = useState("single"); // single | bulk
  const [bio, setBio] = useState("");
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [drafts, setDrafts] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const generate = async () => {
    if (!bio.trim()) { setState("error"); setErrorMsg(t.datingEmpty); return; }
    setState("loading");
    try {
      const res = await fetch(DATING_DRAFT_ENDPOINT, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_text: bio.trim() }),
      });
      const json = await res.json();
      if (!res.ok) {
        const budgetDenied = res.status === 402 || String(json.error || "").startsWith("BUDGET_DENIED");
        setErrorMsg(budgetDenied
          ? (lang === "fa" ? "سقف بودجه روزانه پر شده است." : "Budget cap reached.")
          : t.errorGeneric);
        setState("error");
        return;
      }
      setDrafts(json.drafts || "");
      setState("done");
    } catch {
      setErrorMsg(t.errorGeneric);
      setState("error");
    }
  };

  return (
    <Modal title={COPY[lang].dating} color={color} lang={lang} onClose={onClose}>
      <div style={{ display: "flex", gap: 8 }}>
        {[["single", t.bulkTab], ["bulk", t.bulkTabBulk]].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} style={{
            fontSize: 13, padding: "6px 12px", borderRadius: 6, cursor: "pointer",
            border: tab === key ? `1px solid ${color}` : "1px solid #3a3a55",
            background: tab === key ? `${color}22` : "transparent", color: "#fff",
          }}>
            {label}
          </button>
        ))}
      </div>

      {tab === "single" && (
        <>
          <label style={{ fontSize: 13, opacity: 0.85 }}>{t.datingBioLabel}</label>
          <textarea
            value={bio} onChange={(e) => setBio(e.target.value)} rows={5} maxLength={2000}
            style={{
              width: "100%", boxSizing: "border-box", borderRadius: 8, border: "1px solid #3a3a55",
              background: "#05060a", color: "#fff", padding: 10, fontSize: 14, resize: "vertical",
            }}
          />
          <button
            onClick={generate} disabled={state === "loading"}
            style={{
              fontSize: 15, fontWeight: 700, padding: "10px 14px", borderRadius: 8, border: "none",
              background: color, color: "#05060a", cursor: state === "loading" ? "default" : "pointer",
              opacity: state === "loading" ? 0.6 : 1,
            }}
          >
            {state === "loading" ? t.datingGenerating : t.datingGenerate}
          </button>
          {state === "error" && <div style={{ color: "#ff8a8a", fontSize: 13 }}>{errorMsg}</div>}
          {state === "done" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {splitDrafts(drafts).map((draft, i) => (
                <div key={i} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10,
                  fontSize: 14, background: "rgba(255,255,255,0.04)", padding: 12, borderRadius: 8,
                }}>
                  <div style={{ whiteSpace: "pre-wrap", flex: 1 }}>{draft}</div>
                  <CopyButton text={draft} label={t.copy} copiedLabel={t.copied} />
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === "bulk" && <BulkDatingSection lang={lang} color={color} t={t} />}
    </Modal>
  );
}

function formatPounds(pence) {
  return (pence / 100).toLocaleString(undefined, { style: "currency", currency: "GBP" });
}

// file.text() always decodes as UTF-8, which silently mangles "£" (and other non-ASCII bytes)
// into U+FFFD replacement characters for the many real UK bank CSV exports that are actually
// Windows-1252 (CP1252) - not a hypothetical: a real Santander "Midata" export does exactly
// this. Decode as UTF-8 first; if the result contains the replacement character, the source
// wasn't valid UTF-8, so re-decode the same bytes as windows-1252 instead of silently
// corrupting every amount in the file.
async function readAsTextWithEncodingFallback(file) {
  const buffer = await file.arrayBuffer();
  const utf8 = new TextDecoder("utf-8").decode(buffer);
  if (!utf8.includes("�")) return utf8;
  return new TextDecoder("windows-1252").decode(buffer);
}

function BankingModal({ lang, color, onClose }) {
  const t = COPY[lang];
  const [csvState, setCsvState] = useState("idle"); // idle | loading | done | error
  const [breakdown, setBreakdown] = useState(null);
  const [csvError, setCsvError] = useState("");

  const onFile = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = ""; // allow re-uploading the same filename later
    if (!file) return;
    setCsvState("loading");
    try {
      const text = await readAsTextWithEncodingFallback(file);
      const res = await fetch(BANKING_PARSE_ENDPOINT, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csv_text: text }),
      });
      const json = await res.json();
      if (!res.ok) {
        const budgetDenied = res.status === 402 || String(json.error || "").startsWith("BUDGET_DENIED");
        setCsvError(budgetDenied
          ? (lang === "fa" ? "سقف بودجه روزانه پر شده است." : "Budget cap reached.")
          : String(json.error || t.errorGeneric));
        setCsvState("error");
        return;
      }
      setBreakdown(json);
      setCsvState("done");
    } catch {
      setCsvError(t.errorGeneric);
      setCsvState("error");
    }
  };

  return (
    <Modal title={COPY[lang].banking} color={color} lang={lang} onClose={onClose}>
      <p style={{ fontSize: 14, lineHeight: 1.6, margin: 0 }}>{t.bankingExplain}</p>
      <button
        onClick={() => window.alert(t.bankingAlert)}
        style={{
          fontSize: 15, fontWeight: 700, padding: "10px 14px", borderRadius: 8, border: "none",
          background: color, color: "#05060a", cursor: "pointer",
        }}
      >
        {t.bankingConnect}
      </button>

      <div style={{ borderTop: "1px solid #2a2a3a", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
        <label style={{ fontSize: 13, opacity: 0.85 }}>{t.csvLabel}</label>
        <input type="file" accept=".csv,text/csv" onChange={onFile} style={{ fontSize: 13, color: "#fff" }} />
        {csvState === "loading" && <div style={{ fontSize: 14, opacity: 0.8 }}>{t.csvParsing}</div>}
        {csvState === "error" && <div style={{ color: "#ff8a8a", fontSize: 13 }}>{csvError}</div>}
        {csvState === "done" && breakdown && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {Object.entries(breakdown.totals_pence)
              .filter(([, pence]) => pence !== 0)
              .map(([category, pence]) => (
                <div key={category} style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                  <span>{category}</span>
                  <span style={{ color: pence < 0 ? "#ff8a8a" : "#7dffb0" }}>{formatPounds(pence)}</span>
                </div>
              ))}
            {breakdown.uncategorized_count > 0 && (
              <div style={{ fontSize: 12, opacity: 0.6 }}>
                {breakdown.uncategorized_count} {t.csvUncategorized}
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

function AcademicModal({ lang, color, onClose }) {
  const t = COPY[lang];
  const [state, setState] = useState("loading"); // loading | done | error
  const [titles, setTitles] = useState([]);

  useEffect(() => {
    let cancelled = false;
    fetch(ACADEMIC_ENDPOINT)
      .then((res) => { if (!res.ok) throw new Error(String(res.status)); return res.json(); })
      .then((json) => { if (!cancelled) { setTitles(json.titles || []); setState("done"); } })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, []);
  // Persian titles: a second, slower request (one local-model call). English shows at once;
  // the Persian replaces it when it arrives, with the original kept underneath.
  const [fa, setFa] = useState({});
  const [translating, setTranslating] = useState(false);
  useEffect(() => {
    if (lang !== "fa" || state !== "done" || titles.length === 0) return undefined;
    let cancelled = false;
    setTranslating(true);
    fetch(ACADEMIC_ENDPOINT + "?translate=fa")
      .then((res) => (res.ok ? res.json() : { titles: [] }))
      .then((json) => {
        if (cancelled) return;
        const map = {};
        (json.titles || []).forEach((item) => { if (item.title_fa) map[item.title] = item.title_fa; });
        setFa(map); setTranslating(false);
      })
      .catch(() => { if (!cancelled) setTranslating(false); });
    return () => { cancelled = true; };
  }, [lang, state, titles.length]);

  return (
    <Modal title={COPY[lang].academic} color={color} lang={lang} onClose={onClose}>
      <div style={{ fontSize: 12, opacity: 0.6 }}>{t.academicNote}</div>
      {state === "loading" && <div style={{ fontSize: 14, opacity: 0.8 }}>{t.academicFetching}</div>}
      {translating && <div style={{ fontSize: 13, opacity: 0.7 }}>در حال ترجمه به فارسی با مدل محلی (حدود یک دقیقه)…</div>}
      {lang === "fa" && Object.keys(fa).length > 0 && <div style={{ fontSize: 12, opacity: 0.6 }}>ترجمهٔ ماشینی است؛ عنوان اصلی زیر هر مورد آمده.</div>}
      {state === "error" && <div style={{ color: "#ff8a8a", fontSize: 13 }}>{t.errorGeneric}</div>}
      {state === "done" && titles.length === 0 && <div style={{ fontSize: 14, opacity: 0.8 }}>{t.academicNone}</div>}
      {state === "done" && titles.length > 0 && (
        <ul style={{ margin: 0, padding: lang === "fa" ? "0 18px 0 0" : "0 0 0 18px", fontSize: 14, lineHeight: 1.7 }}>
          {titles.map((item, i) => (
            <li key={i}>
              <a href={item.link} target="_blank" rel="noreferrer" style={{ color }}>{(lang === "fa" && fa[item.title]) || item.title}</a>
              {lang === "fa" && fa[item.title] ? <div dir="ltr" style={{ opacity: 0.5, fontSize: 12 }}>{item.title}</div> : null}
              {" "}<span style={{ opacity: 0.5, fontSize: 12 }}>({item.feed})</span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

function WealthEngineSection({ lang, color, t }) {
  const [portfolioText, setPortfolioText] = useState("");
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");

  const run = async () => {
    if (!portfolioText.trim()) { setState("error"); setErrorMsg(t.wealthEmpty); return; }
    setState("loading");
    try {
      const res = await fetch(WEALTH_ANALYZE_ENDPOINT, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ portfolio_text: portfolioText.trim() }),
      });
      const json = await res.json();
      if (!res.ok) {
        const budgetDenied = res.status === 402 || String(json.error || "").startsWith("BUDGET_DENIED");
        setErrorMsg(budgetDenied
          ? (lang === "fa" ? "سقف بودجه روزانه پر شده است." : "Budget cap reached.")
          : t.errorGeneric);
        setState("error");
        return;
      }
      setResult(json);
      setState("done");
    } catch {
      setErrorMsg(t.errorGeneric);
      setState("error");
    }
  };

  return (
    <div style={{ borderTop: "1px solid #2a2a3a", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <label style={{ fontSize: 13, opacity: 0.85 }}>{t.wealthLabel}</label>
      <textarea
        value={portfolioText} onChange={(e) => setPortfolioText(e.target.value)} rows={3} maxLength={2000}
        style={{
          width: "100%", boxSizing: "border-box", borderRadius: 8, border: "1px solid #3a3a55",
          background: "#05060a", color: "#fff", padding: 10, fontSize: 14, resize: "vertical",
        }}
      />
      <button
        onClick={run} disabled={state === "loading"}
        style={{
          fontSize: 15, fontWeight: 700, padding: "10px 14px", borderRadius: 8, border: "none",
          background: color, color: "#05060a", cursor: state === "loading" ? "default" : "pointer",
          opacity: state === "loading" ? 0.6 : 1,
        }}
      >
        {state === "loading" ? t.wealthRunning : t.wealthButton}
      </button>
      {state === "error" && <div style={{ color: "#ff8a8a", fontSize: 13 }}>{errorMsg}</div>}
      {state === "done" && result && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 15, fontWeight: 700, background: "rgba(255,255,255,0.04)", padding: 12, borderRadius: 8 }}>
            {result.action}
          </div>
          {result.reasoning && (
            <div style={{ fontSize: 13, opacity: 0.85 }}><b>{t.wealthReasoning}</b> {result.reasoning}</div>
          )}
          <div style={{ fontSize: 12, opacity: 0.7, fontStyle: "italic" }}>
            <b>{t.wealthDisclaimerLabel}</b> {result.disclaimer}
          </div>
        </div>
      )}
    </div>
  );
}

function FinanceModal({ lang, color, data, onClose }) {
  const t = COPY[lang];
  return (
    <Modal title={COPY[lang].finance} color={color} lang={lang} onClose={onClose}>
      <div style={{ fontSize: 16 }}>{lang === "fa" ? data.metric_fa : data.metric_en}</div>
      <div style={{ fontSize: 12, opacity: 0.6 }}>{t.financeNote}</div>
      {data.workflow && <Workflow steps={data.workflow} lang={lang} />}
      {(lang === "fa" ? data.judgement_logic_fa : data.judgement_logic_en) && (
        <JudgementLogic text={lang === "fa" ? data.judgement_logic_fa : data.judgement_logic_en} color={color} />
      )}
      <WealthEngineSection lang={lang} color={color} t={t} />
    </Modal>
  );
}

const GOOGLE_COLOR = "#8ab4f8";

// Not a DomainCard: there is no backend "google" entry in dashboard_payload() because this
// isn't owned by this dashboard at all - it's a real, already-working, Access-gated flow on
// console.apexcorelab.uk. This card is honest about that: it never claims "Connected"/"Needs
// setup" here (it would have no way to know without a login this app deliberately doesn't have),
// it only explains and links out.
function GoogleModal({ lang, onClose }) {
  const t = COPY[lang];
  return (
    <Modal title={t.googleLabel} color={GOOGLE_COLOR} lang={lang} onClose={onClose}>
      <p style={{ fontSize: 14, lineHeight: 1.6, margin: 0 }}>{t.googleExplain}</p>
      <a href={GOOGLE_CONSOLE_URL} target="_blank" rel="noreferrer" style={{
        display: "inline-block", fontSize: 15, fontWeight: 700, padding: "10px 14px", borderRadius: 8,
        background: GOOGLE_COLOR, color: "#05060a", textDecoration: "none", textAlign: "center",
      }}>
        {t.googleOpenConsole}
      </a>
    </Modal>
  );
}

function GoogleCard({ lang, onClick }) {
  const t = COPY[lang];
  return (
    <div
      onClick={onClick}
      style={{
        border: `1px solid ${GOOGLE_COLOR}55`, borderRadius: 12, padding: 20, cursor: "pointer",
        background: "rgba(255,255,255,0.03)", display: "flex", flexDirection: "column", gap: 10,
      }}
    >
      <div style={{ fontSize: 28 }}>{"\u{1F4E7}"}</div>
      <div style={{ fontSize: 18, fontWeight: 700 }}>{t.googleLabel}</div>
      <div style={{ fontSize: 14, opacity: 0.75, flex: 1 }}>{t.googleOpenConsole} {"→"}</div>
    </div>
  );
}

function BudgetTracker({ budget, lang }) {
  if (!budget) return null;
  const pounds = (pence) => "£" + (pence / 100).toFixed(2);
  const color = budget.exhausted || budget.warning ? "#ff5c5c" : "#7dffb0";
  return (
    <div style={{ border: `1px solid ${color}88`, borderRadius: 12, padding: 16, marginBottom: 16, background: "#0f1526" }}>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
        <div style={{ fontWeight: 700 }}>{lang === "fa" ? "بودجه ماهانه هوش مصنوعی" : "Monthly AI Budget"} · {budget.month}</div>
        <div style={{ fontWeight: 700, color }}>{pounds(budget.spent_pence)} / {pounds(budget.cap_pence)}</div>
      </div>
      <div style={{ height: 12, borderRadius: 999, background: "rgba(255,255,255,0.12)", overflow: "hidden" }}
           role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={budget.percent}>
        <div style={{ width: `${budget.percent}%`, height: "100%", background: color }} />
      </div>
      {budget.exhausted && (
        <div style={{ color: "#ff5c5c", fontWeight: 700, marginTop: 8 }}>
          {lang === "fa" ? "بودجه ماهانه تمام شد. تا ماه بعد متوقف است." : "Monthly Budget Exhausted. Paused until next month."}
        </div>
      )}
      {!budget.exhausted && budget.warning && (
        <div style={{ color: "#ff5c5c", marginTop: 8 }}>
          {lang === "fa" ? "هشدار: بیش از ۸۰٪ بودجه مصرف شده است." : "Warning: more than 80% of this month's budget is used."}
        </div>
      )}
      {budget.local_model && (
        <div style={{ fontSize: 13, opacity: 0.7, marginTop: 8 }}>
          {lang === "fa" ? "مدل محلی فعال است: هر فراخوانی هزینه‌ای ندارد." : "Local model active: calls cost nothing."}
        </div>
      )}
    </div>
  );
}

// Latest Opportunity Scout results (core/apex/scout_events.py, scout_wealth.py). Shows only
// what the scouts actually fetched; an empty or never-run scout says so instead of a placeholder.
function ScoutAlerts({ scout, lang }) {
  if (!scout) return null;
  const events = scout.events, wealth = scout.wealth;
  const when = (r) => (r && r.generated_at ? new Date(r.generated_at * 1000).toLocaleString() : "");
  const link = { color: "#5fe3ff", textDecoration: "none" };
  const pay = (job) => [job.salary_min, job.salary_max].filter(Boolean).map((v) => "£" + v.toLocaleString()).join(" – ");
  return (
    <div dir="auto" style={{ border: "1px solid #b98fff66", borderRadius: 12, padding: 16, marginBottom: 16, background: "#0f1526" }}>
      <div style={{ fontWeight: 700, marginBottom: 10 }}>{lang === "fa" ? "هشدارهای زنده دیده‌بان" : "Live Scout Alerts"}</div>
      {!events && !wealth && (
        <div style={{ opacity: 0.6 }}>{lang === "fa" ? "دیده‌بان هنوز اجرا نشده است." : "The scout has not run yet."}</div>
      )}
      {events && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 4 }}>
            {lang === "fa" ? "رویدادها" : "Events"} · {when(events)}
            {events.selection === "keyword-fallback" ? (lang === "fa" ? " · رتبه‌بندی با کلیدواژه" : " · ranked by keyword") : ""}
          </div>
          {events.picked && events.picked.length > 0 ? events.picked.map((e, i) => (
            <div key={i} style={{ marginBottom: 6 }}>
              {e.url ? <a href={e.url} target="_blank" rel="noopener noreferrer" style={link}>{e.title}</a> : e.title}
              <div style={{ fontSize: 13, opacity: 0.75 }}>{e.start}{e.location ? " · " + e.location : ""}{e.why ? " · " + e.why : ""}</div>
            </div>
          )) : (
            <div style={{ opacity: 0.6 }}>{lang === "fa" ? "رویدادی پیدا نشد." : "No upcoming events found in your groups."}</div>
          )}
        </div>
      )}
      {wealth && (
        <div>
          <div style={{ fontSize: 13, opacity: 0.7, marginBottom: 4 }}>{lang === "fa" ? "شغل و بازار" : "Jobs and markets"} · {when(wealth)}</div>
          {wealth.job ? (
            <div style={{ marginBottom: 6 }}>
              {wealth.job.url ? <a href={wealth.job.url} target="_blank" rel="noopener noreferrer" style={link}>{wealth.job.title}</a> : wealth.job.title}
              <div style={{ fontSize: 13, opacity: 0.75 }}>{[wealth.job.employer, wealth.job.location, pay(wealth.job)].filter(Boolean).join(" · ")}</div>
            </div>
          ) : (
            <div style={{ opacity: 0.6, marginBottom: 6 }}>
              {wealth.job_status === "NEEDS_REED_KEY"
                ? (lang === "fa" ? "جست‌وجوی شغل به کلید رایگان Reed نیاز دارد." : "Job search needs a free Reed API key.")
                : (lang === "fa" ? "شغل مناسبی با حقوق اعلام‌شده پیدا نشد." : "No matching job with a stated salary.")}
            </div>
          )}
          {wealth.alert && (
            <div>
              <a href={wealth.alert.url} target="_blank" rel="noopener noreferrer" style={link}>{wealth.alert.headline}</a>
              <div style={{ fontSize: 13, opacity: 0.75 }}>
                {wealth.alert.note ? wealth.alert.note + " · " : ""}{wealth.alert.source}
                {lang === "fa" ? " · اطلاع‌رسانی، نه توصیه مالی" : " · information, not financial advice"}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DomainCard({ domain, data, lang, onAction }) {
  if (!data) return null;
  const color = DOMAIN_COLOR[domain];
  const t = COPY[lang];
  const judgementText = lang === "fa" ? data.judgement_logic_fa : data.judgement_logic_en;
  return (
    <div
      onClick={() => onAction(domain)}
      style={{
        border: `1px solid ${color}55`, borderRadius: 12, padding: 20, cursor: "pointer",
        background: "rgba(255,255,255,0.03)", display: "flex", flexDirection: "column", gap: 10,
      }}
    >
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

      {data.workflow && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, opacity: 0.6, textTransform: "uppercase", marginBottom: 2 }}>
            {t.howItWorks}
          </div>
          <Workflow steps={data.workflow} lang={lang} />
        </div>
      )}

      {judgementText && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, opacity: 0.6, textTransform: "uppercase", marginBottom: 4 }}>
            {t.howItJudges}
          </div>
          <JudgementLogic text={judgementText} color={color} />
        </div>
      )}

      <button
        onClick={(e) => { e.stopPropagation(); onAction(domain); }}
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

export default function ExecutiveDashboard({ onOpenSwarmPanel, onOpenChat, lastAction }) {
  const [lang, setLang] = useRemembered("lang", "fa");
  const [data, setData] = useState(null);
  const [unreachable, setUnreachable] = useState(false);
  const [openModalDomain, setOpenModalDomain] = useState(null); // null | "finance" | "academic" | "dating" | "banking" | "google"

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
  const statusOf = (d) => (data && data[d] ? (lang === "fa" ? data[d].metric_fa : data[d].metric_en) || data[d].status : "");
  const areas = DOMAINS.map((d) => ({ id: d, icon: DOMAIN_ICON[d], label: t[d], status: statusOf(d), onOpen: () => setOpenModalDomain(d) }))
    .concat([{ id: "google", icon: "\u{2709}\u{FE0F}", label: "Gmail", status: "", onOpen: () => setOpenModalDomain("google") }]);

  return (
    <div dir={lang === "fa" ? "rtl" : "ltr"} style={{ position: "absolute", inset: 0, color: "#ffffff", fontSize: 16,
                                                     fontFamily: 'Vazirmatn, "Segoe UI", Tahoma, system-ui, sans-serif' }}>
      <FocusHome lang={lang} setLang={setLang} data={data} unreachable={unreachable} lastAction={lastAction} areas={areas}
                 onOpenChat={onOpenChat} onOpenAgents={onOpenSwarmPanel} />

      {openModalDomain === "google" && (
        <GoogleModal lang={lang} onClose={() => setOpenModalDomain(null)} />
      )}
      {openModalDomain === "dating" && (
        <DatingModal lang={lang} color={DOMAIN_COLOR.dating} onClose={() => setOpenModalDomain(null)} />
      )}
      {openModalDomain === "banking" && (
        <BankingModal lang={lang} color={DOMAIN_COLOR.banking} onClose={() => setOpenModalDomain(null)} />
      )}
      {openModalDomain === "academic" && (
        <AcademicModal lang={lang} color={DOMAIN_COLOR.academic} onClose={() => setOpenModalDomain(null)} />
      )}
      {openModalDomain === "finance" && data && (
        <FinanceModal lang={lang} color={DOMAIN_COLOR.finance} data={data.finance} onClose={() => setOpenModalDomain(null)} />
      )}
    </div>
  );
}
