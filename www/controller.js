$(document).ready(function () {
    eel.expose(DisplayMessage)
    function DisplayMessage(message) {
        $(".siri-message").text(message);
        $('.siri-message').textillate('start');
    }

    eel.expose(ShowHood)
    function ShowHood() {
        $("#Oval").attr("hidden", false);
        $("#SiriWave").attr("hidden", true);
    }

    eel.expose(LogUserMessage)
    function LogUserMessage(message) {
        if (typeof addChatMessage === "function") {
            addChatMessage("user", message);
        }
    }

    eel.expose(LogAssistantMessage)
    function LogAssistantMessage(message) {
        if (typeof addChatMessage === "function") {
            addChatMessage("assistant", message);
        }
    }

    // Called by engine/scheduler.py when an alarm/reminder/appointment fires,
    // regardless of what else the user is doing in the UI at that moment.
    eel.expose(ReminderFired)
    function ReminderFired(message, kind) {
        if (typeof addChatMessage === "function") {
            addChatMessage("assistant", message);
        }
        if (typeof showReminderToast === "function") {
            showReminderToast(message, kind);
        }
    }

    // Called by engine/wakeword.py — state is one of: "idle", "listening",
    // "awake", "off". Drives the little indicator dot next to the mic button.
    eel.expose(WakeWordState)
    function WakeWordState(state) {
        if (typeof setWakeIndicator === "function") {
            setWakeIndicator(state);
        }
    }
});
