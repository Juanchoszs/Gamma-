// Instant client-side modal behavior for Tastytrade API configuration
(function() {
    function getModal() {
        return document.getElementById('tt-modal');
    }

    function openModal() {
        var modal = getModal();
        if (modal) {
            modal.style.display = 'flex';
            var inp = document.getElementById('tt-input-client-id');
            if (inp && !inp.value) {
                setTimeout(function() { inp.focus(); }, 50);
            }
            console.log('Modal Tastytrade abierto');
        }
    }

    function closeModal() {
        var modal = getModal();
        if (modal) {
            modal.style.display = 'none';
            console.log('Modal Tastytrade cerrado');
        }
    }

    function showFeedback(message, isSuccess) {
        var feedback = document.getElementById('tt-modal-feedback');
        if (feedback) {
            feedback.innerHTML = message;
            feedback.style.display = 'block';
            if (isSuccess) {
                feedback.style.background = 'rgba(34, 197, 94, 0.15)';
                feedback.style.color = '#4ade80';
                feedback.style.border = '1px solid rgba(34, 197, 94, 0.3)';
                
                // Auto-cerrar el modal después de 3 segundos si es éxito
                setTimeout(function() {
                    closeModal();
                    console.log('Modal cerrado automáticamente tras éxito');
                    // Redirigir a la página principal
                    window.location.href = '/';
                }, 3000);
            } else {
                feedback.style.background = 'rgba(239, 68, 68, 0.15)';
                feedback.style.color = '#f87171';
                feedback.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            }
            console.log('Feedback mostrado:', message);
        }
    }

    document.addEventListener('click', function(e) {
        // Check for modal open triggers
        if (
            e.target.closest('#tt-modal-open-btn') ||
            e.target.closest('#rt-badge') ||
            e.target.closest('.tt-open-trigger') ||
            e.target.closest('[data-action="open-tt-modal"]')
        ) {
            e.preventDefault();
            openModal();
            return;
        }

        // Check for modal close triggers
        if (
            e.target.closest('#tt-modal-close-icon') ||
            e.target.closest('#tt-modal-close-btn') ||
            e.target.id === 'tt-modal'
        ) {
            e.preventDefault();
            closeModal();
            return;
        }
    }, true);

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' || e.keyCode === 27) {
            closeModal();
        }
    });

    // Expose functions globally for callbacks
    window.ttModal = {
        open: openModal,
        close: closeModal,
        showFeedback: showFeedback
    };

    console.log('Script Tastytrade modal cargado correctamente');
})();
