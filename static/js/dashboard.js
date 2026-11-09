(() => {
  const data = window.dashboardData;
  if (!data) return;
  const trendCanvas = document.getElementById('attendanceTrend');
  const distributionCanvas = document.getElementById('attendanceDistribution');
  if (typeof Chart === 'undefined') {
    const fallback = document.getElementById('trendFallback');
    if (fallback) fallback.hidden = false;
    return;
  }
  Chart.defaults.font.family = "'DM Sans', sans-serif";
  Chart.defaults.color = '#8691a5';
  Chart.defaults.plugins.legend.display = false;
  if (trendCanvas) {
    new Chart(trendCanvas, {
      type: 'line',
      data: { labels: data.labels, datasets: [{ label: 'Present', data: data.values, borderColor: '#4563eb', backgroundColor: 'rgba(69, 99, 235, .10)', borderWidth: 2.5, fill: true, tension: .35, pointRadius: 3.5, pointHoverRadius: 5, pointBackgroundColor: '#ffffff', pointBorderColor: '#4563eb', pointBorderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { intersect: false, mode: 'index' }, plugins: { tooltip: { backgroundColor: '#152340', padding: 12, cornerRadius: 8, displayColors: false } }, scales: { x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkip: false } }, y: { beginAtZero: true, suggestedMax: 5, ticks: { precision: 0, padding: 10 }, grid: { color: '#edf0f5', drawTicks: false }, border: { display: false } } } }
    });
  }
  if (distributionCanvas) {
    const values = [data.present, data.absent, data.late];
    const colors = ['#22a06b', '#f0ad43', '#e26a7a'];
    new Chart(distributionCanvas, {
      type: 'doughnut',
      data: { labels: ['Present', 'Absent', 'Late arrivals'], datasets: [{ data: values.every(value => value === 0) ? [1, 0, 0] : values, backgroundColor: values.every(value => value === 0) ? ['#e8ecf3', ...colors.slice(1)] : colors, borderWidth: 0, hoverOffset: 3, spacing: 3 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '76%', plugins: { tooltip: { callbacks: { label: (context) => `${context.label}: ${values[context.dataIndex] || 0}` } } } }
    });
  }
})();
