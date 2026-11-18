import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// PWA: cache the UI shell so it opens instantly on a phone. Production builds only - a service
// worker in `vite dev` would serve stale modules. API calls are cross-origin and never cached.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
    // When a newer version takes over an already-open app, load it once instead of leaving the
    // old screen up until the app is closed and reopened.
    if (navigator.serviceWorker.controller) {
      let reloaded = false;
      navigator.serviceWorker.addEventListener("controllerchange", () => {
        if (!reloaded) { reloaded = true; window.location.reload(); }
      });
    }
  });
}
