(() => {
  const menuButton = document.getElementById('mobileMenu');
  const sidebar = document.getElementById('sidebar');
  if (menuButton && sidebar) {
    menuButton.addEventListener('click', () => sidebar.classList.toggle('sidebar-open'));
    document.addEventListener('click', (event) => {
      if (window.innerWidth <= 900 && sidebar.classList.contains('sidebar-open') && !sidebar.contains(event.target) && !menuButton.contains(event.target)) {
        sidebar.classList.remove('sidebar-open');
      }
    });
  }
})();
