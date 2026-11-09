(() => {
  const checkInButton = document.getElementById('checkInButton');
  const checkOutButton = document.getElementById('checkOutButton');
  const breakStartButton = document.getElementById('breakStartButton');
  const breakEndButton = document.getElementById('breakEndButton');
  const messageBox = document.getElementById('attendanceMessage');

  const showMessage = (message, kind) => {
    if (!messageBox) return;
    messageBox.hidden = false;
    messageBox.className = `attendance-message message-${kind}`;
    messageBox.textContent = message;
  };

  const requestCoordinates = () => new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('This browser does not support location capture. Try a recent version of Chrome or Edge.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      position => resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
      error => {
        const errors = {
          1: 'Location permission was denied. Enable location permission for this site and try again.',
          2: 'Your current location is unavailable. Check device location services and try again.',
          3: 'Location request timed out. Move to an area with better GPS reception and retry.'
        };
        reject(new Error(errors[error.code] || 'Could not obtain your location. Please try again.'));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  });

  const attachGeoAction = (button) => {
    if (!button) return;
    button.addEventListener('click', async () => {
      const action = button.dataset.action;
      const original = button.innerHTML;
      button.disabled = true;
      button.innerHTML = '<span class="button-spinner"></span> Getting location…';
      if (messageBox) messageBox.hidden = true;
      try {
        const coordinates = await requestCoordinates();
        button.innerHTML = '<span class="button-spinner"></span> Saving attendance…';
        const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
        const response = await fetch(`/api/attendance/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
          body: JSON.stringify(coordinates)
        });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.message || 'Attendance could not be saved.');
        showMessage(result.message, 'success');
        button.innerHTML = '<i class="bi bi-check2-circle"></i> Saved — refreshing…';
        window.setTimeout(() => window.location.reload(), 800);
      } catch (error) {
        showMessage(error.message || 'Something went wrong. Please try again.', 'error');
        button.disabled = false;
        button.innerHTML = original;
      }
    });
  };

  attachGeoAction(checkInButton);
  attachGeoAction(checkOutButton);

  const attachBreakAction = (btn, endpoint) => {
    if (!btn) return;
    btn.addEventListener('click', async () => {
      const original = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="button-spinner"></span> Updating break…';
      if (messageBox) messageBox.hidden = true;
      try {
        const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token }
        });
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.message || 'Could not update break status.');
        showMessage(result.message, 'success');
        btn.innerHTML = '<i class="bi bi-check2-circle"></i> Updated — refreshing…';
        window.setTimeout(() => window.location.reload(), 800);
      } catch (error) {
        showMessage(error.message || 'Something went wrong. Please try again.', 'error');
        btn.disabled = false;
        btn.innerHTML = original;
      }
    });
  };

  attachBreakAction(breakStartButton, '/api/attendance/break-start');
  attachBreakAction(breakEndButton, '/api/attendance/break-end');
})();
