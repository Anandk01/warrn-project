document.addEventListener('DOMContentLoaded', function () {
    const map = L.map('map').setView([20.5937, 78.9629], 5); // Centered on India
    // Use Google Maps with gl=IN for correct Indian political borders (HTTPS)
    L.tileLayer('https://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&hl=en-IN&gl=IN', {
        maxZoom: 20,
        subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
        attribution: 'Map data ©2024 Google'
    }).addTo(map);

    const redIcon = new L.Icon({ iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png', shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png', iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41] });

    const reportMarkers = L.layerGroup().addTo(map);

    function addMarkerToMap(report) {
        const marker = L.marker([report.lat, report.lon], { icon: redIcon }).addTo(reportMarkers);

        let popupContent = `<b>Status:</b> ${report.status}<br><b>Reported as:</b> ${report.animal}`;
        if (report.ai_suggestion) {
            popupContent += `<br><b>AI Suggestion:</b> ${report.ai_suggestion}`;
        }
        popupContent += `<br><b>Time:</b> ${report.time}`;
        if (report.desc) {
            popupContent += `<br><b>Description:</b> ${report.desc}`;
        }
        if (report.image_url) {
            popupContent += `<br><img src="${report.image_url}" alt="Incident Image" style="width:150px;height:auto;margin-top:5px;">`;
        }

        marker.bindPopup(popupContent);
    }

    // Initial Load of existing reports
    fetch('/api/reports')
        .then(response => response.json())
        .then(reports => {
            reports.forEach(addMarkerToMap);
        });

    // Real-Time Updates with WebSockets
    const socket = io();
    socket.on('new_report', function (report) {
        addMarkerToMap(report);
        map.panTo([report.lat, report.lon]);
    });

    // Form Handling for New Reports
    const locationStatus = document.getElementById('locationStatus');
    const latInput = document.getElementById('latitude');
    const lonInput = document.getElementById('longitude');
    const submitBtn = document.getElementById('submitBtn');
    const imageInput = document.getElementById('image');
    const imageStatus = document.getElementById('imageStatus');
    let manualMarker = null;
    let imageVerified = false;

    function updateLocation(lat, lon, message) {
        latInput.value = lat;
        lonInput.value = lon;
        locationStatus.textContent = message;
        locationStatus.style.color = 'green';
        updateSubmitButton();

        if (manualMarker) {
            map.removeLayer(manualMarker);
        }

        manualMarker = L.marker([lat, lon]).addTo(map).bindPopup('New Incident Location').openPopup();
        map.setView([lat, lon], 15);
    }

    function updateSubmitButton() {
        submitBtn.disabled = !(latInput.value && lonInput.value && imageVerified);
    }

    // Image verification
    imageInput.addEventListener('change', function () {
        const file = this.files[0];
        if (!file) {
            imageStatus.textContent = '';
            imageVerified = false;
            updateSubmitButton();
            return;
        }

        // Check file size (10MB limit)
        if (file.size > 10 * 1024 * 1024) {
            imageStatus.textContent = '✗ File too large. Please use images under 10MB.';
            imageStatus.style.color = 'red';
            imageVerified = false;
            updateSubmitButton();
            return;
        }

        // Check file type
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif'];
        if (!allowedTypes.includes(file.type)) {
            imageStatus.textContent = '✗ Invalid file type. Please upload JPG, PNG, or GIF images only.';
            imageStatus.style.color = 'red';
            imageVerified = false;
            updateSubmitButton();
            return;
        }

        imageStatus.textContent = 'Verifying image...';
        imageStatus.style.color = 'orange';
        imageVerified = false;
        updateSubmitButton();

        const formData = new FormData();
        formData.append('image', file);

        // Set timeout for the request
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        fetch('/verify-image', {
            method: 'POST',
            body: formData,
            signal: controller.signal
        })
            .then(response => {
                clearTimeout(timeoutId);
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    if (data.detected_animal && data.detected_animal !== 'Unknown') {
                        imageStatus.textContent = `✓ ${data.message}`;
                        imageStatus.style.color = 'green';

                        // Auto-fill animal type if detected
                        const animalSelect = document.getElementById('animal_type');
                        if (animalSelect && data.detected_animal) {
                            const options = animalSelect.options;
                            for (let i = 0; i < options.length; i++) {
                                if (options[i].value.toLowerCase() === data.detected_animal.toLowerCase()) {
                                    animalSelect.selectedIndex = i;
                                    break;
                                }
                            }
                        }
                    } else {
                        imageStatus.textContent = `⚠ ${data.message}`;
                        imageStatus.style.color = 'orange';
                    }
                    imageVerified = true;
                } else {
                    imageStatus.textContent = `✗ ${data.message}`;
                    imageStatus.style.color = 'red';
                    imageVerified = false;
                }
                updateSubmitButton();
            })
            .catch(error => {
                clearTimeout(timeoutId);
                if (error.name === 'AbortError') {
                    imageStatus.textContent = '✗ Upload timeout. Please try a smaller image.';
                } else {
                    imageStatus.textContent = '✗ Error verifying image. Please try again.';
                }
                imageStatus.style.color = 'red';
                imageVerified = false;
                updateSubmitButton();
            });
    });

    document.getElementById('useLocationBtn').addEventListener('click', () => {
        locationStatus.textContent = 'Getting location...';
        if (!navigator.geolocation) {
            locationStatus.textContent = 'Geolocation is not supported by your browser.';
            locationStatus.style.color = 'red';
            return;
        }

        const options = {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        };

        navigator.geolocation.getCurrentPosition(
            (position) => {
                updateLocation(position.coords.latitude, position.coords.longitude, `Current location captured.`);
            },
            (error) => {
                console.warn(`ERROR(${error.code}): ${error.message}`);
                let msg = 'Could not get your location.';
                switch (error.code) {
                    case error.PERMISSION_DENIED:
                        msg = "Location access denied. Please allow location access in your browser settings.";
                        break;
                    case error.POSITION_UNAVAILABLE:
                        msg = "Location information is unavailable.";
                        break;
                    case error.TIMEOUT:
                        msg = "The request to get user location timed out.";
                        break;
                }
                locationStatus.textContent = msg + ' Please click on the map manually.';
                locationStatus.style.color = 'red';
            },
            options
        );
    });

    map.on('click', e => {
        updateLocation(e.latlng.lat, e.latlng.lng, `Manual location selected.`);
    });
});