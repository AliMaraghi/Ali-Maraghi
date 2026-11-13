import { useEffect, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";

// Loads a single owner-provided .vrm asset (e.g. /models/ali.vrm - built with ReadyPlayerMe or an
// equivalent licensed rigging pipeline, from photos/video the owner chose, with the owner's own
// visual acceptance of the likeness). This component does NOT generate, infer or stylize a face -
// it only renders whatever rigged asset is placed at `url`. See
// docs/apex_status/COMPANION_PRESENCE_ADDENDUM_20261113.md section 3 for the full likeness policy.
// Missing/invalid files fail closed (onError callback), exactly like the existing face-api model
// loading elsewhere in this app - never a silent fallback to some other face.
const BLINK_INTERVAL_MS = [2500, 5500]; // randomised gap between blinks, like a real idle blink rate
const BLINK_DURATION_MS = 140;

export default function AvatarStage({ url, listening, speaking, thinking, mouthIntensityRef, onLoaded, onError }) {
  const [vrm, setVrm] = useState(null);
  const blinkRef = useRef(0); // 0..1 current blink closedness, mutated outside React state (per-frame)
  const blinkTimeoutRef = useRef(null);

  useEffect(() => {
    let disposed = false;
    let loadedVrm = null;
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    loader.load(
      url,
      (gltf) => {
        if (disposed) return;
        const result = gltf.userData.vrm;
        if (!result) {
          onError && onError("FILE_IS_NOT_A_VALID_VRM");
          return;
        }
        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        VRMUtils.combineSkeletons(gltf.scene);
        loadedVrm = result;
        setVrm(result);
        onLoaded && onLoaded();
      },
      undefined,
      () => { if (!disposed) onError && onError("VRM_FILE_NOT_FOUND"); }
    );
    return () => {
      disposed = true;
      if (loadedVrm) VRMUtils.deepDispose(loadedVrm.scene);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  useEffect(() => {
    function scheduleBlink() {
      const [min, max] = BLINK_INTERVAL_MS;
      blinkTimeoutRef.current = setTimeout(() => {
        blinkRef.current = 1;
        setTimeout(() => {
          blinkRef.current = 0;
          scheduleBlink();
        }, BLINK_DURATION_MS);
      }, min + Math.random() * (max - min));
    }
    scheduleBlink();
    return () => clearTimeout(blinkTimeoutRef.current);
  }, []);

  useFrame((state, delta) => {
    if (!vrm) return;
    vrm.update(delta);
    const t = state.clock.getElapsedTime();

    // Idle/listening/thinking/speaking state machine drives motion, not a fixed animation loop:
    // faster, shallower breathing while listening (alert), a brief head-tilt only while actually
    // waiting on the real network response (thinking - never artificially prolonged, see the
    // companion addendum's ban on a long "thinking" display just for hype), calm while idle.
    const breatheRate = listening ? 2.0 : thinking ? 1.6 : 1.0;
    const breathe = Math.sin(t * breatheRate) * (listening ? 0.015 : 0.01);
    const chest = vrm.humanoid && vrm.humanoid.getNormalizedBoneNode("chest");
    if (chest) chest.rotation.x = breathe;
    const head = vrm.humanoid && vrm.humanoid.getNormalizedBoneNode("head");
    if (head) head.rotation.y = thinking ? Math.sin(t * 1.1) * 0.08 : Math.sin(t * 0.2) * 0.05;

    if (vrm.expressionManager) {
      vrm.expressionManager.setValue("blink", blinkRef.current);
      // Mouth movement: if the caller supplies mouthIntensityRef (App.jsx sets it from the
      // SpeechSynthesisUtterance "boundary" event - word-timing, not real phonemes), use that;
      // otherwise fall back to an amplitude-driven sine approximation. EITHER WAY this is an
      // approximation, not real viseme lip-sync (companion addendum section 3) - word-boundary
      // timing is closer to real speech rhythm than a fixed sine wave, but still not phonemes.
      let mouth = 0;
      if (speaking) {
        mouth = mouthIntensityRef && mouthIntensityRef.current != null
          ? mouthIntensityRef.current
          : 0.35 + Math.abs(Math.sin(t * 9)) * 0.35;
      }
      vrm.expressionManager.setValue("aa", mouth);
      vrm.expressionManager.update();
    }
  });

  if (!vrm) return null;
  return <primitive object={vrm.scene} position={[0, -1.3, 0]} />;
}
