/* JARVIS · Claude Code memory HUD — front end.
   Talks to the local Python server over NDJSON. The brain is your `claude` CLI,
   so every token here is billed to your subscription, not an API key. */
'use strict';

var $ = function (s) { return document.querySelector(s); };
var TOKEN = document.querySelector('meta[name=jarvis-token]').content;
var headers = function (extra) {
  return Object.assign({ 'X-Jarvis-Token': TOKEN }, extra || {});
};
var esc = function (s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
};
var now = function () { return new Date().toTimeString().slice(0, 8); };

var graph = null, hiddenTypes = new Set(), running = false, activeCtl = null;
var answerText = '', answerBubble = null, GRAPH = { nodes: [], links: [], hubs: [], counts: [] };

/* ── action log ───────────────────────────── */
function log(kind, label, msg) {
  var e = document.createElement('div');
  e.className = 'entry k-' + kind;
  e.innerHTML = '<div class="top"><span class="ts">' + now() + '</span>'
    + '<span class="kind">' + esc(label) + '</span></div>'
    + (msg ? '<div class="msg">' + esc(msg) + '</div>' : '');
  var box = $('#log');
  box.insertBefore(e, box.firstChild);
  while (box.children.length > 45) box.removeChild(box.lastChild);
}

/* Fish Audio reads [square brackets] as stage directions, never as words. We
   send the text through untouched so the model performs them, but on screen we
   render each tag as a chip so you can see the direction and hear the result.
   The browser speechSynthesis fallback has no such notion, so it gets a
   stripped copy — otherwise it literally reads "dry" out loud. */
var TONE_RE = /\[([^\][]{1,90})\]/g;

function stripTones(text) {
  return String(text || '').replace(TONE_RE, ' ').replace(/\s{2,}/g, ' ').trim();
}

function lastTone(text) {
  var found = null, m;
  TONE_RE.lastIndex = 0;
  while ((m = TONE_RE.exec(text)) !== null) found = m[1];
  return found;
}

function renderSpoken(el, text) {
  var html = '', last = 0, m;
  TONE_RE.lastIndex = 0;
  while ((m = TONE_RE.exec(text)) !== null) {
    html += esc(text.slice(last, m.index));
    html += '<span class="tone">' + esc(m[1]) + '</span>';
    last = m.index + m[0].length;
  }
  html += esc(text.slice(last));
  el.innerHTML = html;
}

function bubble(who, text) {
  var b = document.createElement('div');
  b.className = 'bubble ' + who;
  if (who === 'jarvis') renderSpoken(b, text); else b.textContent = text;
  $('#transcript').appendChild(b);
  $('#transcript').scrollTop = $('#transcript').scrollHeight;
  return b;
}

function setVoiceState(state, cls) {
  $('#voiceState').textContent = state;
  $('#voiceDot').className = 'dot ' + (cls || '');
}

/* ── panels ───────────────────────────────── */
function renderHubs() {
  $('#hubs').innerHTML = GRAPH.hubs.map(function (h) {
    return '<li data-id="' + esc(h.id) + '">'
      + '<i class="swatch" style="background:' + esc(h.colour) + '"></i>'
      + '<span class="nm">' + esc(h.title) + '</span>'
      + '<span class="ct">' + h.degree + '</span></li>';
  }).join('');
  Array.prototype.forEach.call($('#hubs').children, function (li) {
    li.onclick = function () { focusNode(li.dataset.id); };
  });
}

function renderFilter() {
  var colours = {};
  GRAPH.nodes.forEach(function (n) { colours[n.type] = n.colour; });
  $('#filter').innerHTML = GRAPH.counts.map(function (pair) {
    var t = pair[0], c = pair[1];
    return '<li data-type="' + esc(t) + '" class="' + (hiddenTypes.has(t) ? 'off' : '') + '">'
      + '<i class="swatch" style="background:' + esc(colours[t] || '#8fa3bf') + '"></i>'
      + '<span class="nm">' + esc(t.charAt(0).toUpperCase() + t.slice(1)) + '</span>'
      + '<span class="ct">' + c + '</span></li>';
  }).join('');
  Array.prototype.forEach.call($('#filter').children, function (li) {
    li.onclick = function () {
      var t = li.dataset.type;
      if (hiddenTypes.has(t)) hiddenTypes.delete(t); else hiddenTypes.add(t);
      graph.setFilter(hiddenTypes);
      renderFilter();
    };
  });
}

function renderInspector(node, trace) {
  var box = $('#inspector');
  if (!node) {
    box.innerHTML = '<p class="hint">Click a node to focus it — only that node and its '
      + 'connections light up, and you can read its note here. Shift-click a second node '
      + 'to trace the path.</p>';
    return;
  }
  var links = (graph.adj.get(node.id) || []).slice(0, 12);
  var html = '<div class="ititle">' + esc(node.title) + '</div>'
    + '<div class="imeta">' + esc(node.type) + ' · ' + node.degree + ' links'
    + (node.updated ? ' · ' + esc(node.updated) : '') + '</div>'
    + '<div class="ibody">' + esc(node.snippet || 'No body text.') + '</div>';
  if (trace && trace.length > 1) {
    html += '<div class="imeta" style="margin-top:10px">path · ' + trace.length + ' hops</div>'
      + '<div class="ibody">' + trace.map(function (id) {
        var n = graph.byId.get(id); return esc(n ? n.title : id);
      }).join(' → ') + '</div>';
  }
  if (links.length) {
    html += '<div class="ilinks">' + links.map(function (id) {
      var n = graph.byId.get(id);
      return '<span class="chip" data-id="' + esc(id) + '">' + esc(n ? n.title : id) + '</span>';
    }).join('') + '</div>';
  }
  box.innerHTML = html;
  Array.prototype.forEach.call(box.querySelectorAll('.chip'), function (c) {
    c.onclick = function () { focusNode(c.dataset.id); };
  });
}

function focusNode(id) {
  if (graph.setFocus(id, false)) {
    log('mem', 'MEMORY', 'focused ' + id);
  }
}

var MATRIX = [
  ['/recall', 'search vault'], ['/graph', 'reload memory'],
  ['/goal', 'objective'], ['/mission', 'queue'],
  ['/profile', 'remember'], ['/status', 'runtime'],
  ['/new', 'fresh session'], ['/help', 'commands']
];
function renderMatrix() {
  $('#matrix').innerHTML = MATRIX.map(function (m) {
    return '<div class="mcell" data-cmd="' + m[0] + '"><b>' + m[0] + '</b><span>' + m[1] + '</span></div>';
  }).join('');
  Array.prototype.forEach.call($('#matrix').children, function (cell) {
    cell.onclick = function () {
      var cmd = cell.dataset.cmd;
      if (['/recall', '/goal', '/mission', '/profile'].indexOf(cmd) >= 0) {
        $('#ask').value = cmd + ' ';
        $('#ask').focus();
      } else { transmit(cmd); }
    };
  });
}

/* ── data ─────────────────────────────────── */
async function loadGraph(force) {
  var res = await fetch('/api/graph' + (force ? '?force=1' : ''), { headers: headers() });
  GRAPH = await res.json();
  graph.setData(GRAPH);
  renderHubs(); renderFilter();
  $('#stageCount').textContent = GRAPH.total + ' notes · ' + GRAPH.links.length + ' links';
  $('#sVault').textContent = GRAPH.total + ' notes';
  setTimeout(function () { graph.fit(); }, 350);
}

async function loadStatus() {
  try {
    var s = await (await fetch('/api/status', { headers: headers() })).json();
    $('#pGateway').textContent = 'online :' + location.port;
    $('#pBrain').textContent = s.runtime === 'claude' ? (s.version || 'Claude CLI') : 'MOCK';
    $('#pVoice').textContent = s.server_voice ? 'Fish Audio' : 'browser';
    document.querySelectorAll('.pill .dot')[2].className = 'dot ' + (s.server_voice ? 'ok' : 'warn');
    $('#sModel').textContent = s.model;
    $('#cliBadge').textContent = s.runtime === 'claude' ? 'CLAUDE CLI' : 'CLI OFFLINE';
    window.__serverVoice = s.server_voice;
  } catch (e) { $('#pGateway').textContent = 'offline'; }
}

/* ── the run ──────────────────────────────── */
async function transmit(message, opts) {
  message = (message || '').trim();
  if (!message) return;
  if (running) { log('note', 'BUSY', 'still working — "' + message.slice(0, 36) + '" not sent'); return; }
  opts = opts || {};
  running = true;
  answerText = '';
  document.body.classList.remove('boot');
  document.body.classList.add('running');
  if (graph) graph.setActivity(1);
  $('#toneNow').textContent = '—';
  setVoiceState('THINKING', 'hot');
  bubble('me', message);
  answerBubble = bubble('jarvis', '');
  answerBubble.classList.add('thinking');
  log('run', 'RUN', message.slice(0, 70));

  var t0 = performance.now();
  try {
    activeCtl = new AbortController();
    var res = await fetch('/api/run', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify({ message: message, fresh: /^\/new\b/.test(message) }),
      signal: activeCtl.signal
    });
    if (!res.ok) throw new Error('backend HTTP ' + res.status);
    var reader = res.body.getReader(), dec = new TextDecoder(), buf = '';
    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += dec.decode(chunk.value, { stream: true });
      var nl;
      while ((nl = buf.indexOf('\n')) >= 0) {
        var line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        if (line) handleEvent(JSON.parse(line));
      }
    }
  } catch (e) {
    if (e && e.name === 'AbortError') log('note', 'CANCEL', 'run cancelled');
    else { log('error', 'ERROR', String(e).slice(0, 160)); answerBubble.textContent = String(e).slice(0, 160); }
  }
  activeCtl = null;
  running = false;
  document.body.classList.remove('running');
  if (graph) graph.setActivity(0);
  answerBubble.classList.remove('thinking');
  $('#sLatency').textContent = Math.round(performance.now() - t0) + 'ms';
  setVoiceState('IDLE', '');
  if (answerText.trim() && opts.speak !== false) speak(answerText.trim());
}

function handleEvent(ev) {
  switch (ev.t) {
    case 'status':
      if (ev.session_id) $('#sSession').textContent = ev.session_id.slice(0, 8);
      if (ev.model) $('#sModel').textContent = ev.model;
      log('ok', 'STATUS', 'claude online · tools=' + (ev.tools || 0)
        + ' · permission=' + (ev.permission || '—'));
      break;
    case 'latency':
      $('#sLatency').textContent = ev.ms + 'ms';
      log('note', 'LATENCY', 'first token after ' + ev.ms + 'ms');
      break;
    case 'tool':
      if (ev.phase === 'use') log('tool', 'TOOL', '→ ' + ev.name + '(' + (ev.input || '') + ')');
      else log('tool', 'TOOL', '✓ ' + (ev.ok === false ? 'error' : 'ok'));
      break;
    case 'focus':
      if (graph.setFocus(ev.id, false)) log('mem', 'MEMORY', 'vault hit → ' + ev.id);
      break;
    case 'graph':
      loadGraph(true);
      break;
    case 'delta':
      answerText += ev.text;
      renderSpoken(answerBubble, answerText);
      var tone = lastTone(answerText);
      if (tone) $('#toneNow').textContent = tone;
      $('#transcript').scrollTop = $('#transcript').scrollHeight;
      break;
    case 'usage':
      $('#sTokens').textContent = (ev.total_tokens || 0).toLocaleString();
      break;
    case 'ratelimit':
      $('#sLimit').textContent = (ev.status || '—') + (ev.window ? ' · ' + ev.window.replace('_', ' ') : '');
      break;
    case 'note':
      log('note', 'NOTE', ev.message || '');
      break;
    case 'error':
      log('error', 'ERROR', ev.message || '');
      answerBubble.textContent = ev.message || 'error';
      break;
    case 'complete':
      if (ev.session_id) $('#sSession').textContent = String(ev.session_id).slice(0, 8);
      log('ok', 'DONE', (ev.ms || 0) + 'ms');
      break;
  }
}

/* ── voice ────────────────────────────────── */
async function speak(text) {
  setVoiceState('SPEAKING', 'hot');
  if (window.__serverVoice) {
    try {
      var res = await fetch('/api/speak', {
        method: 'POST', headers: headers({ 'content-type': 'application/json' }),
        body: JSON.stringify({ text: text })
      });
      if (res.ok) {
        var audio = new Audio(URL.createObjectURL(await res.blob()));
        audio.onended = function () { setVoiceState('IDLE', ''); };
        await audio.play();
        return;
      }
    } catch (e) { log('note', 'VOICE', 'server voice failed, using browser'); }
  }
  if (!window.speechSynthesis) { setVoiceState('IDLE', ''); return; }
  var u = new SpeechSynthesisUtterance(stripTones(text));
  u.rate = 1.02; u.pitch = 0.92;
  u.onend = function () { setVoiceState('IDLE', ''); };
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

/* Listening has two possible paths and both can fail, so try them in order and
   say exactly which one broke instead of logging a bare "network".

   1. MediaRecorder -> /api/listen -> Fish Audio ASR. Works in any browser and
      keeps audio on the same provider as the voice. Needs Fish API credit,
      which is billed separately from the platform balance that TTS uses.
   2. Browser Web Speech API. Free, but it relies on Google's speech service, so
      Chromium builds shipped without a Google API key (Brave, most notably)
      fail instantly with error "network". */
function browserRecognise(onText, onFail) {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { onFail('this browser has no speech recognition'); return null; }
  var rec = new SR();
  rec.continuous = false; rec.interimResults = false; rec.lang = 'en-US';
  rec.onresult = function (e) { onText(e.results[0][0].transcript); };
  rec.onerror = function (e) {
    if (e.error === 'network') {
      onFail('browser speech needs Google\u2019s service — Brave blocks it. '
           + 'Open this in Chrome, or add Fish Audio API credit for on-server listening.');
    } else if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
      onFail('microphone permission denied — allow it in site settings');
    } else {
      onFail('speech recognition failed: ' + e.error);
    }
  };
  return rec;
}

function setupMic() {
  var btn = $('#btnMic');
  var recorder = null, chunks = [], busy = false;

  function stopUI() {
    busy = false;
    btn.classList.remove('rec');
    setVoiceState('IDLE', '');
  }

  function fallbackToBrowser() {
    var rec = browserRecognise(function (text) {
      log('note', 'VOICE', 'heard: "' + text + '"');
      stopUI();
      transmit(text);
    }, function (why) {
      log('error', 'VOICE', why);
      stopUI();
    });
    if (!rec) { stopUI(); return; }
    setVoiceState('LISTENING', 'hot');
    btn.classList.add('rec');
    rec.onend = function () { if (busy) stopUI(); };
    try { rec.start(); } catch (e) { log('error', 'VOICE', String(e)); stopUI(); }
  }

  async function sendClip(blob) {
    setVoiceState('TRANSCRIBING', 'hot');
    try {
      var res = await fetch('/api/listen', {
        method: 'POST',
        headers: headers({ 'content-type': blob.type || 'audio/webm' }),
        body: blob
      });
      var data = await res.json();
      if (res.ok && data.text) {
        log('note', 'VOICE', 'heard: "' + data.text + '"');
        stopUI();
        transmit(data.text);
        return;
      }
      var msg = (data && data.error) || ('HTTP ' + res.status);
      if (/insufficient api credit/i.test(msg)) {
        log('error', 'VOICE', 'Fish Audio ASR needs API credit (billed separately '
          + 'from your plan balance). Falling back to browser speech.');
      } else {
        log('error', 'VOICE', 'server transcription failed: ' + msg.slice(0, 120));
      }
    } catch (e) {
      log('error', 'VOICE', 'server transcription unreachable: ' + String(e).slice(0, 80));
    }
    fallbackToBrowser();
  }

  btn.onclick = async function () {
    if (busy && recorder && recorder.state === 'recording') { recorder.stop(); return; }
    if (busy) return;
    busy = true;

    if (!window.__serverVoice || !navigator.mediaDevices || !window.MediaRecorder) {
      fallbackToBrowser();
      return;
    }
    try {
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      recorder = new MediaRecorder(stream);
      recorder.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        btn.classList.remove('rec');
        sendClip(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }));
      };
      recorder.start();
      btn.classList.add('rec');
      setVoiceState('LISTENING', 'hot');
      log('note', 'VOICE', 'recording — click the mic again to send');
    } catch (e) {
      log('error', 'VOICE', 'microphone unavailable: ' + String(e).slice(0, 80));
      fallbackToBrowser();
    }
  };
}

/* ── boot ─────────────────────────────────── */
window.addEventListener('DOMContentLoaded', function () {
  graph = new MemoryGraph($('#graph'), {
    onSelect: function (node, trace) { renderInspector(node, trace); }
  });
  window.__jarvisGraph = graph;   // handy from devtools while tuning layout

  // dial ticks
  var ticks = '';
  for (var i = 0; i < 60; i++) {
    var a = (i / 60) * Math.PI * 2, r1 = 92, r2 = i % 5 === 0 ? 82 : 87;
    ticks += '<line x1="' + (100 + Math.cos(a) * r1).toFixed(1) + '" y1="' + (100 + Math.sin(a) * r1).toFixed(1)
      + '" x2="' + (100 + Math.cos(a) * r2).toFixed(1) + '" y2="' + (100 + Math.sin(a) * r2).toFixed(1)
      + '" stroke="rgba(95,228,255,' + (i % 5 === 0 ? '.35' : '.15') + ')" stroke-width="1"/>';
  }
  $('#ticks').innerHTML = ticks;

  renderMatrix();
  loadStatus();
  loadGraph(false);
  setupMic();
  setVoiceState('IDLE', '');

  $('#btnSend').onclick = function () { var v = $('#ask').value; $('#ask').value = ''; transmit(v); };
  $('#ask').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { var v = $('#ask').value; $('#ask').value = ''; transmit(v); }
  });
  $('#btnFit').onclick = function () { graph.fit(); };
  $('#btnLabels').onclick = function () {
    graph.showLabels = !graph.showLabels;
    $('#btnLabels').classList.toggle('on', graph.showLabels);
  };
  $('#btnDim').onclick = function () {
    graph.dim = !graph.dim;
    $('#btnDim').classList.toggle('on', graph.dim);
  };
  $('#btnLabels').classList.add('on');

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (activeCtl) activeCtl.abort();
      fetch('/api/cancel', { method: 'POST', headers: headers({ 'content-type': 'application/json' }), body: '{}' });
      graph.setFocus(null);
    }
    if (e.key === '/' && document.activeElement !== $('#ask')) { e.preventDefault(); $('#ask').focus(); }
  });

  setInterval(loadStatus, 20000);
  log('ok', 'BOOT', 'HUD online · claude code · local vault');
});
