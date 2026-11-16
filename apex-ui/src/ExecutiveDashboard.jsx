import { useEffect, useState } from "react";

// Reads GET /api/dashboard - a cheap re-shaping of the real agent_telemetry data (see
// scripts/orchestrator.py's dashboard_payload()). No fabricated scores anywhere: "status" and
// "metric" are either a real file-existence check, a real stored count, or an honest
// "needs setup" / "never run" default. Each domain card opens a modal with real detail or a
// real action - no second parallel "Swarm Command Center" copy of the same information.
const DASHBOARD_ENDPOINT = "https://api.apexcorelab.uk/api/dashboard";
const ACADEMIC_ENDPOINT = "https://api.apexcorelab.uk/api/academic/latest";
const DATING_DRAFT_ENDPOINT = "https://api.apexcorelab.uk/api/dating/draft";
const BANKING_PARSE_ENDPOINT = "https://api.apexcorelab.uk/api/banking/parse";
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

function DatingModal({ lang, color, onClose }) {
  const t = COPY[lang];
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
    </Modal>
  );
}

function formatPounds(pence) {
  return (pence / 100).toLocaleString(undefined, { style: "currency", currency: "GBP" });
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
      const text = await file.text();
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

  return (
    <Modal title={COPY[lang].academic} color={color} lang={lang} onClose={onClose}>
      <div style={{ fontSize: 12, opacity: 0.6 }}>{t.academicNote}</div>
      {state === "loading" && <div style={{ fontSize: 14, opacity: 0.8 }}>{t.academicFetching}</div>}
      {state === "error" && <div style={{ color: "#ff8a8a", fontSize: 13 }}>{t.errorGeneric}</div>}
      {state === "done" && titles.length === 0 && <div style={{ fontSize: 14, opacity: 0.8 }}>{t.academicNone}</div>}
      {state === "done" && titles.length > 0 && (
        <ul style={{ margin: 0, padding: lang === "fa" ? "0 18px 0 0" : "0 0 0 18px", fontSize: 14, lineHeight: 1.7 }}>
          {titles.map((item, i) => (
            <li key={i}>
              <a href={item.link} target="_blank" rel="noreferrer" style={{ color }}>{item.title}</a>
              {" "}<span style={{ opacity: 0.5, fontSize: 12 }}>({item.feed})</span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
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

export default function ExecutiveDashboard({ onOpenSwarmPanel, lastAction }) {
  const [lang, setLang] = useState("en");
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

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
        {data && DOMAINS.map((domain) => (
          <DomainCard key={domain} domain={domain} data={data[domain]} lang={lang} onAction={setOpenModalDomain} />
        ))}
        <GoogleCard lang={lang} onClick={() => setOpenModalDomain("google")} />
      </div>

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
