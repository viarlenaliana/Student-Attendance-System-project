document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("[data-toggle-password]").forEach(function (toggleButton) {
    toggleButton.addEventListener("click", function () {
      var targetId = toggleButton.getAttribute("data-toggle-password");
      var inputElement = document.getElementById(targetId);
      if (!inputElement) {
        return;
      }
      var isHidden = inputElement.type === "password";
      inputElement.type = isHidden ? "text" : "password";
      toggleButton.textContent = isHidden ? "Ẩn" : "Hiện";
    });
  });

  document.querySelectorAll("[data-confirm-password-form]").forEach(function (formElement) {
    formElement.addEventListener("submit", function (event) {
      var newPasswordInput = formElement.querySelector("[name='new_password']");
      var confirmPasswordInput = formElement.querySelector("[name='confirm_password']");
      if (newPasswordInput && confirmPasswordInput && newPasswordInput.value !== confirmPasswordInput.value) {
        event.preventDefault();
        alert("Mật khẩu mới và xác nhận mật khẩu không khớp.");
        confirmPasswordInput.focus();
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
