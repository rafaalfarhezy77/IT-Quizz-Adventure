/**
 * IT Quest Adventure — Interactive Quiz Engine (Langkah 7)
 * Handles question pagination, option selection, background autosave,
 * status feedback, and submit confirmation modals.
 */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const config = window.QUIZ_CONFIG || {};
    const totalQuestions = config.totalQuestions || 0;
    if (totalQuestions === 0) return;

    let currentIndex = 0;

    // Elements
    const questionCards = document.querySelectorAll('.question-card');
    const navButtons = document.querySelectorAll('.q-nav-btn');
    const btnPrev = document.getElementById('btn-prev-question');
    const btnNext = document.getElementById('btn-next-question');
    const savePill = document.getElementById('autosave-status');
    const saveStatusText = document.getElementById('save-status-text');
    const answeredCountEl = document.getElementById('nav-answered-count');

    // Modals
    const modalSubmit = document.getElementById('modal-submit-confirm');
    const btnTriggerFinalSubmit = document.getElementById('btn-trigger-final-submit');
    const btnModalCancel = document.getElementById('btn-modal-cancel');
    const formFinalSubmit = document.getElementById('form-final-submit');
    const btnModalConfirmSubmit = document.getElementById('btn-modal-confirm-submit');

    const modalTotalVal = document.getElementById('modal-total-val');
    const modalAnsweredVal = document.getElementById('modal-answered-val');
    const modalUnansweredVal = document.getElementById('modal-unanswered-val');
    const unansweredWarningBox = document.getElementById('unanswered-warning-box');

    // Member Rotation Elements
    const modalMember = document.getElementById('modal-member-confirm');
    const btnTriggerMemberSubmit = document.getElementById('btn-trigger-member-submit');
    const btnMemberCancel = document.getElementById('btn-member-cancel');
    const btnMemberConfirm = document.getElementById('btn-member-confirm');
    const formMemberSubmit = document.getElementById('form-member-submit');

    // =========================================================================
    // 1. Question Pagination & Navigation
    // =========================================================================
    function showQuestion(index) {
      if (index < 0 || index >= totalQuestions) return;
      currentIndex = index;

      questionCards.forEach(function (card, idx) {
        if (idx === currentIndex) {
          card.classList.remove('hidden-question');
          card.classList.add('active-question');
        } else {
          card.classList.remove('active-question');
          card.classList.add('hidden-question');
        }
      });

      navButtons.forEach(function (btn, idx) {
        if (idx === currentIndex) {
          btn.classList.add('nav-active');
        } else {
          btn.classList.remove('nav-active');
        }
      });

      if (btnPrev) btnPrev.disabled = (currentIndex === 0);
      if (btnNext) btnNext.disabled = (currentIndex === totalQuestions - 1);
    }

    if (btnPrev) {
      btnPrev.addEventListener('click', function () {
        if (currentIndex > 0) showQuestion(currentIndex - 1);
      });
    }

    if (btnNext) {
      btnNext.addEventListener('click', function () {
        if (currentIndex < totalQuestions - 1) showQuestion(currentIndex + 1);
      });
    }

    navButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        const targetIdx = parseInt(this.getAttribute('data-index'), 10);
        if (!isNaN(targetIdx)) showQuestion(targetIdx);
      });
    });

    // =========================================================================
    // 2. Answer Selection & Autosave
    // =========================================================================
    function updateAnswerStats() {
      const checkedRadios = document.querySelectorAll('.option-radio-input:checked');
      const answeredCount = checkedRadios.length;
      if (answeredCountEl) answeredCountEl.textContent = answeredCount;
      return answeredCount;
    }

    function setSaveStatus(state, message) {
      if (!savePill || !saveStatusText) return;
      savePill.className = 'autosave-pill status-' + state;
      saveStatusText.textContent = message;
    }

    const savedAnswersMap = {};
    document.querySelectorAll('.option-radio-input:checked').forEach(function (r) {
      const qId = parseInt(r.getAttribute('data-question-id'), 10);
      if (!isNaN(qId)) savedAnswersMap[qId] = r.value;
    });

    function handleOptionSelect(radio) {
      if (!radio) return;
      radio.checked = true;
      const questionId = parseInt(radio.getAttribute('data-question-id'), 10);
      const selectedAnswer = radio.value;

      // Visual selection on option cards in the current question
      const container = radio.closest('.options-container');
      if (container) {
        container.querySelectorAll('.option-card').forEach(function (card) {
          card.classList.remove('option-selected');
        });
        const parentLabel = radio.closest('.option-card');
        if (parentLabel) parentLabel.classList.add('option-selected');
      }

      // Update navigator indicator
      const navBtn = document.getElementById('nav-btn-' + questionId);
      if (navBtn) {
        navBtn.classList.add('nav-answered');
        const checkSpan = navBtn.querySelector('.nav-check');
        if (checkSpan) checkSpan.textContent = '✓';
      }

      updateAnswerStats();

      // Avoid duplicate simultaneous requests if this answer is already saved
      if (savedAnswersMap[questionId] === selectedAnswer) {
        return;
      }
      savedAnswersMap[questionId] = selectedAnswer;

      saveAnswerToServer(questionId, selectedAnswer);
    }

    async function saveAnswerToServer(questionId, selectedAnswer) {
      setSaveStatus('saving', 'Menyimpan...');

      try {
        const response = await fetch(config.answerApiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': config.csrfToken,
            'Accept': 'application/json',
          },
          body: JSON.stringify({
            question_id: questionId,
            selected_answer: selectedAnswer,
          }),
        });

        const resData = await response.json();

        if (response.ok && resData.success) {
          setSaveStatus('saved', 'Tersimpan');
        } else {
          console.error('[QuizAutosave] Gagal:', resData.error);
          setSaveStatus('error', resData.error || 'Gagal menyimpan');
        }
      } catch (err) {
        console.error('[QuizAutosave] Network error:', err);
        setSaveStatus('error', 'Koneksi terputus');
      }
    }

    const radioInputs = document.querySelectorAll('.option-radio-input');
    radioInputs.forEach(function (radio) {
      radio.addEventListener('change', function () {
        handleOptionSelect(this);
      });
    });

    // =========================================================================
    // 3. Final Submit Modal & Idempotent Submission
    // =========================================================================
    if (btnTriggerFinalSubmit && modalSubmit) {
      btnTriggerFinalSubmit.addEventListener('click', function () {
        const answered = updateAnswerStats();
        const unanswered = Math.max(0, totalQuestions - answered);

        if (modalTotalVal) modalTotalVal.textContent = totalQuestions;
        if (modalAnsweredVal) modalAnsweredVal.textContent = answered;
        if (modalUnansweredVal) modalUnansweredVal.textContent = unanswered;

        if (unansweredWarningBox) {
          unansweredWarningBox.style.display = (unanswered > 0) ? 'flex' : 'none';
        }

        modalSubmit.style.display = 'flex';
      });
    }

    if (btnModalCancel && modalSubmit) {
      btnModalCancel.addEventListener('click', function () {
        modalSubmit.style.display = 'none';
      });
    }

    if (formFinalSubmit && btnModalConfirmSubmit) {
      formFinalSubmit.addEventListener('submit', function () {
        btnModalConfirmSubmit.disabled = true;
        btnModalConfirmSubmit.innerHTML = '<span>MEMPROSES PENILAIAN...</span>';
      });
    }

    // =========================================================================
    // 4. Member Rotation Submit Modal
    // =========================================================================
    if (btnTriggerMemberSubmit && modalMember) {
      btnTriggerMemberSubmit.addEventListener('click', function () {
        modalMember.style.display = 'flex';
      });
    }

    if (btnMemberCancel && modalMember) {
      btnMemberCancel.addEventListener('click', function () {
        modalMember.style.display = 'none';
      });
    }

    if (btnMemberConfirm && formMemberSubmit) {
      btnMemberConfirm.addEventListener('click', function () {
        this.disabled = true;
        this.innerHTML = '<span>MENYIMPAN BAGIAN...</span>';
        formMemberSubmit.submit();
      });
    }

    // Initial setup
    showQuestion(0);
    updateAnswerStats();
  });
})();
