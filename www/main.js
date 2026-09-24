$(document).ready(function() {
    $('.text').textillate({
        loop: true,
        sync: true,
        in: {
            effect: "bounceIn",
        },
        out: {
            effect: "bounceOut",
        },

    });


    var siriWave = new SiriWave({
        container: document.getElementById("siri-container"),
        width: 800,
        height: 200,
        style: "ios9",
        amplitude: "1",
        speed: "0.30",
        autostart: true
      });

      $('.siri-message').textillate({
        loop: true,
        sync: true,
        in: {
            effect: "fadeInUp",
            sync: true,
        },
        out: {
            effect: "fadeOutUp",
            sync: true,
        },

    });


    $("#MicBtn").click(function() {
        $("#Oval").attr("hidden", true);
        $("#SiriWave").attr("hidden", false);
        eel.playClickSound();
        eel.allCommands()();
    });

    
    $("#chatbox").on("keypress", function(e) {
        if (e.which === 13) {
            e.preventDefault();
            sendTypedMessage();
        }
    });

    function sendTypedMessage() {
        var text = $("#chatbox").val().trim();
        if (text === "") return;

        $("#chatbox").val("");
        $("#Oval").attr("hidden", true);
        $("#SiriWave").attr("hidden", false);
        eel.allCommands(text)();
    }

    
    $("#AttachBtn").click(function () {
        $("#fileInput").val("");
        $("#fileInput").click();
    });

    $("#fileInput").on("change", function (e) {
        var file = e.target.files[0];
        if (!file) return;

        
        var question = $("#chatbox").val().trim();
        $("#chatbox").val("");

        var ext = file.name.split('.').pop().toLowerCase();
        var filetype;
        if (ext === "pdf") {
            filetype = "pdf";
        } else if (["png", "jpg", "jpeg", "gif", "webp"].indexOf(ext) !== -1) {
            filetype = "image";
        } else if (["mp3", "wav", "m4a", "ogg", "aac", "flac"].indexOf(ext) !== -1) {
            filetype = "audio";
        } else if (["mp4", "mov", "avi", "mkv"].indexOf(ext) !== -1) {
            filetype = "video";
        } else {
            alert("Unsupported file type: ." + ext);
            return;
        }

        $("#Oval").attr("hidden", true);
        $("#SiriWave").attr("hidden", false);

        var reader = new FileReader();
        reader.onload = function (evt) {
            var base64Data = evt.target.result; 
            eel.handleFileUpload(file.name, filetype, base64Data, question)();
        };
        reader.onerror = function () {
            alert("Couldn't read that file.");
        };
        reader.readAsDataURL(file);
    });


    window.addChatMessage = function (role, text) {
        var label = (role === "user") ? "You" : "Krishteen";
        var alignClass = (role === "user") ? "text-end" : "text-start";
        var bubbleColor = (role === "user") ? "#2a5db0" : "#33445c";
        var safeText = $("<div>").text(text).html();

        var html = '<div class="mb-2 ' + alignClass + '">' +
            '<div style="display:inline-block; background:' + bubbleColor + '; color:#fff; padding:8px 12px; border-radius:10px; max-width:90%; text-align:left;">' +
            '<strong>' + label + ':</strong> ' + safeText +
            '</div></div>';

        $("#chatLog").append(html);
        var chatLogEl = document.getElementById("chatLog");
        chatLogEl.scrollTop = chatLogEl.scrollHeight;
    };

    // ---- Settings modal: answer style ----
    var settingsModalEl = document.getElementById('settingsModal');
    settingsModalEl.addEventListener('show.bs.modal', function () {
        try {
            eel.getResponseStyle()(function (data) {
                if (!data || !data.options) {
                    alert("PROBLEM: getResponseStyle returned unexpected data: " + JSON.stringify(data));
                    return;
                }
                var html = "";
                data.options.forEach(function (opt) {
                    var checked = (opt.key === data.current) ? "checked" : "";
                    html += '<div class="form-check mb-2">' +
                        '<input class="form-check-input" type="radio" name="styleChoice" id="style_' + opt.key + '" value="' + opt.key + '" ' + checked + '>' +
                        '<label class="form-check-label" for="style_' + opt.key + '">' + opt.label + '</label>' +
                        '</div>';
                });
                $("#styleOptions").html(html);
            });
        } catch (err) {
            alert("ERROR calling eel.getResponseStyle: " + err);
        }
    });

    $("#saveStyleBtn").click(function () {
        var selected = $("input[name='styleChoice']:checked").val();
        if (!selected) return;
        eel.setResponseStyle(selected)(function () {
            var modal = bootstrap.Modal.getOrCreateInstance(settingsModalEl);
            modal.hide();
        });
    });

    // ---- Reminders: toast popup + panel ----

    var KIND_ICON = { alarm: "bi-alarm", reminder: "bi-bell", appointment: "bi-calendar-event" };

    window.showReminderToast = function (message, kind) {
        var icon = KIND_ICON[kind] || "bi-bell";
        var toast = $(
            '<div class="reminder-toast">' +
                '<i class="bi ' + icon + '"></i>' +
                '<span></span>' +
            '</div>'
        );
        toast.find("span").text(message);
        $("body").append(toast);
        setTimeout(function () {
            toast.addClass("show");
        }, 10);
        setTimeout(function () {
            toast.removeClass("show");
            setTimeout(function () { toast.remove(); }, 400);
        }, 6000);
    };

    function loadReminders() {
        eel.getUpcomingReminders()(function (items) {
            var $list = $("#remindersList");
            if (!items || items.length === 0) {
                $list.html('<p class="text-muted mb-0">Nothing scheduled. Try saying "remind me to call mom at 6pm".</p>');
                return;
            }
            var html = "";
            items.forEach(function (it) {
                var icon = KIND_ICON[it.kind] || "bi-bell";
                var when = new Date(it.due_at).toLocaleString();
                html += '<div class="reminder-item d-flex justify-content-between align-items-center mb-2">' +
                    '<div><i class="bi ' + icon + ' me-2"></i><strong>' + $("<div>").text(it.title).html() + '</strong>' +
                    '<div class="text-muted small">' + when + '</div></div>' +
                    '<button class="btn btn-sm btn-outline-danger cancel-reminder-btn" data-id="' + it.id + '">' +
                    '<i class="bi bi-x-lg"></i></button>' +
                    '</div>';
            });
            $list.html(html);
        });
    }

    $(document).on("click", ".cancel-reminder-btn", function () {
        var rid = $(this).data("id");
        eel.cancelReminderById(rid)(function () {
            loadReminders();
        });
    });

    var remindersModalEl = document.getElementById('remindersModal');
    if (remindersModalEl) {
        remindersModalEl.addEventListener('show.bs.modal', loadReminders);
    }

    // ---- "Hey Krishteen" wake word: indicator dot + Settings toggle ----

    window.setWakeIndicator = function (state) {
        var $dot = $("#wakeIndicator");
        if ($dot.length === 0) return;
        $dot.removeClass("wake-idle wake-listening wake-awake wake-off");
        $dot.addClass("wake-" + state);
        var titles = {
            idle: "Say \"Hey Krishteen\" anytime",
            listening: "Listening...",
            awake: "Woke up!",
            off: "\"Hey Krishteen\" is turned off"
        };
        $dot.attr("title", titles[state] || "");
    };

    // Load current on/off state whenever Settings is opened
    settingsModalEl.addEventListener('show.bs.modal', function () {
        eel.getWakeWordEnabled()(function (enabled) {
            $("#wakeWordToggle").prop("checked", !!enabled);
        });
    });

    $("#wakeWordToggle").on("change", function () {
        var enabled = $(this).is(":checked");
        eel.setWakeWordEnabled(enabled)(function () {});
    });
});
