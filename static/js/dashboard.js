document.addEventListener('DOMContentLoaded', function () {
    const socket = io();
    const tableBody = document.querySelector('#incidentsPane table tbody');

    socket.on('new_report', function(report) {
        // Remove the "No reports found" row if it exists
        const noReportsRow = document.querySelector('#no-reports-row');
        if (noReportsRow) {
            noReportsRow.remove();
        }

        const newRow = document.createElement('tr');
        
        // Handle Severity Badge
        let severityBadge = '';
        const sev = report.severity ? report.severity.toLowerCase() : 'low';
        if (sev === 'critical') {
            severityBadge = '<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25">CRITICAL</span>';
        } else if (sev === 'high') {
            severityBadge = '<span class="badge bg-warning bg-opacity-10 text-warning border border-warning border-opacity-25">HIGH</span>';
        } else if (sev === 'medium') {
            severityBadge = '<span class="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25">MEDIUM</span>';
        } else {
            severityBadge = '<span class="badge bg-secondary bg-opacity-10 text-secondary border border-secondary border-opacity-25">LOW</span>';
        }

        // Handle AI Badge
        const aiBadge = report.ai_suggestion 
            ? `<div class="small text-info"><i class="fas fa-robot me-1"></i>AI: ${report.ai_suggestion}</div>`
            : '';
            
        // Handle AI Detected indicator (for automated reports)
        const isAutomated = report.desc && report.desc.includes('Automated Detection');
        const aiDetectedIndicator = isAutomated 
            ? `<br><span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25 mt-1" style="font-size: 0.7rem;"><i class="fas fa-robot me-1"></i>AI DETECTED</span>`
            : '';

        // Format Date/Time
        const now = new Date();
        const dateStr = now.toISOString().split('T')[0];
        const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

        newRow.innerHTML = `
            <td class="ps-4 fw-bold">
                #${report.id}
                ${aiDetectedIndicator}
            </td>
            <td class="text-nowrap text-muted small">
                <div><i class="far fa-calendar me-1"></i> ${dateStr}</div>
                <div><i class="far fa-clock me-1"></i> ${report.time || timeStr}</div>
            </td>
            <td>
                <div class="fw-bold text-dark">${report.animal}</div>
                ${aiBadge}
            </td>
            <td>${report.condition}</td>
            <td>${severityBadge}</td>
            <td>
                <span class="text-muted fst-italic">Unclaimed</span>
            </td>
            <td class="text-end pe-4 align-middle">
                <form method="POST" style="display: inline-flex; align-items: center; gap: 0.5rem;">
                    <button type="button" class="btn btn-outline-secondary btn-sm px-2 shadow-sm"
                        data-bs-toggle="modal" data-bs-target="#detailsModal" data-id="${report.id}"
                        data-animal="${report.animal}" data-condition="${report.condition}"
                        data-severity="${report.severity}" data-desc="${report.desc}"
                        data-lat="${report.lat}" data-lon="${report.lon}"
                        data-image="${report.image_url || ''}"
                        data-ai="${report.ai_suggestion || 'None'}"
                        data-time="${report.time || (dateStr + ' ' + timeStr)}"
                        title="View Details">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button type="submit" formaction="${report.claim_url}"
                        class="btn btn-primary btn-sm fw-bold shadow-sm px-3 d-flex align-items-center">
                        <i class="fas fa-hand-paper me-2"></i> Accept Incident
                    </button>
                </form>
            </td>
        `;

        tableBody.prepend(newRow);

        // Desktop Notification
        if (Notification.permission === "granted") {
            new Notification("New Incident Reported!", {
                body: `A ${report.animal} needs help. Click to view dashboard.`,
            });
        } else if (Notification.permission !== "denied") {
            Notification.requestPermission();
        }
    });
});