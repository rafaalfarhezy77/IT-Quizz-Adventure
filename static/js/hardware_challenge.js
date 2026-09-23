/**
 * IT Quest Adventure — Hardware Challenge Client Script
 * Handles image preview, client validations, draft autosave, and confirmation modal.
 */
(function () {
  'use strict';

  const form = document.getElementById('hardware-submission-form');
  const screenshotInput = document.getElementById('screenshot-input');
  const previewContainer = document.getElementById('image-preview-container');
  const previewImg = document.getElementById('image-preview');
  const btnSaveDraft = document.getElementById('btn-save-draft');
  const btnSubmitTrigger = document.getElementById('btn-submit-trigger');
  const modal = document.getElementById('submit-confirm-modal');
  const btnModalCancel = document.getElementById('btn-modal-cancel');
  const btnModalConfirm = document.getElementById('btn-modal-confirm');
  const autosaveText = document.getElementById('autosave-text');
  const autosaveIndicator = document.getElementById('autosave-indicator');

  // 1. Screenshot Image Preview
  if (screenshotInput) {
    screenshotInput.addEventListener('change', function () {
      const file = this.files && this.files[0];
      if (!file) return;

      const validTypes = ['image/png', 'image/jpeg', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        alert('Format berkas tidak valid! Harap pilih gambar dengan format PNG, JPG/JPEG, atau WebP.');
        this.value = '';
        if (previewContainer) previewContainer.style.display = 'none';
        return;
      }

      const maxSize = 5 * 1024 * 1024;
      if (file.size > maxSize) {
        alert('Ukuran berkas terlalu besar! Maksimal 5 MB.');
        this.value = '';
        if (previewContainer) previewContainer.style.display = 'none';
        return;
      }

      const reader = new FileReader();
      reader.onload = function (e) {
        if (previewImg) {
          previewImg.src = e.target.result;
          if (previewContainer) previewContainer.style.display = 'block';
        }
      };
      reader.readAsDataURL(file);
    });
  }

  // 2. Draft Save Action
  async function saveDraft() {
    if (!form) return;

    if (autosaveText && autosaveIndicator) {
      autosaveText.textContent = 'Menyimpan draft...';
      autosaveIndicator.className = 'autosave-pill status-saving';
    }

    try {
      const formData = new FormData(form);
      const response = await fetch('/api/participant/hardware/draft', {
        method: 'POST',
        body: formData,
        cache: 'no-store',
      });

      const data = await response.json();
      if (response.ok && data.success) {
        if (autosaveText && autosaveIndicator) {
          autosaveText.textContent = 'Draft Tersimpan ✓';
          autosaveIndicator.className = 'autosave-pill status-saved';
        }
      } else {
        if (autosaveText && autosaveIndicator) {
          autosaveText.textContent = 'Gagal menyimpan draft';
          autosaveIndicator.className = 'autosave-pill status-unsaved';
        }
      }
    } catch (err) {
      console.warn('[HardwareChallenge] Save draft error:', err);
      if (autosaveText && autosaveIndicator) {
        autosaveText.textContent = 'Koneksi terputus';
        autosaveIndicator.className = 'autosave-pill status-unsaved';
      }
    }
  }

  if (btnSaveDraft) {
    btnSaveDraft.addEventListener('click', saveDraft);
  }

  // Auto-save draft on blur of text inputs
  const inputs = form ? form.querySelectorAll('input, textarea') : [];
  inputs.forEach(input => {
    if (input.type !== 'file' && input.type !== 'hidden') {
      input.addEventListener('blur', function () {
        saveDraft();
      });
    }
  });

  // 3. Confirmation Modal Before Final Submit
  if (btnSubmitTrigger && modal) {
    btnSubmitTrigger.addEventListener('click', function () {
      // Validasi client-side dasar
      const urlInput = document.getElementById('buildcores_url');
      const priceInput = document.getElementById('total_price');
      const checkInput = document.getElementById('confirmation_checked');

      if (!urlInput || !urlInput.value.trim()) {
        alert('URL BuildCores wajib diisi!');
        urlInput.focus();
        return;
      }

      if (!priceInput || parseFloat(priceInput.value) <= 0 || isNaN(parseFloat(priceInput.value))) {
        alert('Total harga build harus bernilai positif!');
        priceInput.focus();
        return;
      }

      if (!checkInput || !checkInput.checked) {
        alert('Anda wajib mencentang pernyataan kesesuaian data sebelum mengirim!');
        checkInput.focus();
        return;
      }

      modal.style.display = 'flex';
    });
  }

  if (btnModalCancel && modal) {
    btnModalCancel.addEventListener('click', function () {
      modal.style.display = 'none';
    });
  }

  if (btnModalConfirm && form) {
    btnModalConfirm.addEventListener('click', function () {
      btnModalConfirm.disabled = true;
      btnModalConfirm.textContent = 'Mengirim...';
      form.submit();
    });
  }
})();
