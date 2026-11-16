(() => {
  const linkInput = document.getElementById("round-invite-link");
  const copyButton = document.getElementById("copy-round-link");
  if (!linkInput || !copyButton) return;

  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(linkInput.value);
      copyButton.textContent = "Скопійовано ✓";
    } catch {
      linkInput.select();
      const copied = document.execCommand("copy");
      copyButton.textContent = copied ? "Скопійовано ✓" : "Скопіюй посилання";
    }
  });
})();
