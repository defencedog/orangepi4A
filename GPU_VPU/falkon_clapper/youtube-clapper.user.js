// ==UserScript==
// @name         YouTube -> Clapper (VPU)
// @namespace    ukhan.falkon.clapper
// @version      1.0.0
// @description  Send YouTube watch/Shorts pages to Clapper for cedar VPU playback
// @match        https://www.youtube.com/*
// @match        https://m.youtube.com/*
// @run-at       document-end
// @noframes
// ==/UserScript==

(function () {
    'use strict';

    // Falkon's GreaseMonkey plugin runs this in an isolated world, but only in
    // the top frame because of @noframes.  Guard anyway.
    if (window.top !== window.self) {
        return;
    }

    var AUTO_KEY = 'falkon-clapper-auto';
    var AUTO_DELAY_MS = 1500;
    var ID_RE = /^[A-Za-z0-9_-]{11}$/;
    var HOST_ID = 'falkon-clapper-host';
    var TOAST_ID = 'falkon-clapper-toast';

    var autoEnabled = readBool(AUTO_KEY, true);
    var currentId = null;
    var lastHref = location.href;
    var autoTimer = null;
    var autoDeadline = 0;
    var toastMode = null;          // 'countdown' | 'opening' | 'playing' | null
    var handled = Object.create(null); // ids handled/skipped in this page session
    var uiHost = null;

    // ---------------------------------------------------------------------
    // Settings
    // ---------------------------------------------------------------------

    function readBool(key, fallback) {
        var value;
        try {
            if (typeof GM_getValue === 'function') {
                value = GM_getValue(key, fallback);
            }
        } catch (e) {
            value = undefined;
        }
        if (value === undefined || value === null) {
            try {
                var raw = window.localStorage.getItem(key);
                if (raw !== null) {
                    value = JSON.parse(raw);
                }
            } catch (e2) {
                value = undefined;
            }
        }
        if (typeof value === 'boolean') {
            return value;
        }
        if (typeof value === 'string') {
            return value === 'true' || value === '1';
        }
        if (typeof value === 'number') {
            return value !== 0;
        }
        return fallback;
    }

    function writeBool(key, value) {
        try {
            if (typeof GM_setValue === 'function') {
                GM_setValue(key, value);
                return;
            }
        } catch (e) {
            // fall through
        }
        try {
            window.localStorage.setItem(key, JSON.stringify(value));
        } catch (e2) {
            // ignore
        }
    }

    // ---------------------------------------------------------------------
    // URL handling
    // ---------------------------------------------------------------------

    function videoIdFromUrl(href) {
        var u;
        try {
            u = new URL(href, location.href);
        } catch (e) {
            return null;
        }
        if (u.hostname !== 'www.youtube.com' &&
            u.hostname !== 'm.youtube.com' &&
            u.hostname !== 'youtube.com') {
            return null;
        }
        if (u.pathname === '/watch') {
            var v = u.searchParams.get('v');
            return (v && ID_RE.test(v)) ? v : null;
        }
        var m = u.pathname.match(/^\/shorts\/([A-Za-z0-9_-]{11})(?:$|\/)/);
        return m ? m[1] : null;
    }

    function pauseVideos() {
        var videos = document.querySelectorAll('video');
        for (var i = 0; i < videos.length; i++) {
            try {
                videos[i].pause();
            } catch (e) {
                // ignore
            }
        }
    }

    // ---------------------------------------------------------------------
    // UI
    // ---------------------------------------------------------------------

    function makeButton(label, onClick) {
        var el = document.createElement('span');
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        el.textContent = label;
        el.style.cssText =
            'display:inline-block!important;background:#2f2f2f!important;' +
            'color:#fff!important;border:1px solid #666!important;' +
            'border-radius:6px!important;padding:4px 9px!important;' +
            'font:600 12px system-ui,-apple-system,Segoe UI,Roboto,sans-serif!important;' +
            'cursor:pointer!important;user-select:none!important;white-space:nowrap!important;';
        el.addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            onClick();
        });
        el.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                ev.stopPropagation();
                onClick();
            }
        });
        return el;
    }

    function buildUi() {
        if (document.getElementById(HOST_ID)) {
            return;
        }

        var host = document.createElement('div');
        host.id = HOST_ID;
        host.style.cssText =
            'position:fixed!important;right:18px!important;bottom:18px!important;' +
            'z-index:2147483647!important;display:flex!important;' +
            'flex-direction:column!important;align-items:flex-end!important;' +
            'gap:6px!important;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif!important;';

        var play = makeButton('\u25b6 Clapper (VPU)', function () {
            if (currentId) {
                handoff(currentId, false);
            }
        });
        play.id = 'falkon-clapper-play';
        play.style.cssText +=
            'background:#1f6feb!important;padding:9px 13px!important;' +
            'font-size:13px!important;box-shadow:0 4px 14px rgba(0,0,0,.45)!important;';

        var auto = makeButton('', toggleAuto);
        auto.id = 'falkon-clapper-auto';
        auto.style.cssText +=
            'background:#222!important;color:#ddd!important;' +
            'font-size:11px!important;font-weight:500!important;' +
            'padding:4px 8px!important;';

        host.appendChild(play);
        host.appendChild(auto);
        document.documentElement.appendChild(host);
        uiHost = host;
        updateUi();
    }

    function removeUi() {
        if (uiHost && uiHost.parentNode) {
            uiHost.parentNode.removeChild(uiHost);
        }
        uiHost = null;
    }

    function updateUi() {
        if (!uiHost) {
            return;
        }
        var auto = document.getElementById('falkon-clapper-auto');
        if (auto) {
            auto.textContent = autoEnabled ? 'Auto: ON (Alt+P)' : 'Auto: OFF (Alt+P)';
        }
        uiHost.style.display = document.fullscreenElement ? 'none' : 'flex';
    }

    function getToast() {
        var toast = document.getElementById(TOAST_ID);
        if (toast) {
            return toast;
        }
        toast = document.createElement('div');
        toast.id = TOAST_ID;
        toast.style.cssText =
            'position:fixed!important;top:16px!important;left:50%!important;' +
            'transform:translateX(-50%)!important;z-index:2147483647!important;' +
            'background:#181818!important;color:#fff!important;' +
            'border:1px solid #555!important;border-radius:10px!important;' +
            'padding:10px 14px!important;display:none!important;' +
            'align-items:center!important;gap:10px!important;' +
            'max-width:min(92vw,720px)!important;' +
            'box-shadow:0 6px 24px rgba(0,0,0,.5)!important;' +
            'font:13px system-ui,-apple-system,Segoe UI,Roboto,sans-serif!important;' +
            'line-height:1.35!important;';
        document.documentElement.appendChild(toast);
        return toast;
    }

    function setToast(text, buttons, timeoutMs) {
        var toast = getToast();
        toast.textContent = '';

        var span = document.createElement('span');
        span.textContent = text;
        span.style.cssText =
            'white-space:normal!important;display:inline-block!important;' +
            'max-width:min(70vw,560px)!important;';
        toast.appendChild(span);

        (buttons || []).forEach(function (b) {
            toast.appendChild(makeButton(b.label, b.onClick));
        });

        toast.style.display = 'flex';
        if (toast._hideTimer) {
            clearTimeout(toast._hideTimer);
            toast._hideTimer = null;
        }
        if (timeoutMs) {
            toast._hideTimer = setTimeout(function () {
                hideToast();
            }, timeoutMs);
        }
    }

    function hideToast() {
        var toast = document.getElementById(TOAST_ID);
        if (toast) {
            toast.style.display = 'none';
        }
        toastMode = null;
    }

    function showCountdown(id) {
        toastMode = 'countdown';
        var toast = getToast();
        toast.textContent = '';

        var span = document.createElement('span');
        span.id = 'falkon-clapper-countdown-text';
        span.style.cssText =
            'white-space:normal!important;display:inline-block!important;' +
            'max-width:min(70vw,560px)!important;';
        toast.appendChild(span);
        toast.appendChild(makeButton('Cancel', function () {
            skipVideo(id);
        }));
        toast.style.display = 'flex';
        updateCountdown(Math.ceil(AUTO_DELAY_MS / 1000));
    }

    function updateCountdown(seconds) {
        var span = document.getElementById('falkon-clapper-countdown-text');
        if (span) {
            span.textContent = 'Opening in Clapper (VPU) in ' + seconds + 's\u2026';
        }
    }

    function showOpening() {
        toastMode = 'opening';
        setToast('Opening in Clapper (VPU)\u2026', [], 0);
    }

    function showPlaying(id) {
        toastMode = 'playing';
        setToast('Playing in Clapper (VPU)', [
            {
                label: 'Reopen',
                onClick: function () {
                    handoff(id, false);
                }
            },
            {
                label: 'Play in browser',
                onClick: function () {
                    hideToast();
                    handled[id] = true;
                    pauseVideos();
                    var videos = document.querySelectorAll('video');
                    for (var i = 0; i < videos.length; i++) {
                        try {
                            videos[i].play();
                        } catch (e) {
                            // ignore
                        }
                    }
                }
            }
        ], 12000);
    }

    // ---------------------------------------------------------------------
    // Handoff / auto scheduling
    // ---------------------------------------------------------------------

    function handoff(id, isAuto) {
        if (!id || !ID_RE.test(id)) {
            return;
        }

        clearAuto();
        handled[id] = true;
        pauseVideos();
        showOpening();

        // Let the toast paint before triggering the custom-scheme navigation.
        setTimeout(function () {
            try {
                window.location.href = 'clapper://play?v=' + encodeURIComponent(id);
            } catch (e) {
                setToast('Could not open Clapper: ' + e, [], 8000);
            }
        }, 50);

        // YouTube may start the player after our first pause; pause again.
        setTimeout(pauseVideos, 1000);
        setTimeout(function () {
            pauseVideos();
            showPlaying(id);
        }, 2000);
    }

    function skipVideo(id) {
        handled[id] = true;
        clearAuto();
        hideToast();
    }

    function scheduleAuto(id) {
        clearAuto();
        if (!autoEnabled || !id || handled[id]) {
            return;
        }
        if (document.visibilityState !== 'visible') {
            return;
        }

        autoDeadline = Date.now() + AUTO_DELAY_MS;
        showCountdown(id);
        autoTimer = setInterval(function () {
            var left = autoDeadline - Date.now();
            if (left <= 0) {
                clearAuto();
                handoff(id, true);
            } else {
                updateCountdown(Math.ceil(left / 1000));
            }
        }, 200);
    }

    function clearAuto() {
        if (autoTimer) {
            clearInterval(autoTimer);
            autoTimer = null;
        }
        if (toastMode === 'countdown') {
            hideToast();
        }
    }

    function toggleAuto() {
        autoEnabled = !autoEnabled;
        writeBool(AUTO_KEY, autoEnabled);
        updateUi();
        if (!autoEnabled) {
            clearAuto();
        } else if (currentId && !handled[currentId]) {
            scheduleAuto(currentId);
        }
    }

    // ---------------------------------------------------------------------
    // Navigation detection
    // ---------------------------------------------------------------------

    function checkNavigation() {
        if (location.href === lastHref) {
            if (currentId) {
                buildUi();
            }
            return;
        }

        lastHref = location.href;
        var id = videoIdFromUrl(location.href);
        if (id === currentId) {
            return;
        }

        currentId = id;
        clearAuto();
        hideToast();

        if (id) {
            buildUi();
            scheduleAuto(id);
        } else {
            removeUi();
        }
    }

    function onNavigate() {
        // YouTube updates location after yt-navigate-finish; give it a tick.
        setTimeout(checkNavigation, 50);
    }

    document.addEventListener('yt-navigate-finish', onNavigate, true);
    window.addEventListener('popstate', onNavigate, true);
    window.addEventListener('hashchange', onNavigate, true);
    document.addEventListener('fullscreenchange', updateUi, true);

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            if (currentId && autoEnabled && !handled[currentId] && !autoTimer) {
                scheduleAuto(currentId);
            }
        } else {
            // Do not fire a handoff while the user is in another tab.
            clearAuto();
        }
    }, true);

    document.addEventListener('keydown', function (ev) {
        if (ev.altKey && !ev.ctrlKey && !ev.metaKey && !ev.shiftKey &&
            (ev.key === 'p' || ev.key === 'P')) {
            if (!currentId) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            handoff(currentId, false);
        }
    }, true);

    setInterval(checkNavigation, 1000);

    currentId = videoIdFromUrl(location.href);
    if (currentId) {
        buildUi();
        scheduleAuto(currentId);
    }
})();
