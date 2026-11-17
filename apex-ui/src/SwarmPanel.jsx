import { useState, useEffect } from "react";

// Reads scripts/voice_api.py's GET /api/agent_telemetry (also reachable as /api/telemetry, same
// payload). Field names here MUST match what that endpoint actually returns - see
// scripts/orchestrator.py's agent_telemetry(): agent_id, name, status, current_task, due_in_seconds,
// spend_today_pence, calls_today, daily_cap_pence, last_error. There is no "total" or "domain"
// field and no live "ACTIVE" status (no live-execution signal exists to report; see that
// function's docstring for why) - this component never invents one.
const TELEMETRY_ENDPOINT = "/api/agent_telemetry";
const TELEMETRY_POLL_MS = 3000;
const STATUS_COLOR = { OK: "#7dffb0", ERROR: "#ff6a6a", NEVER_RUN: "#6a7a85" };

function formatDueIn(seconds) {
  if (seconds == null) return "not yet scheduled";
  if (seconds <= 0) return "due now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `due in ~${minutes}m`;
  return `due in ~${Math.round(minutes / 60)}h`;
}

export default function SwarmPanel({ open, onToggle }) {
  const [agents, setAgents] = useState(null);
  const [unreachable, setUnreachable] = useState(false);
  const [expanded, setExpanded] = useState(null); // agent_id currently showing "how it works", or null

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const response = await fetch(TELEMETRY_ENDPOINT);
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();
        if (!cancelled) {
          setAgents(data.agents);
          setUnreachable(false);
        }
      } catch {
        if (!cancelled) setUnreachable(true);
      }
    };
    poll();
    const timer = setInterval(poll, TELEMETRY_POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [open]);

  return (
    <div style={{
      position: "absolute", top: 0, right: 0, height: "100vh", width: open ? 280 : 40,
      background: "rgba(5,10,16,0.82)", borderLeft: "1px solid #1d4254", transition: "width 0.2s",
      overflow: "hidden", display: "flex", flexDirection: "column",
    }}>
      <button onClick={onToggle} style={{
        alignSelf: open ? "flex-end" : "center", margin: 8, background: "transparent",
        border: "1px solid #2a6f8a", color: "#dff6ff", borderRadius: 6, cursor: "pointer",
        padding: "4px 8px", fontSize: 12,
      }}>
        {open ? "›" : "‹"}
      </button>
      {open && (
        <div style={{ padding: "0 14px 14px", overflowY: "auto", fontSize: 12 }}>
          <h2 style={{ fontSize: 13, letterSpacing: 0.5, opacity: 0.85, margin: "0 0 10px" }}>
            Swarm Command Center
          </h2>
          {unreachable && <div style={{ color: "#ff8a8a" }}>Telemetry endpoint unreachable.</div>}
          {!agents && !unreachable && <div style={{ opacity: 0.6 }}>Loading...</div>}
          {agents && agents.map((a) => (
            <div key={a.agent_id} style={{
              border: "1px solid #1d4254", borderRadius: 8, padding: 10, marginBottom: 10,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: STATUS_COLOR[a.status] || "#6a7a85", flexShrink: 0,
                }} />
                <strong>{a.agent_id}</strong>
                <span style={{ opacity: 0.7 }}>{a.name}</span>
              </div>
              <div style={{ opacity: 0.85, marginBottom: 4 }}>{a.current_task}</div>
              <div style={{ opacity: 0.55, fontSize: 11, marginBottom: 2 }}>{formatDueIn(a.due_in_seconds)}</div>
              {a.due_in_seconds != null && a.interval_seconds > 0 && (
                <div style={{ height: 3, background: "#1d4254", borderRadius: 2, marginBottom: 2 }}>
                  <div style={{
                    height: 3, borderRadius: 2, background: "#3a7a90",
                    width: `${Math.min(100, (1 - a.due_in_seconds / a.interval_seconds) * 100)}%`,
                  }} />
                </div>
              )}
              {Array.isArray(a.workflow) && a.workflow.length > 0 && (
                <>
                  <button
                    onClick={() => setExpanded(expanded === a.agent_id ? null : a.agent_id)}
                    style={{
                      background: "transparent", border: "none", color: "#5fe3ff", fontSize: 11,
                      cursor: "pointer", padding: 0, marginTop: 4,
                    }}
                  >
                    {expanded === a.agent_id ? "Hide how it works" : "How it works"}
                  </button>
                  {expanded === a.agent_id && (
                    <ol style={{ margin: "4px 0 0", paddingLeft: 16, fontSize: 11, opacity: 0.75 }}>
                      {a.workflow.map((step, i) => <li key={i}>{step}</li>)}
                    </ol>
                  )}
                </>
              )}
              {a.status === "ERROR" && a.last_error && (
                <div style={{ color: "#ff8a8a", fontSize: 11, marginTop: 4 }}>
                  {"⚠"} last run failed: {a.last_error}
                </div>
              )}
              {a.calls_today > 0 && (
                <div style={{ marginTop: 6 }}>
                  <div style={{ opacity: 0.6, fontSize: 11, marginBottom: 2 }}>
                    {a.spend_today_pence}p{a.daily_cap_pence != null ? ` / ${a.daily_cap_pence}p today` : " spent today"}
                    {" "}({a.calls_today} call{a.calls_today === 1 ? "" : "s"})
                  </div>
                  {a.daily_cap_pence != null && a.daily_cap_pence > 0 && (
                    <div style={{ height: 4, background: "#1d4254", borderRadius: 2 }}>
                      <div style={{
                        height: 4, borderRadius: 2, background: "#5fe3ff",
                        width: `${Math.min(100, (a.spend_today_pence / a.daily_cap_pence) * 100)}%`,
                      }} />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
