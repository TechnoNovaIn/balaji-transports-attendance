(() => {
  const menuButton = document.getElementById('mobileMenu');
  const bottomMenuButton = document.getElementById('bottomNavMenuBtn');
  const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebarBackdrop');

  const toggleSidebar = (forceState) => {
    if (!sidebar) return;
    const shouldOpen = typeof forceState === 'boolean' ? forceState : !sidebar.classList.contains('sidebar-open');
    if (shouldOpen) {
      sidebar.classList.add('sidebar-open');
      if (backdrop) backdrop.classList.add('active');
      document.body.style.overflow = window.innerWidth <= 1000 ? 'hidden' : '';
    } else {
      sidebar.classList.remove('sidebar-open');
      if (backdrop) backdrop.classList.remove('active');
      document.body.style.overflow = '';
    }
  };

  if (sidebar) {
    if (menuButton) {
      menuButton.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleSidebar();
      });
    }

    if (bottomMenuButton) {
      bottomMenuButton.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleSidebar();
      });
    }

    if (sidebarCloseBtn) {
      sidebarCloseBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleSidebar(false);
      });
    }

    if (backdrop) {
      backdrop.addEventListener('click', () => toggleSidebar(false));
    }

    document.addEventListener('click', (event) => {
      if (window.innerWidth <= 1000 && sidebar.classList.contains('sidebar-open')) {
        const isTrigger = (menuButton && menuButton.contains(event.target)) ||
                          (bottomMenuButton && bottomMenuButton.contains(event.target)) ||
                          (sidebarCloseBtn && sidebarCloseBtn.contains(event.target));
        if (!sidebar.contains(event.target) && !isTrigger) {
          toggleSidebar(false);
        }
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && sidebar.classList.contains('sidebar-open')) {
        toggleSidebar(false);
      }
    });

    window.addEventListener('resize', () => {
      if (window.innerWidth > 1000 && sidebar.classList.contains('sidebar-open')) {
        toggleSidebar(false);
      }
    });
  }

  // --- Attendance Records Action Dropdowns ---
  let activeDropdown = null;

  const closeActiveDropdown = () => {
    if (!activeDropdown) return;
    const { btn, menu } = activeDropdown;
    btn.setAttribute('aria-expanded', 'false');
    menu.classList.remove('show');
    menu.style.position = '';
    menu.style.top = '';
    menu.style.left = '';
    menu.style.zIndex = '';
    activeDropdown = null;
  };

  const positionDropdown = (btn, menu) => {
    const rect = btn.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.zIndex = '1000';
    menu.style.display = 'flex';
    menu.style.visibility = 'hidden';

    const menuRect = menu.getBoundingClientRect();
    const menuWidth = menuRect.width || 215;
    const menuHeight = menuRect.height || 180;

    menu.style.display = '';
    menu.style.visibility = '';

    // Calculate vertical position (prefer below, flip above if overflowing viewport)
    let top = rect.bottom + 4;
    if (top + menuHeight > window.innerHeight - 8 && rect.top - menuHeight > 8) {
      top = rect.top - menuHeight - 4;
    }

    // Calculate horizontal position (align to left edge of button, or clamp if overflowing)
    let left = rect.left;
    if (left + menuWidth > window.innerWidth - 12) {
      left = Math.max(12, window.innerWidth - menuWidth - 12);
    }
    if (left < 12) {
      left = 12;
    }

    menu.style.top = `${Math.round(top)}px`;
    menu.style.left = `${Math.round(left)}px`;
  };

  const toggleDropdown = (btn, menu) => {
    const isOpen = menu.classList.contains('show');
    if (isOpen) {
      closeActiveDropdown();
    } else {
      closeActiveDropdown();
      positionDropdown(btn, menu);
      menu.classList.add('show');
      btn.setAttribute('aria-expanded', 'true');
      activeDropdown = { btn, menu };

      // Focus first actionable item for keyboard accessibility
      const firstFocusable = menu.querySelector('button:not(:disabled), a, input');
      if (firstFocusable) {
        firstFocusable.focus();
      }
    }
  };

  document.querySelectorAll('.action-dropdown').forEach((dropdown) => {
    const btn = dropdown.querySelector('.action-dropdown-btn');
    const menu = dropdown.querySelector('.action-menu');
    if (!btn || !menu) return;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleDropdown(btn, menu);
    });

    btn.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleDropdown(btn, menu);
      }
    });
  });

  // Global dismiss listeners
  document.addEventListener('click', (e) => {
    if (activeDropdown && !activeDropdown.menu.contains(e.target) && !activeDropdown.btn.contains(e.target)) {
      closeActiveDropdown();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && activeDropdown) {
      const btnToFocus = activeDropdown.btn;
      closeActiveDropdown();
      if (btnToFocus) btnToFocus.focus();
    }
  });

  // Dismiss on window scroll or resize to keep menu attached and avoid clipping
  window.addEventListener('scroll', () => {
    if (activeDropdown) closeActiveDropdown();
  }, { passive: true });

  window.addEventListener('resize', () => {
    if (activeDropdown) closeActiveDropdown();
  });

  // Prevent duplicate submissions in action menu forms
  document.querySelectorAll('.action-menu-form').forEach((form) => {
    form.addEventListener('submit', function (e) {
      const submitBtn = this.querySelector('button[type="submit"]');
      if (submitBtn) {
        if (submitBtn.disabled) {
          e.preventDefault();
          return false;
        }
        setTimeout(() => {
          submitBtn.disabled = true;
          const textSpan = submitBtn.querySelector('span');
          if (textSpan) textSpan.textContent = 'Processing...';
        }, 0);
      }
    });
  });
})();
