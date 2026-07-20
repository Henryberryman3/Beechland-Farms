async function apiFetch(path, options = {}) {
    const response = await fetch(path, options);
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;

    if (!response.ok) {
        const message = payload?.error || payload?.message || `Request failed with status ${response.status}`;
        throw new Error(message);
    }

    return payload;
}

function normalizeError(error) {
    return (error && error.message) ? error.message : String(error);
}

async function fetchFarms() {
    return apiFetch('/api/farms');
}

async function createFarm(name) {
    return apiFetch('/api/farms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
}

async function fetchFarm(farmId) {
    return apiFetch(`/api/farms/${encodeURIComponent(farmId)}`);
}

async function fetchFields(farmId) {
    return apiFetch(`/api/fields?farmId=${encodeURIComponent(farmId)}`);
}

async function createField(farmId, name) {
    return apiFetch('/api/fields', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ farm_id: farmId, name })
    });
}

async function renameField(fieldId, name) {
    return apiFetch(`/api/fields/${encodeURIComponent(fieldId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
}

async function deleteField(fieldId) {
    return apiFetch(`/api/fields/${encodeURIComponent(fieldId)}`, {
        method: 'DELETE'
    });
}

async function fetchField(fieldId) {
    return apiFetch(`/api/fields/${encodeURIComponent(fieldId)}`);
}

async function fetchImages(fieldId) {
    return apiFetch(`/api/images?fieldId=${encodeURIComponent(fieldId)}`);
}

async function uploadImage(fieldId, file) {
    const formData = new FormData();
    formData.append('field_id', fieldId);
    formData.append('file', file);

    return apiFetch('/api/images', {
        method: 'POST',
        body: formData
    });
}
