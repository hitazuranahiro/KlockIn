document.querySelectorAll(".auth-password-toggle").forEach((button) => {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) return;

    button.hidden = false;
    button.addEventListener("click", () => {
        const showPassword = input.type === "password";
        input.type = showPassword ? "text" : "password";
        button.textContent = showPassword ? button.dataset.hideLabel : button.dataset.showLabel;
        button.setAttribute(
            "aria-label",
            showPassword ? button.dataset.hidePasswordLabel : button.dataset.showPasswordLabel,
        );
    });
});
