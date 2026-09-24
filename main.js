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

    
    var settingsModalEl = document.getElementById('settingsModal');
    settingsModalEl.addEventListener('show.bs.modal', function () {
        eel.getResponseStyle()(function (data) {
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
    });

    $("#saveStyleBtn").click(function () {
        var selected = $("input[name='styleChoice']:checked").val();
        if (!selected) return;
        eel.setResponseStyle(selected)(function () {
            var modal = bootstrap.Modal.getOrCreateInstance(settingsModalEl);
            modal.hide();
        });
    });
});