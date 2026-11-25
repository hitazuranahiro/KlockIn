(() => {
    const dialog = document.querySelector("#web-punch-preview");
    const clock = document.querySelector("#attendance-activity-container");
    const breaks = document.querySelector("[data-break-panel]");
    if (!dialog || !clock || !breaks) return;

    const find = (name) => dialog.querySelector(`[data-${name}]`);
    const breakField = (name) => breaks.querySelector(`[data-break-${name}]`);
    const video = find("punch-video");
    const photo = find("punch-selfie");
    const cameraButton = find("punch-camera");
    const confirm = find("punch-confirm");
    const breakAction = breakField("action");
    const csrfToken = dialog.querySelector('[name="csrfmiddlewaretoken"]').value;
    const baseTitle = document.querySelector("#whiteLabelCompany")?.dataset.company
        || document.title.replace(/ \| \d+:\d{2}:\d{2}$/, "");
    let preview;
    let workTimer;
    let renderWorkTimer;
    let breakStatus;
    let breakReadVersion = 0;
    let changingBreak = false;

    function duration(value) {
        const seconds = Math.floor(Math.max(0, Number(value) || 0));
        return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
            .map((part) => String(part).padStart(2, "0"))
            .join(":");
    }

    function showMessage(element, message) {
        element.textContent = message;
        element.hidden = !message;
    }

    async function requestJSON(url, { method = "GET", body, signal } = {}) {
        const headers = { Accept: "application/json" };
        if (method === "POST") {
            headers["X-CSRFToken"] = csrfToken;
            if (!(body instanceof FormData)) {
                headers["Content-Type"] = "application/json";
                body = JSON.stringify(body);
            }
        }

        const response = await fetch(url, { method, body, signal, headers, credentials: "same-origin" });
        const result = await response.json().catch(() => null);
        if (!response.ok || !result) {
            const message = typeof result?.detail === "string" && result.detail;
            throw new Error(message || "The request could not be completed. Try again.");
        }
        return result;
    }

    function startWorkTimer() {
        clearInterval(workTimer);
        const timer = clock.querySelector("[data-work-timer]");
        if (!timer) {
            renderWorkTimer = null;
            document.title = baseTitle;
            return;
        }

        const initial = Number(timer.dataset.workTimer) || 0;
        const started = performance.now();
        const running = timer.hasAttribute("data-work-running");
        renderWorkTimer = () => {
            const elapsed = running ? (performance.now() - started) / 1000 : 0;
            const used = Number(breakStatus?.used_seconds) || 0;
            const ongoing = running ? liveBreakSeconds() : 0;
            timer.textContent = duration(initial + elapsed - used - ongoing);
            document.title = baseTitle + " | " + timer.textContent;
        };
        renderWorkTimer();
        if (running) workTimer = setInterval(renderWorkTimer, 1000);
    }

    function stopCamera() {
        video.srcObject?.getTracks().forEach((track) => track.stop());
        video.srcObject = null;
        video.hidden = true;
    }

    function clearPhoto(state) {
        if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
        state.selfie = null;
        state.photoUrl = null;
        photo.removeAttribute("src");
        photo.hidden = true;
    }

    function renderPreview(state) {
        const { selfie, location, camera, submitting } = state;
        confirm.disabled = !selfie || !location || submitting;
        find("confirm-in").hidden = submitting || state.action !== "in";
        find("confirm-out").hidden = submitting || state.action !== "out";
        find("confirm-progress").hidden = !submitting;
        cameraButton.disabled = submitting || camera === "loading" || camera === "starting";
        find("camera-capture").hidden = !["starting", "ready", "loading"].includes(camera);
        find("camera-retake").hidden = camera !== "captured";
        find("camera-retry").hidden = camera !== "error";
        find("location-retry").disabled = submitting;
        dialog.querySelectorAll("[data-punch-cancel]").forEach((button) => {
            button.disabled = submitting;
        });
    }

    function updateCamera(state, status, message = "") {
        state.camera = status;
        showMessage(find("camera-status"), message);
        renderPreview(state);
    }

    async function startCamera(state) {
        clearPhoto(state);
        updateCamera(state, "loading", "Starting camera…");

        try {
            if (!navigator.mediaDevices?.getUserMedia) throw new Error("no camera access");
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: { facingMode: "user", width: { ideal: 960 }, height: { ideal: 720 } },
            });
            if (preview !== state) {
                stream.getTracks().forEach((track) => track.stop());
                return;
            }
            video.srcObject = stream;
            updateCamera(state, "starting", "Starting camera…");
            await video.play();
            if (preview !== state) return;
            video.hidden = false;
            updateCamera(state, "ready");
        } catch {
            if (preview !== state) return;
            stopCamera();
            updateCamera(state, "error", "Allow camera access in your browser and try again.");
        }
    }

    function captureSelfie(state) {
        if (!video.videoWidth || !video.videoHeight) return;
        updateCamera(state, "starting");
        const canvas = document.createElement("canvas");
        const scale = Math.min(1, 1024 / Math.max(video.videoWidth, video.videoHeight));
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((image) => {
            if (preview !== state) return;
            if (!image) {
                updateCamera(state, "ready", "The selfie could not be captured. Try again.");
                return;
            }
            state.selfie = image;
            state.photoUrl = URL.createObjectURL(image);
            photo.src = state.photoUrl;
            photo.hidden = false;
            stopCamera();
            updateCamera(state, "captured");
        }, "image/jpeg", 0.86);
    }

    function getLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error("Location is unavailable in this browser."));
                return;
            }
            navigator.geolocation.getCurrentPosition(
                ({ coords }) => resolve({
                    latitude: coords.latitude.toFixed(6),
                    longitude: coords.longitude.toFixed(6),
                }),
                ({ code }) => reject(new Error(code === 1
                    ? "Allow location access in your browser and try again."
                    : "Your location could not be read. Try again.")),
                { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
            );
        });
    }

    async function loadLocation(state) {
        const status = find("location-status");
        const coordinates = find("location-coordinates");
        const map = find("location-map");
        const retry = find("location-retry");
        state.location = null;
        showMessage(status, "Getting your location…");
        showMessage(coordinates, "");
        map.hidden = true;
        map.removeAttribute("href");
        retry.hidden = true;
        renderPreview(state);

        try {
            state.location = await getLocation();
        } catch (error) {
            if (preview !== state) return;
            showMessage(status, error.message);
            retry.hidden = false;
            return;
        }

        if (preview !== state) {
            state.location = null;
            return;
        }

        const { latitude, longitude } = state.location;
        showMessage(coordinates, `${latitude}, ${longitude}`);
        map.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${latitude},${longitude}`)}`;
        map.hidden = false;
        renderPreview(state);
        showMessage(status, "Looking up street address…");

        const address = await requestJSON(dialog.dataset.locationUrl, {
            method: "POST",
            body: state.location,
            signal: state.lookup.signal,
        }).then((result) => result.address).catch(() => "");
        if (preview === state) showMessage(status, address || "Street address unavailable.");
    }

    function openPreview(button) {
        if (dialog.open) return;
        if (typeof dialog.showModal !== "function" || !globalThis.crypto?.randomUUID) {
            window.alert("Open KlockIN in a current browser over HTTPS to capture a punch.");
            return;
        }
        preview = {
            action: button.dataset.webPunch,
            uuid: crypto.randomUUID(),
            lookup: new AbortController(),
            trigger: button,
            submitting: false,
        };
        dialog.querySelector("h2").textContent = button.dataset.actionLabel;
        showMessage(find("punch-error"), "");
        dialog.showModal();
        startCamera(preview);
        loadLocation(preview);
    }

    function closePreview() {
        const state = preview;
        if (!state) return;
        preview = null;
        state.lookup.abort();
        stopCamera();
        clearPhoto(state);
        state.location = null;
        const map = find("location-map");
        map.removeAttribute("href");
        showMessage(find("location-coordinates"), "");
        showMessage(find("location-status"), "");
        showMessage(find("punch-error"), "");
        if (state.trigger.isConnected) state.trigger.focus();
        else clock.querySelector("[data-web-punch]")?.focus();
    }

    async function savePunch() {
        const state = preview;
        if (!state || state.submitting || !state.selfie || !state.location) return;
        state.submitting = true;
        showMessage(find("punch-error"), "");
        renderPreview(state);
        const body = new FormData();
        body.set("action", state.action);
        body.set("punch_uuid", state.uuid);
        body.set("selfie", state.selfie, "selfie.jpg");
        body.set("latitude", state.location.latitude);
        body.set("longitude", state.location.longitude);
        try {
            const result = await requestJSON(dialog.dataset.punchUrl, { method: "POST", body });
            if (result.ok !== true || typeof result.html !== "string") {
                throw new Error("The punch result could not be verified. Try again.");
            }
            clock.innerHTML = result.html;
            startWorkTimer();
            dialog.close();
            refreshBreak();
        } catch (error) {
            if (preview === state) showMessage(find("punch-error"), error.message);
        } finally {
            state.submitting = false;
            if (preview === state) renderPreview(state);
        }
    }

    function liveBreakSeconds() {
        return breakStatus?.active_since ? (performance.now() - breakStatus.receivedAt) / 1000 : 0;
    }

    function drawBreak() {
        if (breaks.hidden || !breakStatus) return;
        const status = breakStatus;
        const live = liveBreakSeconds();
        const elapsed = Number.isFinite(status.activeElapsed) ? Math.max(0, status.activeElapsed + live) : 0;
        breakField("allowed").textContent = duration(status.allowed_seconds);
        breakField("used").textContent = duration(Number(status.used_seconds) + live);
        breakField("remaining").textContent = duration(Number(status.remaining_seconds) - live);
        breakField("elapsed").textContent = duration(elapsed);
        showMessage(breakField("badge"), status.active_since ? duration(elapsed) : "");
    }

    function updateBreak(result) {
        breakStatus = {
            ...result,
            receivedAt: performance.now(),
            activeElapsed: (Date.parse(result.as_of) - Date.parse(result.active_since)) / 1000,
        };
        renderWorkTimer?.();
        const active = Boolean(result.active_since);
        breaks.hidden = !result.enabled && !active;
        if (breaks.hidden) {
            breaks.open = false;
            return;
        }
        const unavailable = !active && !result.can_start;
        const exhausted = Number(result.remaining_seconds) <= 0;
        breakField("active").hidden = !active;
        breakField("unavailable").hidden = !unavailable || exhausted;
        breakField("exhausted").hidden = !unavailable || !exhausted;
        breakField("start").hidden = active;
        breakField("end").hidden = !active;
        breakAction.hidden = !active && !result.can_start;
        breakAction.dataset.action = active ? "end" : "start";
        drawBreak();
    }

    async function refreshBreak() {
        if (changingBreak) return;
        const version = ++breakReadVersion;
        try {
            const result = await requestJSON(breaks.dataset.url);
            if (version === breakReadVersion) updateBreak(result);
        } catch {
            // A passive refresh should not interrupt a punch or display unavailable controls.
        }
    }

    async function changeBreak() {
        if (changingBreak || breakAction.hidden) return;
        changingBreak = true;
        breakReadVersion += 1;
        breakAction.disabled = true;
        breaks.setAttribute("aria-busy", "true");
        showMessage(breakField("error"), "");
        try {
            updateBreak(await requestJSON(breaks.dataset.url, {
                method: "POST",
                body: { action: breakAction.dataset.action },
            }));
        } catch (error) {
            showMessage(breakField("error"), error.message);
        } finally {
            changingBreak = false;
            breakAction.disabled = false;
            breaks.removeAttribute("aria-busy");
        }
    }

    clock.addEventListener("click", (event) => {
        const button = event.target.closest("[data-web-punch]");
        if (button) openPreview(button);
    });
    document.addEventListener("htmx:afterSwap", (event) => {
        if (event.detail?.target === clock) {
            startWorkTimer();
            refreshBreak();
        }
    });
    cameraButton.addEventListener("click", () => {
        if (preview?.camera === "ready") captureSelfie(preview);
        else if (preview) startCamera(preview);
    });
    find("location-retry").addEventListener("click", () => {
        if (preview) loadLocation(preview);
    });
    confirm.addEventListener("click", savePunch);
    dialog.querySelectorAll("[data-punch-cancel]").forEach((button) => {
        button.addEventListener("click", () => dialog.close());
    });
    dialog.addEventListener("cancel", (event) => {
        if (preview?.submitting) event.preventDefault();
    });
    dialog.addEventListener("close", closePreview);
    window.addEventListener("pagehide", () => {
        if (dialog.open) dialog.close();
        closePreview();
    });
    breakAction.addEventListener("click", changeBreak);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) refreshBreak();
    });

    startWorkTimer();
    refreshBreak();
    setInterval(drawBreak, 1000);
    setInterval(() => {
        if (!document.hidden && !breaks.hidden) refreshBreak();
    }, 60000);
})();
