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
    messageBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  const requestCoordinates = () => new Promise((resolve, reject) => {
    // 1. Android Native Location Bridge (WebView over local HTTP or HTTPS)
    if (window.AndroidLocationBridge && typeof window.AndroidLocationBridge.requestLocation === 'function') {
      const cbName = '__onAndroidLocation_' + Date.now() + '_' + Math.floor(Math.random() * 10000);
      let timedOut = false;
      const timer = window.setTimeout(() => {
        timedOut = true;
        try { delete window[cbName]; } catch (e) { window[cbName] = undefined; }
        reject(new Error('Location request timed out. Please ensure GPS/Location is enabled and retry.'));
      }, 25000);

      window[cbName] = (success, lat, lng, accuracy, errorMsg) => {
        if (timedOut) return;
        window.clearTimeout(timer);
        try { delete window[cbName]; } catch (e) { window[cbName] = undefined; }
        if (success) {
          resolve({
            latitude: Number(lat),
            longitude: Number(lng),
            accuracy: Number(accuracy) || 10
          });
        } else {
          reject(new Error(errorMsg || 'Could not acquire your location coordinates. Please try again.'));
        }
      };

      try {
        window.AndroidLocationBridge.requestLocation(cbName);
      } catch (err) {
        window.clearTimeout(timer);
        try { delete window[cbName]; } catch (e) { window[cbName] = undefined; }
        reject(new Error('Device location bridge error: ' + (err.message || err)));
      }
      return;
    }

    // 2. Standard HTML5 Geolocation (Desktop & HTTPS browsers)
    if (!navigator.geolocation) {
      reject(new Error('This browser does not support geolocation capture. Please use a modern browser such as Chrome, Edge, or Safari with location services enabled.'));
      return;
    }

    const acquirePosition = (highAccuracy) => {
      navigator.geolocation.getCurrentPosition(
        position => resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy
        }),
        error => {
          // Laptops typically lack satellite GPS hardware; automatically retry with Wi-Fi triangulation
          if (highAccuracy && (error.code === 2 || error.code === 3)) {
            acquirePosition(false);
            return;
          }
          const errors = {
            1: 'Location permission was denied. In your browser address bar (top left next to the URL), click the Tune/Padlock icon, change Location to "Allow", then refresh the page.',
            2: 'Physical location is currently unavailable on this device. Ensure Windows Location Services or Wi-Fi positioning is enabled.',
            3: 'Location request timed out. Please refresh and try again.'
          };
          reject(new Error(errors[error.code] || 'Could not acquire your location coordinates. Please try again.'));
        },
        { enableHighAccuracy: highAccuracy, timeout: highAccuracy ? 10000 : 15000, maximumAge: 30000 }
      );
    };

    acquirePosition(true);
  });

  const attachGeoAction = (button) => {
    if (!button) return;
    button.addEventListener('click', async () => {
      const action = button.dataset.action;
      const original = button.innerHTML;
      button.disabled = true;
      button.innerHTML = '<span class="button-spinner"></span> Acquiring GPS coordinates…';
      if (messageBox) messageBox.hidden = true;
      try {
        const coordinates = await requestCoordinates();
        button.innerHTML = '<span class="button-spinner"></span> Validating with server…';
        const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
        const response = await fetch(`/api/attendance/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
          body: JSON.stringify(coordinates)
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
          throw new Error(result.message || 'Attendance request could not be validated.');
        }
        showMessage(result.message, 'success');
        button.innerHTML = '<i class="bi bi-check2-circle"></i> Recorded — refreshing…';
        window.setTimeout(() => window.location.reload(), 800);
      } catch (error) {
        showMessage(error.message || 'An unexpected error occurred while recording attendance. Please retry.', 'error');
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
      btn.innerHTML = '<span class="button-spinner"></span> Updating break status…';
      if (messageBox) messageBox.hidden = true;
      try {
        const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
        const response = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token }
        });
        const result = await response.json();
        if (!response.ok || !result.ok) {
          throw new Error(result.message || 'Could not update break status.');
        }
        showMessage(result.message, 'success');
        btn.innerHTML = '<i class="bi bi-check2-circle"></i> Updated — refreshing…';
        window.setTimeout(() => window.location.reload(), 800);
      } catch (error) {
        showMessage(error.message || 'An error occurred while updating break buffer. Please try again.', 'error');
        btn.disabled = false;
        btn.innerHTML = original;
      }
    });
  };

  attachBreakAction(breakStartButton, '/api/attendance/break-start');
  attachBreakAction(breakEndButton, '/api/attendance/break-end');
})();
