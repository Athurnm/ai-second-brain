// meetbot in-page audio tap.
//
// Injected by src/meet.rs once the bot is admitted to the call. It mixes every
// remote MediaStream the page is playing into one WebAudio graph, downsamples
// to the canonical 16 kHz mono, and ships base64 i16-LE frames back to Rust
// through the CDP binding created with `Runtime.addBinding`.
//
// The double-underscore MEETBOT placeholder tokens below are substituted by
// meet.rs before evaluation, so every DOM selector in here still comes from the
// single selector table at the top of src/meet.rs — never hardcode a selector
// in this file.
//
// Returns an object (never a bare `null`: CDP drops null return values and
// `EvaluationResult::into_value` would then fail):
//   { status: "started" | "already-running" | "no-binding" | "no-audiocontext" }
(() => {
  'use strict';

  var BINDING = __MEETBOT_BINDING__;
  var FRAME_SAMPLES = __MEETBOT_FRAME_SAMPLES__;
  var TARGET_RATE = __MEETBOT_TARGET_RATE__;
  var SPEAKING_SELECTORS = __MEETBOT_SPEAKING_SELECTORS__;
  var SPEAKER_NAME_SELECTORS = __MEETBOT_SPEAKER_NAME_SELECTORS__;
  var SPEAKER_TILE_SELECTORS = __MEETBOT_SPEAKER_TILE_SELECTORS__;
  var RESCAN_MS = 1000;

  if (window.__meetbotCapture) {
    return { status: 'already-running' };
  }

  var send = window[BINDING];
  if (typeof send !== 'function') {
    return { status: 'no-binding' };
  }

  var Ctor = window.AudioContext || window.webkitAudioContext;
  if (!Ctor) {
    return { status: 'no-audiocontext' };
  }

  // Asking for a 16 kHz context makes Chrome resample every source for us, so
  // the samples that reach `onaudioprocess` are already at the rate whisper
  // wants. Rust still re-checks `rate` on every frame and resamples if the
  // browser ignored the hint.
  var ctx = new Ctor({ sampleRate: TARGET_RATE });

  var mixer = ctx.createGain();
  mixer.gain.value = 1;

  // ScriptProcessorNode is deprecated but is the only tap that works without
  // shipping a separate AudioWorklet module file, and it is stable in headless
  // Chrome. 4096 frames ≈ 256 ms at 16 kHz.
  var proc = ctx.createScriptProcessor(4096, 1, 1);

  // A muted terminal sink: the graph has to reach `ctx.destination` for the
  // processor to be pulled, but the bot must never play the meeting back out.
  var sink = ctx.createGain();
  sink.gain.value = 0;

  mixer.connect(proc);
  proc.connect(sink);
  sink.connect(ctx.destination);

  var state = {
    seq: 0,
    sentSamples: 0,
    buf: new Float32Array(FRAME_SAMPLES),
    used: 0,
    attached: Object.create(null),
    attachedCount: 0,
    dropped: 0,
    stopped: false,
    timer: null
  };
  window.__meetbotCapture = state;

  var B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

  function base64(bytes) {
    var out = '';
    var i = 0;
    var n = bytes.length;
    while (i + 2 < n) {
      var a = bytes[i], b = bytes[i + 1], c = bytes[i + 2];
      out += B64[a >> 2];
      out += B64[((a & 3) << 4) | (b >> 4)];
      out += B64[((b & 15) << 2) | (c >> 6)];
      out += B64[c & 63];
      i += 3;
    }
    var rem = n - i;
    if (rem === 1) {
      var x = bytes[i];
      out += B64[x >> 2];
      out += B64[(x & 3) << 4];
      out += '==';
    } else if (rem === 2) {
      var y = bytes[i], z = bytes[i + 1];
      out += B64[y >> 2];
      out += B64[((y & 3) << 4) | (z >> 4)];
      out += B64[(z & 15) << 2];
      out += '=';
    }
    return out;
  }

  function clean(text) {
    if (!text) {
      return null;
    }
    var t = String(text).replace(/\s+/g, ' ').trim();
    if (!t || t.length > 80) {
      return null;
    }
    return t;
  }

  function nameFor(node) {
    var roots = [node];
    for (var s = 0; s < SPEAKER_TILE_SELECTORS.length; s++) {
      try {
        var tile = node.closest(SPEAKER_TILE_SELECTORS[s]);
        if (tile) {
          roots.push(tile);
        }
      } catch (e) { /* selector unsupported by this Chrome */ }
    }
    if (node.parentElement) {
      roots.push(node.parentElement);
    }
    for (var r = 0; r < roots.length; r++) {
      var root = roots[r];
      for (var i = 0; i < SPEAKER_NAME_SELECTORS.length; i++) {
        var sel = SPEAKER_NAME_SELECTORS[i];
        if (sel === ':self') {
          var own = clean(root.getAttribute && (root.getAttribute('data-participant-name') || root.getAttribute('aria-label')));
          if (own) {
            return own;
          }
          continue;
        }
        try {
          var found = root.querySelector(sel);
          if (found) {
            var got = clean(found.getAttribute('aria-label') || found.textContent);
            if (got) {
              return got;
            }
          }
        } catch (e) { /* selector unsupported */ }
      }
    }
    return null;
  }

  // Best effort only. When Google reshuffles the speaking indicator this
  // returns null and Rust falls back to `speaker: None`, which the transcript
  // renders as "Unknown" — degraded, never fatal.
  function currentSpeaker() {
    for (var i = 0; i < SPEAKING_SELECTORS.length; i++) {
      var nodes;
      try {
        nodes = document.querySelectorAll(SPEAKING_SELECTORS[i]);
      } catch (e) {
        continue;
      }
      for (var j = 0; j < nodes.length; j++) {
        var name = nameFor(nodes[j]);
        if (name) {
          return name;
        }
      }
    }
    return null;
  }

  function flushFrame() {
    var n = state.used;
    if (n <= 0) {
      return;
    }
    var pcm = new Int16Array(n);
    for (var i = 0; i < n; i++) {
      var s = state.buf[i];
      if (s > 1) {
        s = 1;
      } else if (s < -1) {
        s = -1;
      }
      pcm[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
    }
    var offset = state.sentSamples / TARGET_RATE;
    state.sentSamples += n;
    state.used = 0;
    state.seq += 1;
    try {
      send(JSON.stringify({
        seq: state.seq,
        offset: offset,
        rate: TARGET_RATE,
        speaker: currentSpeaker(),
        pcm: base64(new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength))
      }));
    } catch (e) {
      // The binding is gone (page torn down mid-call). Stop trying so the
      // audio thread does not spin on exceptions.
      state.dropped += 1;
      if (state.dropped > 10) {
        state.stopped = true;
      }
    }
  }

  proc.onaudioprocess = function (ev) {
    if (state.stopped) {
      return;
    }
    var input = ev.inputBuffer.getChannelData(0);
    for (var i = 0; i < input.length; i++) {
      state.buf[state.used] = input[i];
      state.used += 1;
      if (state.used >= FRAME_SAMPLES) {
        flushFrame();
      }
    }
  };

  // Google Meet plays each remote participant through its own media element.
  // Elements come and go as people join, leave and get re-tiled, so rescan on
  // an interval and connect any stream we have not already wired in.
  function attachStreams() {
    var els = document.querySelectorAll('audio, video');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var ms = el.srcObject;
      if (!ms || typeof ms.getAudioTracks !== 'function') {
        continue;
      }
      if (ms.getAudioTracks().length === 0) {
        continue;
      }
      var id = ms.id || ('anon-' + i);
      if (state.attached[id]) {
        continue;
      }
      try {
        var src = ctx.createMediaStreamSource(ms);
        src.connect(mixer);
        state.attached[id] = true;
        state.attachedCount += 1;
      } catch (e) { /* stream already consumed by another context */ }
    }
  }

  attachStreams();
  state.timer = setInterval(attachStreams, RESCAN_MS);

  if (ctx.state === 'suspended' && typeof ctx.resume === 'function') {
    ctx.resume();
  }

  // Debugging hook. When a call comes back with no audio, evaluate
  // `window.__meetbotCaptureStats()` in the page: `attached` proves the remote
  // streams were found, `seq` proves the processor is actually being pulled,
  // and `ctxState` distinguishes a suspended context from a stalled one.
  window.__meetbotCaptureStats = function () {
    return {
      seq: state.seq,
      used: state.used,
      attached: state.attachedCount,
      dropped: state.dropped,
      sentSamples: state.sentSamples,
      ctxState: ctx.state,
      ctxRate: ctx.sampleRate,
      // The audio clock. Rust gates capture start on this ADVANCING between two
      // probes: in headless, a context can report 'running' while the render
      // quantum is never pumped, and currentTime is the only reliable witness
      // that samples are actually flowing. Do not replace with a fixed sleep.
      ctxTime: ctx.currentTime
    };
  };

  window.__meetbotStopCapture = function () {
    state.stopped = true;
    if (state.timer !== null) {
      clearInterval(state.timer);
      state.timer = null;
    }
    try { proc.disconnect(); } catch (e) { /* already torn down */ }
    try { mixer.disconnect(); } catch (e) { /* already torn down */ }
    try { ctx.close(); } catch (e) { /* already closed */ }
    return { status: 'stopped' };
  };

  return { status: 'started' };
})()
