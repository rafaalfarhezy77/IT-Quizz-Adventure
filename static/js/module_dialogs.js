/* Local dialog behaviour for station modules that use Bootstrap-style markup. */
(() => {
  let activeDialog = null;
  let previousFocus = null;

  function closeDialog() {
    if (!activeDialog) return;
    activeDialog.classList.remove('is-open');
    activeDialog.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    activeDialog = null;
    if (previousFocus) previousFocus.focus();
  }

  function openDialog(dialog, trigger) {
    if (!dialog) return;
    previousFocus = trigger;
    activeDialog = dialog;
    dialog.classList.add('is-open');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.removeAttribute('aria-hidden');
    document.body.style.overflow = 'hidden';
    (dialog.querySelector('button, input, select, textarea, a') || dialog).focus();
  }

  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-bs-toggle="modal"]');
    if (trigger) {
      event.preventDefault();
      openDialog(document.querySelector(trigger.dataset.bsTarget), trigger);
      return;
    }
    if (event.target.closest('[data-bs-dismiss="modal"]') || (activeDialog && event.target === activeDialog)) {
      closeDialog();
    }
  });
  document.addEventListener('keydown', event => {
    if (!activeDialog) return;
    if (event.key === 'Escape') closeDialog();
    if (event.key === 'Tab') {
      const focusable = [...activeDialog.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]')];
      if (!focusable.length) return;
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
})();
