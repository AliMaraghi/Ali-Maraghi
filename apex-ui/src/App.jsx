import { useRef, useState, useCallback, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Mic, MicOff, Camera, CameraOff, Eye, EyeOff, User, Circle } from "lucide-react";
import Webcam from "react-webcam";
import * as faceapi from "face-api.js";
import AvatarStage from "./AvatarStage.jsx";
import SwarmPanel from "./SwarmPanel.jsx";
import ExecutiveDashboard from "./ExecutiveDashboard.jsx";

const VRM_URL = "/models/ali.vrm"; // owner-provided asset; absent until the owner places one there

const LANGS = { en: "en-US", fa: "fa-IR" };
// Presence-mode feature flag (companion addendum docs/apex_status/COMPANION_PRESENCE_ADDENDUM_20261113.md,
// section 2/3/11): a selectable mode, sphere kept as the default/efficient fallback, never replaced.
// "avatar" here is ONLY a generic abstract rig placeholder - no personal likeness, no GLB/VRM asset
// (none exists yet; getting one needs owner-selected photos/video and a licensed rigging pipeline,
// which this toggle does not do). Swapping in a real asset later is a separate, reviewed step.
const PRESENCE_KEY = "apex.presenceMode";
function loadPresenceMode() {
  try {
    const saved = localStorage.getItem(PRESENCE_KEY);
    return saved === "avatar" ? "avatar" : "sphere";
  } catch {
    return "sphere";
  }
}
function savePresenceMode(mode) {
  try { localStorage.setItem(PRESENCE_KEY, mode); } catch { /* per-viewer convenience only */ }
}
// tiny_face_detector model weights must be present at apex-ui/public/models/ - see the setup
// note above getReply() below for the exact download command. Without them, face detection
// simply stays off (modelsLoaded=false) and everything else in this file works as before.
const MODEL_URL = "/models";
const DETECT_INTERVAL_MS = 700;

function GlowingSphere({ listening, faceDetected }) {
  const meshRef = useRef(null);
  const color = listening ? "#5fe3ff" : faceDetected ? "#7dffb0" : "#2a6f8a";
  const emissive = listening ? "#5fe3ff" : faceDetected ? "#7dffb0" : "#0f3a4a";
  useFrame((state) => {
    if (!meshRef.current) return;
    const t = state.clock.getElapsedTime();
    const active = listening || faceDetected;
    const pulse = active ? 1 + Math.sin(t * (listening ? 6 : 3)) * 0.12 : 1 + Math.sin(t * 1.2) * 0.03;
    meshRef.current.scale.setScalar(pulse);
    meshRef.current.rotation.y = t * 0.15;
  });
  return (
    <mesh ref={meshRef}>
      <icosahedronGeometry args={[1.4, 2]} />
      <meshStandardMaterial
        color={color}
        emissive={emissive}
        emissiveIntensity={listening ? 1.8 : faceDetected ? 1.1 : 0.6}
        wireframe
      />
    </mesh>
  );
}

// Abstract rig placeholder only: a head + body silhouette with idle breathing/head-turn, built
// from primitives so it cannot be mistaken for a rendered face or a stock photo. Real facial
// identity (section 3 of the companion addendum) replaces this group's contents later, once a
// licensed, owner-approved GLB/VRM asset exists - this component does not attempt that.
function PlaceholderAvatar({ listening, faceDetected }) {
  const headRef = useRef(null);
  const groupRef = useRef(null);
  const color = listening ? "#5fe3ff" : faceDetected ? "#7dffb0" : "#3a7a90";
  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (headRef.current) {
      const breathe = 1 + Math.sin(t * (listening ? 2.2 : 1.1)) * 0.015;
      headRef.current.scale.set(breathe, breathe, breathe);
    }
    if (groupRef.current) {
      groupRef.current.rotation.y = Math.sin(t * 0.3) * 0.15;
    }
  });
  return (
    <group ref={groupRef} position={[0, -0.4, 0]}>
      <mesh ref={headRef} position={[0, 1.55, 0]}>
        <sphereGeometry args={[0.55, 24, 24]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.25} wireframe />
      </mesh>
      <mesh position={[0, 0.55, 0]}>
        <capsuleGeometry args={[0.45, 1.1, 8, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.15} wireframe />
      </mesh>
    </group>
  );
}

function Scene({ listening, speaking, thinking, mouthIntensityRef, faceDetected, presenceMode, vrmStatus, onVrmLoaded, onVrmError }) {
  return (
    <Canvas camera={{ position: [0, 0, 5], fov: 50 }}>
      <ambientLight intensity={0.3} />
      <pointLight position={[4, 4, 4]} intensity={1.2} color="#5fe3ff" />
      <pointLight position={[-4, -2, -2]} intensity={0.5} color="#7a5fff" />
      {presenceMode === "avatar" ? (
        vrmStatus === "error" ? (
          <PlaceholderAvatar listening={listening} faceDetected={faceDetected} />
        ) : (
          <>
            <AvatarStage url={VRM_URL} listening={listening} speaking={speaking} thinking={thinking}
                         mouthIntensityRef={mouthIntensityRef} onLoaded={onVrmLoaded} onError={onVrmError} />
            {vrmStatus !== "loaded" && <PlaceholderAvatar listening={listening} faceDetected={faceDetected} />}
          </>
        )
      ) : (
        <GlowingSphere listening={listening} faceDetected={faceDetected} />
      )}
      <OrbitControls enablePan={false} enableZoom={true} autoRotate={false} />
    </Canvas>
  );
}

// Recognized speech and the reply text both flow through here. Backed by scripts/voice_api.py
// (POST /api/chat); that service fails closed (HTTP 402) until its daily spend cap is configured,
// so an unanswered/odd-looking reply during setup is expected, not a bug in this fetch call.
const CHAT_ENDPOINT = "https://api.apexcorelab.uk/api/chat";

async function getReply(transcript, lang) {
  // Returns {reply, steps}. "steps" reports what the backend actually ran for THIS request
  // (see scripts/orchestrator.py's own comments) - it only exists once the full response
  // arrives (no streaming), so the UI shows it as a completed list, never as live progress.
  try {
    const response = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: transcript }),
    });
    const data = await response.json();
    if (!response.ok) {
      // Mission 2026-11-15 "reconciliation" fix: a 402 from voice_api.py's own Budget
      // circuit breaker (see its docstring - "fails closed until its daily spend cap is
      // configured") was previously shown as a generic "Error: 402", easy to mistake for an
      // unreachable server. It is the opposite: the server IS reachable and IS enforcing the
      // real spend cap correctly - that is the circuit breaker working as designed, not a bug.
      const budgetDenied = response.status === 402 || String(data.error || "").startsWith("BUDGET_DENIED");
      const message = budgetDenied
        ? (lang === "fa" ? "سقف بودجه روزانه پر شده است." : "Budget Cap Reached.")
        : (lang === "fa" ? `خطا: ${data.error || response.status}` : `Error: ${data.error || response.status}`);
      console.error(`apex-ui chat request failed: HTTP ${response.status}`, data.error || "(no error field)");
      return { reply: message, steps: [], isError: true };
    }
    return { reply: data.reply, steps: Array.isArray(data.steps) ? data.steps : [], isError: false };
  } catch (err) {
    // A thrown fetch (as opposed to a non-ok HTTP response above) means the request never
    // got a response at all - true network failure, DNS failure, OR a CORS preflight
    // rejection (the browser throws the SAME generic TypeError for all three; it does not
    // expose which one happened, by design, for security reasons - this is a real browser
    // limitation, not something this code can see around). Logging the real error object
    // (not just this generic message) is the one thing that actually helps distinguish them:
    // a CORS rejection's err.message mentions "CORS" or "Access-Control" on most browsers;
    // plain network/DNS failure does not.
    console.error("apex-ui chat request never reached the server (network/DNS/CORS):", err);
    const message = lang === "fa" ? "اتصال به سرور برقرار نشد." : "Could not reach the server.";
    return { reply: message, steps: [], isError: true };
  }
}

export default function App() {
  const [lang, setLang] = useState("en");
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [steps, setSteps] = useState([]); // real steps the LAST response actually ran; see getReply()
  const [replyIsError, setReplyIsError] = useState(false);
  const [supported, setSupported] = useState(true);
  const recognizerRef = useRef(null);

  // Presence-mode toggle: sphere (default, unchanged) or avatar. "avatar" tries the owner's real
  // VRM asset first (AvatarStage, see that file) and falls back to the abstract placeholder rig
  // while it is missing/loading/invalid - never a stock face, per the companion addendum.
  const [presenceMode, setPresenceMode] = useState(loadPresenceMode);
  useEffect(() => { savePresenceMode(presenceMode); }, [presenceMode]);
  const [vrmStatus, setVrmStatus] = useState("loading"); // "loading" | "loaded" | "error"
  // Speaking state: tracked from the actual SpeechSynthesisUtterance lifecycle below (speak()),
  // not inferred - so the avatar's mouth movement only runs while audio is really playing.
  const [speaking, setSpeaking] = useState(false);
  const [thinking, setThinking] = useState(false);
  const mouthIntensityRef = useRef(null);       // null = no boundary data yet, use amplitude fallback
  const mouthCloseTimeoutRef = useRef(null);
  const [swarmPanelOpen, setSwarmPanelOpen] = useState(false);
  const [view, setView] = useState("chat"); // "chat" | "dashboard"

  // Camera/presence are both OFF by default and require an explicit click - starting a webcam
  // or auto-activating the microphone without the person asking first is exactly the kind of
  // silent default that makes people distrust a product. cameraEnabled grants getUserMedia;
  // autoMicOnPresence is a SEPARATE opt-in on top of that, so turning the camera on to see the
  // 3D reaction never by itself starts listening.
  const [cameraEnabled, setCameraEnabled] = useState(false);
  const [autoMicOnPresence, setAutoMicOnPresence] = useState(false);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [modelError, setModelError] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const webcamRef = useRef(null);
  const detectTimerRef = useRef(null);

  useEffect(() => {
    if (!cameraEnabled) return;
    let cancelled = false;
    faceapi.nets.tinyFaceDetector
      .loadFromUri(MODEL_URL)
      .then(() => { if (!cancelled) setModelsLoaded(true); })
      .catch(() => { if (!cancelled) setModelError(true); });
    return () => { cancelled = true; };
  }, [cameraEnabled]);

  useEffect(() => {
    if (!cameraEnabled || !modelsLoaded) {
      setFaceDetected(false);
      return;
    }
    detectTimerRef.current = setInterval(async () => {
      const video = webcamRef.current && webcamRef.current.video;
      if (!video || video.readyState !== 4) return;
      try {
        const result = await faceapi.detectSingleFace(video, new faceapi.TinyFaceDetectorOptions());
        setFaceDetected(!!result);
      } catch {
        // a dropped frame or a mid-reload model isn't an error worth surfacing; just try again next tick
      }
    }, DETECT_INTERVAL_MS);
    return () => clearInterval(detectTimerRef.current);
  }, [cameraEnabled, modelsLoaded]);

  const lastFaceDetected = useRef(false);
  useEffect(() => {
    const justAppeared = faceDetected && !lastFaceDetected.current;
    lastFaceDetected.current = faceDetected;
    if (justAppeared && autoMicOnPresence && supported && !listening) {
      toggleListening();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [faceDetected]);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSupported(false);
      return;
    }
    const recognizer = new SpeechRecognition();
    recognizer.continuous = false;
    recognizer.interimResults = false;
    recognizer.lang = LANGS[lang];

    recognizer.onresult = async (event) => {
      const text = event.results[0][0].transcript;
      setTranscript(text);
      // "thinking" reflects the REAL wait on getReply()'s network round trip - it clears the
      // instant a real response arrives or fails, never held open artificially (companion
      // addendum: no long "thinking" display just to seem smarter).
      setThinking(true);
      setSteps([]);
      let result;
      try {
        result = await getReply(text, lang);
      } finally {
        setThinking(false);
      }
      setReply(result.reply);
      setSteps(result.steps);
      setReplyIsError(!!result.isError);
      speak(result.reply, lang);
    };
    recognizer.onerror = () => setListening(false);
    recognizer.onend = () => setListening(false);

    recognizerRef.current = recognizer;
    return () => recognizer.abort();
  }, [lang]);

  const speak = useCallback((text, spokenLang) => {
    if (!window.speechSynthesis) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = LANGS[spokenLang];
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => { setSpeaking(false); mouthIntensityRef.current = 0; };
    utterance.onerror = () => { setSpeaking(false); mouthIntensityRef.current = 0; };
    // "boundary" fires per word (most engines) with a real timestamp - word-rhythm timing, not
    // real phonemes (still an approximation, see AvatarStage.jsx's own comment on this). Not
    // every engine/voice fires it; AvatarStage falls back to its amplitude sine wave when it
    // doesn't (mouthIntensityRef.current stays null).
    utterance.onboundary = () => {
      mouthIntensityRef.current = 0.7;
      clearTimeout(mouthCloseTimeoutRef.current);
      mouthCloseTimeoutRef.current = setTimeout(() => { mouthIntensityRef.current = 0.15; }, 120);
    };
    window.speechSynthesis.cancel();
    setSpeaking(false); // cancel() does not reliably fire onend for the utterance it interrupts
    mouthIntensityRef.current = null;
    window.speechSynthesis.speak(utterance);
  }, []);

  const toggleListening = () => {
    if (!supported || !recognizerRef.current) return;
    if (listening) {
      recognizerRef.current.stop();
      setListening(false);
    } else {
      setTranscript("");
      setReply("");
      recognizerRef.current.lang = LANGS[lang];
      recognizerRef.current.start();
      setListening(true);
    }
  };

  if (view === "dashboard") {
    return (
      <div style={{ width: "100vw", height: "100vh", position: "relative" }}>
        <ExecutiveDashboard
          onOpenSwarmPanel={() => { setView("chat"); setSwarmPanelOpen(true); }}
          lastAction={reply ? `${transcript ? transcript + " → " : ""}${reply}` : ""}
        />
        <button
          onClick={() => setView("chat")}
          style={{
            position: "absolute", top: 20, right: 20, fontSize: 12, padding: "4px 10px", borderRadius: 6,
            border: "1px solid #3a7a90", background: "transparent", color: "#fff", cursor: "pointer",
          }}
        >
          Chat/Avatar
        </button>
      </div>
    );
  }

  return (
    <div style={{ width: "100vw", height: "100vh", position: "relative", color: "#dff6ff", fontFamily: "system-ui, sans-serif" }}>
      <style>{"@keyframes apexPulse { 0%,100% { opacity: 0.25; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1); } }"}</style>
      <div style={{ position: "absolute", inset: 0 }}>
        <Scene listening={listening} speaking={speaking} thinking={thinking} mouthIntensityRef={mouthIntensityRef}
               faceDetected={faceDetected} presenceMode={presenceMode}
               vrmStatus={vrmStatus} onVrmLoaded={() => setVrmStatus("loaded")} onVrmError={() => setVrmStatus("error")} />
      </div>

      <div style={{ position: "absolute", top: 20, left: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <h1 style={{ margin: 0, fontSize: 20, letterSpacing: 1, opacity: 0.85 }}>APEX CONSOLE</h1>
          <button
            onClick={() => setView(view === "chat" ? "dashboard" : "chat")}
            style={{
              fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #2a6f8a",
              background: "transparent", color: "#dff6ff", cursor: "pointer",
            }}
          >
            {view === "chat" ? "Dashboard" : "Chat/Avatar"}
          </button>
        </div>
        {presenceMode === "avatar" && (
          <div style={{ fontSize: 11, opacity: 0.65, marginTop: 2 }}>
            {vrmStatus === "loaded"
              ? "Avatar: owner VRM asset"
              : vrmStatus === "error"
              ? `Avatar: ${VRM_URL} not found - showing placeholder rig`
              : "Avatar: loading..."}
          </div>
        )}
      </div>

      {/* Camera preview + presence indicator: visible proof the camera is on whenever it is,
          never hidden - the whole point of this block is that nothing here happens invisibly. */}
      <div style={{ position: "absolute", top: 70, left: 20, display: "flex", flexDirection: "column", gap: 10, width: 220 }}>
        <button
          onClick={() => { setCameraEnabled((v) => !v); if (cameraEnabled) { setModelsLoaded(false); setFaceDetected(false); } }}
          style={{
            display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 6,
            border: "1px solid #2a6f8a", background: cameraEnabled ? "#5fe3ff" : "transparent",
            color: cameraEnabled ? "#05060a" : "#dff6ff", cursor: "pointer", fontSize: 13,
          }}
        >
          {cameraEnabled ? <Camera size={16} /> : <CameraOff size={16} />}
          {cameraEnabled ? "Camera ON" : "Camera OFF"}
        </button>

        {cameraEnabled && (
          <>
            <div style={{ borderRadius: 8, overflow: "hidden", border: `2px solid ${faceDetected ? "#7dffb0" : "#2a6f8a"}` }}>
              <Webcam ref={webcamRef} audio={false} width={220} height={165} mirrored
                      onUserMediaError={() => setModelError(true)} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, opacity: 0.85 }}>
              {faceDetected ? <Eye size={14} color="#7dffb0" /> : <EyeOff size={14} />}
              {modelError ? "Face model failed to load" : !modelsLoaded ? "Loading face model..." : faceDetected ? "Face detected" : "No face detected"}
            </div>
            <button
              onClick={() => setAutoMicOnPresence((v) => !v)}
              style={{
                display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderRadius: 6,
                border: "1px solid #2a6f8a", background: autoMicOnPresence ? "#7dffb0" : "transparent",
                color: autoMicOnPresence ? "#05060a" : "#dff6ff", cursor: "pointer", fontSize: 12,
              }}
            >
              {autoMicOnPresence ? "Auto-mic on presence: ON" : "Auto-mic on presence: OFF"}
            </button>
          </>
        )}
      </div>

      <div style={{ position: "absolute", top: 20, right: 20, display: "flex", gap: 8 }}>
        <button
          onClick={() => setPresenceMode((m) => (m === "sphere" ? "avatar" : "sphere"))}
          title="Presence mode: sphere (efficient fallback) or avatar (placeholder rig)"
          style={{
            display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 6,
            border: "1px solid #2a6f8a", background: "transparent", color: "#dff6ff", cursor: "pointer",
          }}
        >
          {presenceMode === "avatar" ? <User size={14} /> : <Circle size={14} />}
          {presenceMode === "avatar" ? "Avatar" : "Sphere"}
        </button>
        {Object.keys(LANGS).map((code) => (
          <button
            key={code}
            onClick={() => setLang(code)}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid #2a6f8a",
              background: lang === code ? "#5fe3ff" : "transparent",
              color: lang === code ? "#05060a" : "#dff6ff",
              cursor: "pointer",
            }}
          >
            {code === "en" ? "EN" : "فا"}
          </button>
        ))}
      </div>

      <div
        style={{
          position: "absolute",
          bottom: 40,
          left: "50%",
          transform: "translateX(-50%)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 14,
          width: "min(600px, 90vw)",
        }}
      >
        {!supported && (
          <div style={{ color: "#ff8a8a", fontSize: 13 }}>
            This browser does not support the Web Speech API. Try Chrome or Edge.
          </div>
        )}

        {transcript && (
          <div style={{ fontSize: 14, opacity: 0.8, textAlign: "center" }}>
            <strong>You:</strong> {transcript}
          </div>
        )}

        {/* Generic "working on it" indicator while the one HTTP round trip is in flight. There is
            no streaming, so this is NOT a live per-step progress feed - just an honest "not done
            yet" pulse. The real steps (if any) only appear below once the full response lands. */}
        {thinking && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, opacity: 0.7 }}>
            {[0, 1, 2].map((i) => (
              <span key={i} style={{
                width: 6, height: 6, borderRadius: "50%", background: "#5fe3ff",
                animation: `apexPulse 1.1s ${i * 0.15}s infinite ease-in-out`,
              }} />
            ))}
            <span>{lang === "fa" ? "در حال پردازش..." : "Working on it..."}</span>
          </div>
        )}

        {reply && (
          <div style={{ fontSize: 14, opacity: 0.95, textAlign: "center", color: replyIsError ? "#ff8a8a" : "#dff6ff" }}>
            <strong>Apex:</strong> {reply}
          </div>
        )}

        {/* Chain-of-thought checklist: what the backend ACTUALLY ran for this reply, shown only
            once it's known - see scripts/orchestrator.py's "steps" field. A single-step list
            (e.g. plain chat) renders fine too; it's just not very interesting to look at. */}
        {!thinking && steps.length > 0 && (
          <div style={{ fontSize: 12, opacity: 0.75, display: "flex", flexDirection: "column", gap: 3 }}>
            {steps.map((step, i) => (
              <div key={i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ color: "#7dffb0" }}>{"✓"}</span>
                <span>{step}</span>
              </div>
            ))}
          </div>
        )}

        <button
          onClick={toggleListening}
          disabled={!supported}
          style={{
            width: 64,
            height: 64,
            borderRadius: "50%",
            border: "none",
            background: listening ? "#ff5f6d" : "#5fe3ff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: supported ? "pointer" : "not-allowed",
            boxShadow: listening ? "0 0 24px #ff5f6d" : "0 0 24px #5fe3ff",
          }}
          aria-label={listening ? "Stop listening" : "Start listening"}
        >
          {listening ? <MicOff color="#05060a" size={26} /> : <Mic color="#05060a" size={26} />}
        </button>
      </div>

      <SwarmPanel open={swarmPanelOpen} onToggle={() => setSwarmPanelOpen((v) => !v)} />
    </div>
  );
}
