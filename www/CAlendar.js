// calendar.js — renders a month-view calendar of appointments/reminders/alarms
// pulled from krishteen.db via the eel-exposed getAllReminders() function
// (engine/scheduler.py). Falls back to getUpcomingReminders() if that
// newer endpoint isn't available yet.

let currentMonth = new Date().getMonth();
let currentYear = new Date().getFullYear();
let allEvents = [];
let selectedDateKey = null;

const monthNames = ["January","February","March","April","May","June",
                     "July","August","September","October","November","December"];

function dateKey(d) {
  // Local YYYY-MM-DD, matching how due_at's date portion should be compared
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

async function loadEvents() {
  try {
    if (window.eel.getAllReminders) {
      allEvents = await eel.getAllReminders()();
    } else {
      allEvents = await eel.getUpcomingReminders()();
    }
  } catch (e) {
    console.error("Failed to load reminders from Krishteen backend:", e);
    allEvents = [];
  }
  renderCalendar();
}

function eventsForDate(key) {
  return allEvents.filter(ev => (ev.due_at || '').slice(0, 10) === key);
}

function renderCalendar() {
  document.getElementById('monthLabel').textContent = `${monthNames[currentMonth]} ${currentYear}`;

  const grid = document.getElementById('calGrid');
  // remove old day cells (keep the 7 weekday labels)
  document.querySelectorAll('.cal-day').forEach(el => el.remove());

  const firstOfMonth = new Date(currentYear, currentMonth, 1);
  const startWeekday = firstOfMonth.getDay();
  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const todayKey = dateKey(new Date());

  for (let i = 0; i < startWeekday; i++) {
    const empty = document.createElement('div');
    empty.className = 'cal-day empty';
    grid.appendChild(empty);
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const cellDate = new Date(currentYear, currentMonth, day);
    const key = dateKey(cellDate);
    const dayEvents = eventsForDate(key);

    const cell = document.createElement('div');
    cell.className = 'cal-day';
    if (key === todayKey) cell.classList.add('today');
    if (key === selectedDateKey) cell.classList.add('selected');
    cell.dataset.key = key;

    const num = document.createElement('div');
    num.className = 'cal-day-number';
    num.textContent = day;
    cell.appendChild(num);

    if (dayEvents.length > 0) {
      const dots = document.createElement('div');
      dots.className = 'cal-dots';
      dayEvents.slice(0, 6).forEach(ev => {
        const dot = document.createElement('span');
        dot.className = `cal-dot ${ev.kind || 'reminder'}` + (ev.fired ? ' fired' : '');
        dots.appendChild(dot);
      });
      cell.appendChild(dots);
    }

    cell.addEventListener('click', () => selectDate(key));
    grid.appendChild(cell);
  }

  if (selectedDateKey) {
    renderDayPanel(selectedDateKey);
  }
}

function selectDate(key) {
  selectedDateKey = key;
  document.querySelectorAll('.cal-day').forEach(el => el.classList.remove('selected'));
  const cell = document.querySelector(`.cal-day[data-key="${key}"]`);
  if (cell) cell.classList.add('selected');
  renderDayPanel(key);
}

function renderDayPanel(key) {
  const list = document.getElementById('dayPanelList');
  const title = document.getElementById('dayPanelTitle');
  const events = eventsForDate(key);

  title.textContent = events.length
    ? `${events.length} item${events.length > 1 ? 's' : ''} on ${key}`
    : `Nothing scheduled on ${key}`;

  list.innerHTML = '';
  events.forEach(ev => {
    const li = document.createElement('li');
    if (ev.fired) li.classList.add('fired');

    const label = document.createElement('span');
    const time = (ev.due_at || '').slice(11, 16);
    label.textContent = `${time ? time + ' — ' : ''}${ev.title}`;

    const tag = document.createElement('span');
    tag.className = 'cal-kind-tag';
    tag.textContent = ev.kind || 'reminder';

    li.appendChild(label);
    li.appendChild(tag);
    list.appendChild(li);
  });
}

document.getElementById('prevMonth').addEventListener('click', () => {
  currentMonth--;
  if (currentMonth < 0) { currentMonth = 11; currentYear--; }
  renderCalendar();
});

document.getElementById('nextMonth').addEventListener('click', () => {
  currentMonth++;
  if (currentMonth > 11) { currentMonth = 0; currentYear++; }
  renderCalendar();
});

loadEvents();
// Refresh periodically so newly booked appointments (e.g. from a live phone
// call) show up without needing to manually reload the page.
setInterval(loadEvents, 15000);