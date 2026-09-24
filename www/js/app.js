/* ================================================================
   KRISHTEEN — Full Browser Voice (Wake Word + Live Call)
   Works on ANY device via ngrok. Uses browser Web Speech API.
   ================================================================ */

/* ---------- Utilities ---------- */
const $ = (sel) => document.querySelector(sel);

function addChatMessage(role, text) {
    const log = document.getElementById('chatLog');
    const inline = document.getElementById('inlineChat');
    const wrap = document.createElement('div');
    wrap.className = 'bubble-wrap ' + role;

    const label = document.createElement('div');
    label.className = 'bubble-label';
    label.textContent = role === 'user' ? 'You' : 'Krishteen';

    const bub = document.createElement('div');
    bub.className = 'bubble';
    bub.textContent = text;

    wrap.appendChild(label);
    wrap.appendChild(bub);

    if (log) log.appendChild(wrap.cloneNode(true));
    if (log) log.scrollTop = log.scrollHeight;

    if (inline) {
        inline.style.display = 'flex';
        inline.appendChild(wrap);
        inline.scrollTop = inline.scrollHeight;
    }
}
window.addChatMessage = addChatMessage;

function showReminderToast(message, iconClass) {
    const toast = document.createElement('div');
    toast.className = 'reminder-toast';
    toast.innerHTML = '<i class="bi ' + (iconClass || 'bi-bell') + '"></i><span></span>';
    toast.querySelector('span').textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, 6000);
}
window.showReminderToast = showReminderToast;

function setWakeIndicator(state) {
    const dot = document.getElementById('wakeIndicator');
    if (!dot) return;
    dot.className = '';
    dot.classList.add('wake-' + state);
    const titles = {
        idle: 'Say "Hey Krishteen" anytime',
        listening: 'Listening…',
        awake: 'Woke up!',
        off: '"Hey Krishteen" is off'
    };
    dot.title = titles[state] || '';
}
window.setWakeIndicator = setWakeIndicator;

/* ---------- Eel Exposed Handlers (Python calls these) ---------- */
eel.expose(DisplayMessage);
function DisplayMessage(message) {
    const box = document.getElementById('chatbox');
    if (box) box.placeholder = message;
}

eel.expose(ShowHood);
function ShowHood() {
    const box = document.getElementById('chatbox');
    if (box) { box.disabled = false; box.placeholder = 'type here…'; }
}

eel.expose(LogUserMessage);
function LogUserMessage(message) { addChatMessage('user', message); }

eel.expose(LogAssistantMessage);
function LogAssistantMessage(message) { addChatMessage('assistant', message); }

eel.expose(ReminderFired);
function ReminderFired(message, kind) {
    const map = { alarm: 'bi-alarm', reminder: 'bi-bell', appointment: 'bi-calendar-event' };
    addChatMessage('assistant', message);
    showReminderToast(message, map[kind] || 'bi-bell');
}

eel.expose(WakeWordState);
function WakeWordState(state) { setWakeIndicator(state); }

/* Call screen handlers */
eel.expose(CallStatus);
function CallStatus(state) { setCallState(state); }

eel.expose(CallUserMessage);
function CallUserMessage(text) { addCallBubble('user', text); }

eel.expose(CallAssistantMessage);
function CallAssistantMessage(text) { addCallBubble('assistant', text); }

/* ---------- Settings Modal ---------- */
const settingsModalEl = document.getElementById('settingsModal');
if (settingsModalEl) {
    settingsModalEl.addEventListener('show.bs.modal', () => {
        eel.getResponseStyle()(function (data) {
            if (!data || !data.options) return;
            let html = '';
            data.options.forEach(opt => {
                const checked = (opt.key === data.current) ? 'checked' : '';
                html += '<div class="form-check mb-2">' +
                    '<input class="form-check-input" type="radio" name="styleChoice" id="style_' + opt.key + '" value="' + opt.key + '" ' + checked + '>' +
                    '<label class="form-check-label" for="style_' + opt.key + '">' + opt.label + '</label>' +
                    '</div>';
            });
            document.getElementById('styleOptions').innerHTML = html;
        });
        eel.getWakeWordEnabled()(function (enabled) {
            const toggle = document.getElementById('wakeWordToggle');
            if (toggle) toggle.checked = !!enabled;
        });
    });
}

const saveStyleBtn = document.getElementById('saveStyleBtn');
if (saveStyleBtn) {
    saveStyleBtn.addEventListener('click', () => {
        const selected = document.querySelector("input[name='styleChoice']:checked");
        if (selected) eel.setResponseStyle(selected.value)();
    });
}

const wakeWordToggle = document.getElementById('wakeWordToggle');
if (wakeWordToggle) {
    wakeWordToggle.addEventListener('change', function () {
        const enabled = this.checked;
        eel.setWakeWordEnabled(enabled)();
        if (enabled) startBrowserWakeWord();
        else stopBrowserWakeWord();
    });
}

/* ---------- Reminders Modal ---------- */
const KIND_ICON = { alarm: 'bi-alarm', reminder: 'bi-bell', appointment: 'bi-calendar-event' };

function loadReminders() {
    eel.getUpcomingReminders()(function (items) {
        const list = document.getElementById('remindersList');
        if (!items || items.length === 0) {
            if (list) list.innerHTML = '<p class="text-muted-custom mb-0">Nothing scheduled yet. Try saying "remind me to call mom at 6pm".</p>';
            return;
        }
        let html = '';
        items.forEach(it => {
            const icon = KIND_ICON[it.kind] || 'bi-bell';
            const when = new Date(it.due_at).toLocaleString();
            html += '<div class="reminder-item">' +
                '<div><i class="bi ' + icon + ' me-2" style="color:var(--accent2);"></i>' +
                '<strong>' + it.title + '</strong>' +
                '<div style="font-size:.78rem; color:var(--text-muted); margin-left:24px;">' + when + '</div></div>' +
                '<button class="btn btn-sm btn-outline-danger cancel-reminder-btn" data-id="' + it.id + '"><i class="bi bi-x-lg"></i></button>' +
                '</div>';
        });
        if (list) list.innerHTML = html;
    });
}

const remindersModalEl = document.getElementById('remindersModal');
if (remindersModalEl) {
    remindersModalEl.addEventListener('show.bs.modal', loadReminders);
    remindersModalEl.addEventListener('click', function (e) {
        const btn = e.target.closest('.cancel-reminder-btn');
        if (!btn) return;
        eel.cancelReminderById(btn.dataset.id)(loadReminders);
    });
}

/* ---------- File Upload ---------- */
const attachBtn = document.getElementById('AttachBtn');
const fileInput = document.getElementById('fileInput');
if (attachBtn && fileInput) {
    attachBtn.addEventListener('click', () => { fileInput.value = ''; fileInput.click(); });
    fileInput.addEventListener('change', function () {
        const file = this.files[0];
        if (!file) return;
        const question = document.getElementById('chatbox').value.trim();
        document.getElementById('chatbox').value = '';

        const ext = file.name.split('.').pop().toLowerCase();
        let filetype;
        if (ext === 'pdf') filetype = 'pdf';
        else if (['png','jpg','jpeg','gif','webp'].includes(ext)) filetype = 'image';
        else if (['mp3','wav','m4a','ogg','aac','flac'].includes(ext)) filetype = 'audio';
        else if (['mp4','mov','avi','mkv'].includes(ext)) filetype = 'video';
        else { alert('Unsupported file type: .' + ext); return; }

        const reader = new FileReader();
        reader.onload = evt => { eel.handleFileUpload(file.name, filetype, evt.target.result, question)(); };
        reader.onerror = () => alert("Couldn't read that file.");
        reader.readAsDataURL(file);
    });
}

/* ---------- Text Chat ---------- */
const chatbox = document.getElementById('chatbox');
if (chatbox) {
    chatbox.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); sendTypedMessage(); }
    });
}

function sendTypedMessage() {
    const box = document.getElementById('chatbox');
    const text = box.value.trim();
    if (!text) return;
    box.value = '';
    box.disabled = true;
    eel.allCommands(text)();
}

/* ---------- Mic Button (Browser Recording -> Python) ---------- */
let micRecorder = null, micChunks = [], micRecording = false;
const micBtn = document.getElementById('MicBtn');

async function startMicRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        micChunks = [];
        micRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        micRecorder.ondataavailable = e => { if (e.data.size > 0) micChunks.push(e.data); };
        micRecorder.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            handleMicRecordingStopped();
        };
        micRecorder.start();
        micRecording = true;
        micBtn.classList.add('active-btn');
        chatbox.placeholder = 'Listening… click again to stop';
    } catch (err) {
        alert("Microphone access denied or unavailable.");
    }
}

function stopMicRecording() {
    if (micRecorder && micRecording) {
        micRecorder.stop();
        micRecording = false;
        micBtn.classList.remove('active-btn');
    }
}

function handleMicRecordingStopped() {
    const blob = new Blob(micChunks, { type: 'audio/webm' });
    chatbox.disabled = true;
    chatbox.placeholder = 'Processing…';

    const reader = new FileReader();
    reader.onload = async evt => {
        try {
            const result = await eel.handleVoiceMessage(evt.target.result, "webm")();
            if (result.query) addChatMessage('user', result.query);
            addChatMessage('assistant', result.response);
            if (result.audio_base64) {
                const audio = new Audio('data:audio/wav;base64,' + result.audio_base64);
                audio.play().catch(e => console.warn('Autoplay blocked:', e));
            }
        } catch (err) {
            addChatMessage('assistant', 'Sorry, something went wrong.');
        } finally {
            chatbox.disabled = false;
            chatbox.placeholder = 'type here…';
        }
    };
    reader.onerror = () => {
        alert("Couldn't process recording.");
        chatbox.disabled = false;
        chatbox.placeholder = 'type here…';
    };
    reader.readAsDataURL(blob);
}

if (micBtn) {
    micBtn.addEventListener('click', () => {
        eel.playClickSound();
        if (!micRecording) startMicRecording();
        else stopMicRecording();
    });
}

/* ================================================================
   BROWSER WAKE WORD  —  "Hey Krishteen" on ANY device
   ================================================================ */
const WAKE_VARIANTS = ['krishteen','christine','kristen','kristina','christina','krishtin','krishtine','christeen','krishten','kristeen'];
let wakeRec = null, wakeEnabled = true, wakeProcessing = false;

function initBrowserWakeWord() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { console.warn('[WakeWord] SpeechRecognition not supported'); return; }

    wakeRec = new SR();
    wakeRec.continuous = true;
    wakeRec.interimResults = true;
    wakeRec.lang = 'en-US';

    wakeRec.onresult = (e) => {
        const transcript = Array.from(e.results).map(r => r[0].transcript).join('').toLowerCase();
        if (WAKE_VARIANTS.some(v => transcript.includes(v)) && !wakeProcessing && !callActive && !micRecording) {
            wakeProcessing = true;
            wakeRec.stop();

            const fullText = Array.from(e.results).map(r => r[0].transcript).join('');
            let command = extractAfterWake(fullText);

            if (command.length > 2) {
                processBrowserCommand(command, restartWakeWord);
            } else {
                browserTTS("Yes?", () => listenOnce(restartWakeWord));
            }
        }
    };

    wakeRec.onerror = (e) => { if (e.error !== 'no-speech' && e.error !== 'aborted') console.warn('[WakeWord]', e.error); };
    wakeRec.onend = () => { if (wakeEnabled && !wakeProcessing && !callActive) setTimeout(() => wakeRec.start(), 200); };

    if (wakeEnabled) wakeRec.start();
    console.log('[WakeWord] Browser wake word active.');
}

function stopBrowserWakeWord() {
    wakeEnabled = false;
    if (wakeRec) wakeRec.abort();
    setWakeIndicator('off');
}

function startBrowserWakeWord() {
    wakeEnabled = true;
    if (wakeRec) wakeRec.start();
    else initBrowserWakeWord();
}

function restartWakeWord() {
    wakeProcessing = false;
    if (wakeEnabled && !callActive) {
        setTimeout(() => { if (wakeRec) wakeRec.start(); }, 300);
    }
}

function extractAfterWake(text) {
    const low = text.toLowerCase();
    for (const v of WAKE_VARIANTS) {
        const i = low.indexOf(v);
        if (i !== -1) return text.substring(i + v.length).trim().replace(/^[,.\s]+/, '');
    }
    return '';
}

function listenOnce(onDone) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = 'en-US'; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onresult = (e) => onDone(e.results[0][0].transcript);
    rec.onerror = () => onDone('');
    rec.start();
}

function processBrowserCommand(text, onDone) {
    eel.LogUserMessage(text);
    DisplayMessage('Thinking…');
    eel.getTextResponse(text)().then(resp => {
        addChatMessage('assistant', resp);
        ShowHood();
        browserTTS(resp, onDone);
    }).catch(err => {
        addChatMessage('assistant', 'Sorry, something went wrong.');
        ShowHood();
        if (onDone) onDone();
    });
}

function browserTTS(text, onDone) {
    if (!window.speechSynthesis) { if (onDone) onDone(); return; }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1; u.pitch = 1; u.lang = 'en-US';
    const voices = window.speechSynthesis.getVoices();
    const v = voices.find(x => x.name.includes('Google US English'))
           || voices.find(x => x.name.includes('Samantha'))
           || voices.find(x => x.lang === 'en-US');
    if (v) u.voice = v;
    u.onend = () => { if (onDone) onDone(); };
    u.onerror = () => { if (onDone) onDone(); };
    window.speechSynthesis.speak(u);
}

// Preload voices
if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

/* ================================================================
   BROWSER LIVE CALL  —  works on ANY device
   ================================================================ */
let callActive = false, callConnecting = false, callSessionId = '';
let timerInterval = null, secondsElapsed = 0;
let callRec = null, silenceStrikes = 0;

const callOrb = document.getElementById('callOrb');
const orbRings = document.getElementById('orbRings');
const callStatus = document.getElementById('callStatus');
const callBtn = document.getElementById('callBtn');
const callBtnLabel = document.getElementById('callBtnLabel');
const callTimer = document.getElementById('callTimer');
const callTranscript = document.getElementById('callTranscript');

function setCallState(state) {
    const labels = {
        connecting: 'Connecting…', connected: 'Connected', listening: 'Listening…',
        thinking: 'Thinking…', speaking: 'Speaking…', ended: 'Call ended', idle: 'Tap to start the call'
    };
    if (callStatus) callStatus.textContent = labels[state] || state;
    if (callOrb) callOrb.className = 'orb ' + (state === 'idle' ? '' : state);
    if (orbRings) orbRings.className = 'rings ' + (state === 'listening' || state === 'speaking' ? state : '');
    if (orbRings && (!orbRings.children.length || orbRings.dataset.state !== state)) {
        orbRings.innerHTML = '<div class="ring ring-3"></div><div class="ring ring-2"></div><div class="ring ring-1"></div>';
        orbRings.dataset.state = state;
    }
}

function startTimer() {
    secondsElapsed = 0;
    if (callTimer) callTimer.textContent = '00:00';
    timerInterval = setInterval(() => {
        secondsElapsed++;
        const m = String(Math.floor(secondsElapsed / 60)).padStart(2, '0');
        const s = String(secondsElapsed % 60).padStart(2, '0');
        if (callTimer) callTimer.textContent = m + ':' + s;
    }, 1000);
}

function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
}

function addCallBubble(role, text) {
    const empty = document.getElementById('transcriptEmpty');
    if (empty) empty.remove();
    const b = document.createElement('div');
    b.className = 'c-bubble ' + role;
    b.textContent = text;
    if (callTranscript) {
        callTranscript.appendChild(b);
        callTranscript.scrollTop = callTranscript.scrollHeight;
    }
}

function startBrowserCall() {
    if (callConnecting || callActive) return;
    callConnecting = true;
    if (callBtn) { callBtn.classList.add('connecting'); callBtnLabel.textContent = 'Connecting…'; }
    if (callTranscript) callTranscript.innerHTML = '<p class="transcript-empty" id="transcriptEmpty">Your conversation will appear here once the call connects.</p>';
    setCallState('connecting');

    setTimeout(() => {
        callConnecting = false; callActive = true;
        if (callBtn) { callBtn.classList.remove('connecting'); callBtn.classList.add('active'); callBtnLabel.textContent = 'End Call'; }
        startTimer(); setCallState('connected');
        callSessionId = 'browser-call-' + Math.random().toString(36).substr(2, 8);
        silenceStrikes = 0;

        const greeting = "Hi, this is Krishteen. I'm listening, go ahead.";
        addCallBubble('assistant', greeting);
        browserTTS(greeting, () => callListeningLoop());
    }, 600);
}

function callListeningLoop() {
    if (!callActive) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { addCallBubble('assistant', "Voice recognition not supported in this browser."); return; }

    callRec = new SR();
    callRec.continuous = false;
    callRec.interimResults = false;
    callRec.maxAlternatives = 1;
    callRec.lang = 'en-US';

    let heardSomething = false;

    callRec.onresult = async (e) => {
        heardSomething = true;
        const query = e.results[0][0].transcript;
        addCallBubble('user', query);
        setCallState('thinking');
        silenceStrikes = 0;

        const endPhrases = ['end call','hang up','goodbye','bye krishteen','stop call','that\'s all','see you'];
        if (endPhrases.some(p => query.toLowerCase().includes(p))) {
            const bye = "Okay, ending the call. Goodbye!";
            addCallBubble('assistant', bye);
            browserTTS(bye, endBrowserCall);
            return;
        }

        try {
            const resp = await eel.getTextResponse(query, callSessionId)();
            addCallBubble('assistant', resp);
            setCallState('speaking');
            browserTTS(resp, () => { if (callActive) callListeningLoop(); });
        } catch (err) {
            addCallBubble('assistant', "Sorry, something went wrong.");
            if (callActive) callListeningLoop();
        }
    };

    callRec.onerror = (e) => {
        if (e.error === 'no-speech') {
            silenceStrikes++;
            if (silenceStrikes >= 4) {
                const msg = "I haven't heard anything in a while, so I'll end the call here. Goodbye!";
                addCallBubble('assistant', msg);
                browserTTS(msg, endBrowserCall);
                return;
            }
        }
        if (callActive) setTimeout(() => callListeningLoop(), 300);
    };

    callRec.onend = () => {
        if (!heardSomething && callActive) setTimeout(() => callListeningLoop(), 300);
    };

    setCallState('listening');
    callRec.start();
}

function endBrowserCall() {
    callActive = false;
    if (callRec) { callRec.abort(); callRec = null; }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (callBtn) { callBtn.classList.remove('active', 'connecting'); callBtnLabel.textContent = 'Start Call'; }
    stopTimer(); setCallState('ended');
    if (callSessionId) eel.clearBrowserSession(callSessionId)();
    callSessionId = '';
    restartWakeWord();
}

/* ---------- Call Screen Navigation ---------- */
const viewMain = document.getElementById('viewMain');
const viewCall = document.getElementById('viewCall');
const callBtnLink = document.getElementById('CallBtnLink');
const backToMain = document.getElementById('backToMain');

if (callBtnLink) {
    callBtnLink.addEventListener('click', () => {
        if (viewCall) viewCall.classList.add('active');
        if (viewMain) viewMain.classList.add('hidden');
    });
}

if (backToMain) {
    backToMain.addEventListener('click', () => {
        if (viewCall) viewCall.classList.remove('active');
        if (viewMain) viewMain.classList.remove('hidden');
        if (callActive) endBrowserCall();
    });
}

if (callBtn) {
    callBtn.addEventListener('click', async () => {
        if (callConnecting) return;
        if (!callActive) {
            startBrowserCall();
        } else {
            endBrowserCall();
        }
    });
}

setCallState('idle');

/* ---------- Init ---------- */
initBrowserWakeWord();