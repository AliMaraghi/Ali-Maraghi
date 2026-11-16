import { useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function formatPounds(pence) {
  return (pence / 100).toLocaleString(undefined, { style: "currency", currency: "GBP" });
}

function splitDrafts(raw) {
  const lines = String(raw || "").split(/\r?\n/).filter((l) => l.trim());
  const items = lines.map((l) => l.replace(/^\s*\d+[.)]\s*/, "").trim()).filter(Boolean);
  return items.length > 1 ? items : [String(raw || "").trim()].filter(Boolean);
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const doCopy = async () => {
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard may be unavailable */ }
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };
  return <button onClick={doCopy} style={styles.smallButton}>{copied ? "Copied" : "Copy"}</button>;
}

async function readAsTextWithEncodingFallback(file) {
  const buffer = await file.arrayBuffer();
  const utf8 = new TextDecoder("utf-8").decode(buffer);
  if (!utf8.includes("�")) return utf8;
  return new TextDecoder("windows-1252").decode(buffer);
}

function DatingTool() {
  const [bio, setBio] = useState("");
  const [state, setState] = useState("idle");
  const [drafts, setDrafts] = useState("");
  const [error, setError] = useState("");

  const generate = async () => {
    if (!bio.trim()) { setState("error"); setError("Paste a profile bio first."); return; }
    setState("loading");
    try {
      const res = await fetch(`${API}/dating/draft`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_text: bio.trim() }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Request failed");
      setDrafts(json.drafts);
      setState("done");
    } catch (e) {
      setError(e.message);
      setState("error");
    }
  };

  return (
    <div style={styles.panel}>
      <h2>Dating Drafts</h2>
      <p style={styles.note}>Paste a profile bio. Nothing is sent to any dating app - copy the result yourself.</p>
      <textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={5} style={styles.textarea} />
      <button onClick={generate} disabled={state === "loading"} style={styles.button}>
        {state === "loading" ? "Generating..." : "Generate Drafts"}
      </button>
      {state === "error" && <div style={styles.error}>{error}</div>}
      {state === "done" && (
        <div style={styles.list}>
          {splitDrafts(drafts).map((d, i) => (
            <div key={i} style={styles.listItem}>
              <span>{d}</span>
              <CopyButton text={d} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CsvTool() {
  const [state, setState] = useState("idle");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setState("loading");
    try {
      const text = await readAsTextWithEncodingFallback(file);
      const res = await fetch(`${API}/csv/categorize`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csv_text: text }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Request failed");
      setResult(json);
      setState("done");
    } catch (e2) {
      setError(e2.message);
      setState("error");
    }
  };

  return (
    <div style={styles.panel}>
      <h2>Bank CSV Categorizer</h2>
      <p style={styles.note}>Upload your own bank CSV export. Nothing is stored; parsed once and discarded.</p>
      <input type="file" accept=".csv,text/csv" onChange={onFile} />
      {state === "loading" && <div style={styles.note}>Categorizing...</div>}
      {state === "error" && <div style={styles.error}>{error}</div>}
      {state === "done" && result && (
        <div style={styles.list}>
          {Object.entries(result.totals_pence).filter(([, p]) => p !== 0).map(([cat, pence]) => (
            <div key={cat} style={styles.row}>
              <span>{cat}</span>
              <span style={{ color: pence < 0 ? "#c0392b" : "#1e8449" }}>{formatPounds(pence)}</span>
            </div>
          ))}
          {result.uncategorized_count > 0 && (
            <div style={styles.note}>{result.uncategorized_count} uncategorized (in "Other")</div>
          )}
        </div>
      )}
    </div>
  );
}

function TaxTool() {
  const [dataText, setDataText] = useState(
    '{\n  "annual_salary_pence": 4200000,\n  "espp": {\n    "contribution_pence": 150000,\n    "fmv_start_pence_per_share": 2500,\n    "fmv_end_pence_per_share": 3100,\n    "discount_bp": 1500\n  }\n}'
  );
  const [rulesText, setRulesText] = useState(
    '{\n  "tax_year": "2026/27",\n  "source": "gov.uk",\n  "verified_on": "2026-04-06",\n  "income_tax": {\n    "personal_allowance_pence": 1257000,\n    "bands": [\n      {"upto_pence": 5027000, "rate_bp": 2000},\n      {"upto_pence": 12527000, "rate_bp": 4000},\n      {"upto_pence": null, "rate_bp": 4500}\n    ]\n  }\n}'
  );
  const [state, setState] = useState("idle");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const calculate = async () => {
    setState("loading");
    try {
      const data = JSON.parse(dataText);
      const rules = JSON.parse(rulesText);
      const res = await fetch(`${API}/tax/calculate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data, rules }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Request failed");
      setResult(json);
      setState("done");
    } catch (e) {
      setError(e.message);
      setState("error");
    }
  };

  return (
    <div style={styles.panel}>
      <h2>UK ESPP Tax Calculator</h2>
      <p style={styles.note}>Pure arithmetic, no LLM call. Not tax advice - see the disclaimer in the result.</p>
      <label style={styles.label}>Your ESPP data (JSON, pence):</label>
      <textarea value={dataText} onChange={(e) => setDataText(e.target.value)} rows={8} style={styles.textarea} />
      <label style={styles.label}>Tax rules (JSON, with a real source and verified date):</label>
      <textarea value={rulesText} onChange={(e) => setRulesText(e.target.value)} rows={8} style={styles.textarea} />
      <button onClick={calculate} disabled={state === "loading"} style={styles.button}>
        {state === "loading" ? "Calculating..." : "Calculate"}
      </button>
      {state === "error" && <div style={styles.error}>{error}</div>}
      {state === "done" && result && (
        <div style={styles.list}>
          <div style={styles.row}><b>{result.summary}</b></div>
          <div style={styles.note}>{result.disclaimer}</div>
        </div>
      )}
    </div>
  );
}

function RssTool() {
  const [state, setState] = useState("idle");
  const [titles, setTitles] = useState([]);
  const [error, setError] = useState("");

  const fetchLatest = async () => {
    setState("loading");
    try {
      const res = await fetch(`${API}/rss/latest`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail || "Request failed");
      setTitles(json.titles || []);
      setState("done");
    } catch (e) {
      setError(e.message);
      setState("error");
    }
  };

  return (
    <div style={styles.panel}>
      <h2>Recent AI Papers (arXiv + MIT News)</h2>
      <p style={styles.note}>Free, no LLM call. Fetched live - no stored history.</p>
      <button onClick={fetchLatest} disabled={state === "loading"} style={styles.button}>
        {state === "loading" ? "Fetching..." : "Fetch Latest"}
      </button>
      {state === "error" && <div style={styles.error}>{error}</div>}
      {state === "done" && (
        <div style={styles.list}>
          {titles.length === 0 && <div style={styles.note}>No feed responded just now.</div>}
          {titles.map((t, i) => (
            <div key={i} style={styles.row}>
              <a href={t.link} target="_blank" rel="noreferrer">{t.title}</a>
              <span style={styles.note}>({t.feed})</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const TABS = [
  ["dating", "Dating Drafts", DatingTool],
  ["csv", "CSV Categorizer", CsvTool],
  ["tax", "Tax Calculator", TaxTool],
  ["rss", "AI Papers", RssTool],
];

export default function App() {
  const [tab, setTab] = useState("dating");
  const Active = TABS.find(([key]) => key === tab)[2];

  return (
    <div style={styles.app}>
      <h1>Local Tools</h1>
      <div style={styles.tabs}>
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} style={tab === key ? styles.tabActive : styles.tab}>
            {label}
          </button>
        ))}
      </div>
      <Active />
    </div>
  );
}

const styles = {
  app: { maxWidth: 720, margin: "0 auto", padding: 24, fontFamily: "system-ui, sans-serif", color: "#1a1a1a" },
  tabs: { display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap" },
  tab: { padding: "8px 14px", borderRadius: 6, border: "1px solid #ccc", background: "#fff", cursor: "pointer" },
  tabActive: { padding: "8px 14px", borderRadius: 6, border: "1px solid #333", background: "#eee", cursor: "pointer", fontWeight: 700 },
  panel: { display: "flex", flexDirection: "column", gap: 10 },
  textarea: { width: "100%", boxSizing: "border-box", fontFamily: "monospace", fontSize: 13, padding: 8 },
  button: { padding: "10px 16px", borderRadius: 6, border: "none", background: "#2563eb", color: "#fff", cursor: "pointer", fontWeight: 700, alignSelf: "flex-start" },
  smallButton: { padding: "4px 10px", borderRadius: 6, border: "1px solid #ccc", background: "#fff", cursor: "pointer", fontSize: 12 },
  note: { fontSize: 13, color: "#666" },
  error: { color: "#c0392b", fontSize: 13 },
  label: { fontSize: 13, fontWeight: 600 },
  list: { display: "flex", flexDirection: "column", gap: 8 },
  listItem: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10, background: "#f5f5f5", padding: 10, borderRadius: 6 },
  row: { display: "flex", justifyContent: "space-between", gap: 10 },
};
