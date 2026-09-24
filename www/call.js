/*
 * Live-call frontend for Krishteen.
 *
 * IMPORTANT CHANGE FROM THE OLD VERSION:
 * The old call.js just clicked a Python-side "Start Call" and let
 * engine/call.py record from and speak through the SERVER's own
 * hardware. This version does the actual listening and speaking HERE,
 * in the browser, using getUserMedia + MediaRecorder for input and the
 * Audio element for output — so it works correctly no matter whose
 * device is looking at this page, not just the machine running Krishteen.
 *
 * Flow per turn:
 *   1. Record one utterance from the mic, using a simple volume-based
 *      silence detector to know when the person stopped talking.
 *   2. Send it to Python (eel.processCallTurn) for transcription + a reply.
 *   3. Play the reply's audio through this browser's speakers.
 *   4. Loop back to step 1, until an end-phrase / silence hangup / the
 *      user clicks "End Call".
 */

let callActive = false;
let callConnecting = false;
let sessionId = null;
let timerInterval = null;
let secondsElapsed = 0;

let mediaStream = null;
let audioContext = null;
let analyser = null;

const orb = document.getElementById('orb');
const orbRings = document.getElementById('orbRings');
const statusLabel = document.getElementById('status');
const callBtn = document.getElementById('callBtn');
const callBtnLabel = document.getElementById('callBtnLabel');
const callTimer = document.getElementById('callTimer');
const transcript = document.getElementById('transcript');
const transcriptEmpty = document.getElementById('transcriptEmpty');

const STATUS_TEXT = {
  connecting: 'Connecting…',
  connected: 'Connected',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Speaking…',
  ended: 'Call ended',
};

// --- Silence-detection tuning ---
const SPEAK_RMS_THRESHOLD = 0.02;      // volume level counted as "talking"
const SILENCE_AFTER_SPEECH_MS = 1200;  // stop recording after this much quiet, once speech was heard
const NO_SPEECH_TIMEOUT_MS = 8000;     // give up if nothing crosses the threshold at all
const MAX_UTTERANCE_MS = 20000;        // hard cap so one long ramble can't run forever
const POLL_MS = 100;

function setOrbState(state) {
  orb.className = 'orb ' + state;
  orbRings.className = 'orb-rings ' + (state === 'listening' || state === 'speaking' ? state : '');
}

function setStatus(state) {
  statusLabel.textContent = STATUS_TEXT[state] || state;
  setOrbState(state);
}

function startTimer() {
  secondsElapsed = 0;
  callTimer.textContent = '00:00';
  timerInterval = setInterval(() => {
    secondsElapsed += 1;
    const m = String(Math.floor(secondsElapsed / 60)).padStart(2, '0');
    const s = String(secondsElapsed % 60).padStart(2, '0');
    callTimer.textContent = `${m}:${s}`;
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
}

function addBubble(role, text) {
  if (!text) return;
  if (transcriptEmpty) transcriptEmpty.remove();
  const bubble = document.createElement('div');
  bubble.className = 'bubble ' + role;
  bubble.textContent = text;
  transcript.appendChild(bubble);
  transcript.scrollTop = transcript.scrollHeight;
}

// ---- Mic setup ----

async function setupMic() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('This browser does not support microphone access (or this page is not being served over https/localhost).');
  }

  // getUserMedia() never resolves OR rejects until the mic-permission prompt
  // is answered. Some browsers (Opera/Opera GX in particular) show that
  // prompt as a tiny icon in the address bar instead of a banner — easy to
  // miss, and if nobody clicks it, this call hangs forever with no error.
  // Race it against a timeout so the UI can say something useful instead
  // of spinning on "Connecting..." indefinitely.
  const micPromise = navigator.mediaDevices.getUserMedia({ audio: true });
  const timeoutPromise = new Promise((_, reject) => {
    setTimeout(() => reject(new Error('MIC_PERMISSION_TIMEOUT')), 10000);
  });

  mediaStream = await Promise.race([micPromise, timeoutPromise]);

  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioContext.createMediaStreamSource(mediaStream);
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
}

function teardownMic() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }
  if (audioContext) {
    audioContext.close().catch(() => {});
    audioContext = null;
  }
  analyser = null;
}

function currentRms() {
  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);
  let sumSquares = 0;
  for (let i = 0; i < data.length; i++) {
    const norm = (data[i] - 128) / 128;
    sumSquares += norm * norm;
  }
  return Math.sqrt(sumSquares / data.length);
}

function pickMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
  for (const type of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(type)) return type;
  }
  return '';
}

/**
 * Records one utterance. Resolves with { blob, mimeType } once the person
 * has gone quiet after speaking, or with { blob: null } if nothing
 * intelligible was heard within NO_SPEECH_TIMEOUT_MS (still resolves,
 * rather than hanging forever, so the call loop can treat it as a
 * silent/empty turn same as the old server-side timeout did).
 */
function recordUtterance() {
  return new Promise((resolve) => {
    const mimeType = pickMimeType();
    const recorder = mimeType
      ? new MediaRecorder(mediaStream, { mimeType })
      : new MediaRecorder(mediaStream);
    const chunks = [];

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };

    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearInterval(pollHandle);
      if (recorder.state !== 'inactive') recorder.stop();
    };

    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: mimeType || 'audio/webm' });
      resolve({ blob, mimeType: mimeType || 'audio/webm' });
    };

    let spokeAny = false;
    let lastLoudAt = Date.now();
    const startedAt = Date.now();

    const pollHandle = setInterval(() => {
      if (!callActive) {
        finish();
        return;
      }
      const rms = currentRms();
      const now = Date.now();

      if (rms > SPEAK_RMS_THRESHOLD) {
        spokeAny = true;
        lastLoudAt = now;
      }

      if (!spokeAny && now - startedAt > NO_SPEECH_TIMEOUT_MS) {
        finish();
        return;
      }
      if (spokeAny && now - lastLoudAt > SILENCE_AFTER_SPEECH_MS) {
        finish();
        return;
      }
      if (now - startedAt > MAX_UTTERANCE_MS) {
        finish();
        return;
      }
    }, POLL_MS);

    recorder.start();
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1] || '');
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function playAudioBase64(base64Wav) {
  return new Promise((resolve) => {
    if (!base64Wav) {
      resolve();
      return;
    }
    const audio = new Audio('data:audio/wav;base64,' + base64Wav);
    audio.onended = () => resolve();
    audio.onerror = () => resolve();
    audio.play().catch(() => resolve());
  });
}

// ---- Call loop ----

async function listenLoop() {
  while (callActive) {
    setStatus('listening');
    const { blob } = await recordUtterance();
    if (!callActive) break;

    setStatus('thinking');
    let result;
    try {
      const base64Audio = await blobToBase64(blob);
      result = await eel.processCallTurn(sessionId, base64Audio, 'webm')();
    } catch (err) {
      console.error('processCallTurn failed:', err);
      break;
    }

    if (!callActive) break;

    if (result.error) {
      console.error(result.error);
      continue;
    }

    if (result.query) addBubble('user', result.query);

    if (result.response) {
      addBubble('assistant', result.response);
      setStatus('speaking');
      await playAudioBase64(result.audio_base64);
    }

    if (result.ended) {
      hangUp();
      break;
    }
  }
}

function hangUp() {
  callActive = false;
  callConnecting = false;
  callBtn.classList.remove('active', 'connecting');
  callBtnLabel.textContent = 'Start Call';
  stopTimer();
  teardownMic();
  setStatus('ended');
}

// ---- Button ----

callBtn.addEventListener('click', async () => {
  if (callConnecting) return;

  if (!callActive) {
    callConnecting = true;
    callBtn.classList.add('connecting');
    callBtnLabel.textContent = 'Connecting…';
    transcript.innerHTML = '';
    setStatus('connecting');

    try {
      await setupMic();
    } catch (err) {
      console.error('Mic access failed:', err);
      setStatus('ended');
      if (err && err.message === 'MIC_PERMISSION_TIMEOUT') {
        statusLabel.textContent = 'Still waiting on mic permission — check the address bar for a mic icon and allow access, then try again.';
      } else {
        statusLabel.textContent = 'Microphone access denied or unavailable.';
      }
      callConnecting = false;
      callBtn.classList.remove('connecting');
      callBtnLabel.textContent = 'Start Call';
      return;
    }

    let started;
    try {
      started = await eel.startCall()();
    } catch (err) {
      console.error('startCall failed:', err);
      teardownMic();
      setStatus('ended');
      callConnecting = false;
      callBtn.classList.remove('connecting');
      callBtnLabel.textContent = 'Start Call';
      return;
    }

    sessionId = started.session_id;
    callConnecting = false;
    callActive = true;
    callBtn.classList.remove('connecting');
    callBtn.classList.add('active');
    callBtnLabel.textContent = 'End Call';
    setStatus('connected');
    startTimer();

    addBubble('assistant', started.greeting);
    setStatus('speaking');
    await playAudioBase64(started.greeting_audio_base64);

    listenLoop();
  } else {
    callBtnLabel.textContent = 'Ending…';
    const endingSessionId = sessionId;
    hangUp();
    try {
      await eel.endCall(endingSessionId)();
    } catch (err) {
      console.error('endCall failed:', err);
    }
  }
});

setOrbState('idle');