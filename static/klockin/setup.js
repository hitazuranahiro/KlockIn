(() => {
    let locationData;

    function loadLocationData(url) {
        if (!locationData) {
            locationData = new Promise((resolve, reject) => {
                const script = document.createElement("script");
                script.src = url;
                script.onload = resolve;
                script.onerror = reject;
                document.head.append(script);
            });
        }
        return locationData;
    }

    function showRequestError() {
        const notice = document.querySelector("[data-setup-error]");
        if (notice) notice.hidden = false;
    }

    function prepareCompanyForm() {
        const form = document.querySelector("[data-setup-country]");
        if (!form || form.dataset.locationReady) return;
        form.dataset.locationReady = "true";
        loadLocationData(form.dataset.setupCountry).then(() => {
            if (!form.isConnected) return;
            const country = form.elements.country;
            const state = form.elements.state;
            window.populateCountries(country.id, state.id);
            country.options[0].text = country.dataset.placeholder;
            state.options[0].text = state.dataset.placeholder;
            country.addEventListener("change", () => state.removeAttribute("data-selected"), true);
            country.addEventListener("change", () => {
                state.options[0].text = state.dataset.placeholder;
            });
        }).catch(() => {
            locationData = undefined;
            delete form.dataset.locationReady;
            showRequestError();
        });
    }

    function passwordMatch(form) {
        const pass = form.elements.password;
        const confirmation = form.elements.confirm_password;
        const error = form.querySelector("#setup-password-error");
        const hasMismatch = Boolean(confirmation.value && confirmation.value !== pass.value);
        confirmation.setCustomValidity(hasMismatch ? error.textContent.trim() : "");
        if (hasMismatch) confirmation.setAttribute("aria-invalid", "true");
        else confirmation.removeAttribute("aria-invalid");
        error.hidden = !hasMismatch;
    }

    document.addEventListener("click", (event) => {
        const trigger = event.target.closest("[data-setup-password]");
        if (!trigger) return;
        const input = document.getElementById(trigger.getAttribute("aria-controls"));
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        trigger.setAttribute("aria-pressed", String(show));
        trigger.setAttribute("aria-label", show ? trigger.dataset.hideLabel : trigger.dataset.showLabel);
        trigger.textContent = show ? trigger.dataset.hide : trigger.dataset.show;
    });

    document.addEventListener("input", (event) => {
        const form = event.target.closest("[data-setup-signup]");
        if (form && ["password", "confirm_password"].includes(event.target.name)) {
            passwordMatch(form);
        }
    });

    document.body.addEventListener("htmx:configRequest", (event) => {
        const form = event.detail.elt;
        if (form.matches("[data-setup-signup]")) {
            passwordMatch(form);
            if (!form.reportValidity()) event.preventDefault();
        }
        const notice = document.querySelector("[data-setup-error]");
        if (notice) notice.hidden = true;
    });

    document.body.addEventListener("htmx:afterSettle", (event) => {
        const target = event.detail.target;
        if (target.id === "ohAuthCard") {
            document.getElementById("setup-step-title")?.focus();
        } else if (["initializeDepartment", "initializeJobPositions"].includes(target.id)) {
            document.getElementById(target.id)?.querySelector("input[type=text]")?.focus();
        }
        prepareCompanyForm();
    });

    document.body.addEventListener("htmx:responseError", showRequestError);
    document.body.addEventListener("htmx:sendError", showRequestError);
    document.body.addEventListener("htmx:timeout", showRequestError);

    prepareCompanyForm();
})();
