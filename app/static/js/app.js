document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-toggle-password]").forEach(function (toggleButton) {
    toggleButton.setAttribute("aria-pressed", "false");
    toggleButton.addEventListener("click", function () {
      var targetId = toggleButton.getAttribute("data-toggle-password");
      var inputElement = document.getElementById(targetId);
      if (!inputElement) {
        return;
      }
      var isHidden = inputElement.type === "password";
      inputElement.type = isHidden ? "text" : "password";
      toggleButton.textContent = isHidden ? "Ẩn" : "Hiện";
      toggleButton.setAttribute("aria-pressed", isHidden ? "true" : "false");
    });
  });

  document.querySelectorAll("[data-confirm-password-form]").forEach(function (formElement) {
    var newPasswordInput = formElement.querySelector("[name='new_password']");
    var confirmPasswordInput = formElement.querySelector("[name='confirm_password']");
    if (!newPasswordInput || !confirmPasswordInput) {
      return;
    }

    var clearMismatchError = function () {
      confirmPasswordInput.setCustomValidity("");
    };

    newPasswordInput.addEventListener("input", clearMismatchError);
    confirmPasswordInput.addEventListener("input", clearMismatchError);

    formElement.addEventListener("submit", function (event) {
      if (newPasswordInput.value !== confirmPasswordInput.value) {
        event.preventDefault();
        confirmPasswordInput.setCustomValidity("Mật khẩu mới và xác nhận mật khẩu không khớp.");
        confirmPasswordInput.reportValidity();
        confirmPasswordInput.focus();
      } else {
        confirmPasswordInput.setCustomValidity("");
      }
    });
  });

  var otpInput = document.querySelector(".otp-input");
  if (otpInput) {
    otpInput.addEventListener("input", function () {
      otpInput.value = otpInput.value.replace(/\D/g, "").slice(0, 6);
    });
  }
});
