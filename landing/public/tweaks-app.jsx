// tweaks-app.jsx — Terminal Ops tweak controls

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "palette": "default",
  "scanlines": true,
  "pixelHeaders": true,
  "alwaysReplayIntro": false
}/*EDITMODE-END*/;

function TerminalOpsTweaks() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Re-apply to page on any change
  React.useEffect(() => {
    if (window.__applyTweaks) window.__applyTweaks(t);
  }, [t]);

  return (
    <TweaksPanel title="Tweaks — Terminal Ops">
      <TweakSection label="Palette" />
      <TweakRadio
        label="Mode"
        value={t.palette}
        options={["default", "neon", "dusk", "mono"]}
        onChange={(v) => setTweak("palette", v)}
      />

      <TweakSection label="Arcade FX" />
      <TweakToggle
        label="CRT scanlines"
        value={t.scanlines}
        onChange={(v) => setTweak("scanlines", v)}
      />
      <TweakToggle
        label="Pixel-font headers"
        value={t.pixelHeaders}
        onChange={(v) => setTweak("pixelHeaders", v)}
      />

      <TweakSection label="Intro" />
      <TweakButton
        label="▶ Replay ROUND 1 / FIGHT!"
        onClick={() => window.__replayIntro && window.__replayIntro()}
      />
    </TweaksPanel>
  );
}

const __twkRoot = ReactDOM.createRoot(document.getElementById("tweaks-root"));
__twkRoot.render(<TerminalOpsTweaks />);
