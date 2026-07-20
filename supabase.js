const SUPABASE_URL = 'https://qsbhvpbzyuqyttynjpgx.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_hyBlz1tYm-avs9AIBckbcg_6jGQsXsn';
const SUPABASE_IMAGE_BUCKET = 'images';

const supabase = typeof createClient === 'function'
    ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
    : null;

const localFarmsKey = 'beechland-farms';
const localFieldsKey = 'beechland-fields';
const localImagesKey = 'beechland-images';

function hasSupabaseConfig() {
    return SUPABASE_URL && SUPABASE_URL.indexOf('your-project') === -1
        && SUPABASE_ANON_KEY && SUPABASE_ANON_KEY.indexOf('your-anon') === -1;
}

function supabaseEnabled() {
    return supabase && hasSupabaseConfig();
}

function localStorageJson(key, fallback) {
    try {
        return JSON.parse(localStorage.getItem(key) || fallback);
    } catch {
        return JSON.parse(fallback);
    }
}

function localSaveJson(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function getFarmsLocal() {
    return localStorageJson(localFarmsKey, '[]');
}

function saveFarmsLocal(farms) {
    localSaveJson(localFarmsKey, farms);
}

function getFieldsMapLocal() {
    return localStorageJson(localFieldsKey, '{}');
}

function saveFieldsMapLocal(map) {
    localSaveJson(localFieldsKey, map);
}

function getImagesMapLocal() {
    return localStorageJson(localImagesKey, '{}');
}

function saveImagesMapLocal(map) {
    localSaveJson(localImagesKey, map);
}

function generateId() {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function normalizeError(error) {
    return error?.message || error?.error_description || error?.msg || 'Unknown error';
}

async function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

async function fetchFarms() {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('farms')
            .select('id,name')
            .order('name', { ascending: true });
        if (error) throw new Error(normalizeError(error));
        return data || [];
    }
    return getFarmsLocal();
}

async function createFarm(name) {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('farms')
            .insert({ name })
            .select()
            .single();
        if (error) throw new Error(normalizeError(error));
        return data;
    }
    const farms = getFarmsLocal();
    const farm = { id: generateId(), name };
    farms.push(farm);
    saveFarmsLocal(farms);
    return farm;
}

async function fetchFarm(farmId) {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('farms')
            .select('id,name')
            .eq('id', farmId)
            .single();
        if (error) throw new Error(normalizeError(error));
        return data;
    }
    return getFarmsLocal().find(farm => farm.id === farmId) || null;
}

async function fetchFields(farmId) {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('fields')
            .select('id,name')
            .eq('farm_id', farmId)
            .order('name', { ascending: true });
        if (error) throw new Error(normalizeError(error));
        return data || [];
    }
    const map = getFieldsMapLocal();
    return map[farmId] || [];
}

async function createField(farmId, name) {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('fields')
            .insert({ farm_id: farmId, name })
            .select()
            .single();
        if (error) throw new Error(normalizeError(error));
        return data;
    }
    const map = getFieldsMapLocal();
    const fields = map[farmId] || [];
    const field = { id: generateId(), name };
    fields.push(field);
    map[farmId] = fields;
    saveFieldsMapLocal(map);
    return { ...field, farm_id: farmId };
}

async function renameField(fieldId, name) {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('fields')
            .update({ name })
            .eq('id', fieldId)
            .select()
            .single();
        if (error) throw new Error(normalizeError(error));
        return data;
    }
    const map = getFieldsMapLocal();
    for (const farmId in map) {
        const fields = map[farmId];
        const field = fields.find(item => item.id === fieldId);
        if (field) {
            field.name = name;
            saveFieldsMapLocal(map);
            return field;
        }
    }
    return null;
}

async function deleteField(fieldId) {
    if (supabaseEnabled()) {
        const { error: deleteImagesError } = await supabase
            .from('images')
            .delete()
            .eq('field_id', fieldId);
        if (deleteImagesError) throw new Error(normalizeError(deleteImagesError));

        const { error } = await supabase
            .from('fields')
            .delete()
            .eq('id', fieldId);
        if (error) throw new Error(normalizeError(error));
        return true;
    }
    const fieldsMap = getFieldsMapLocal();
    for (const farmId in fieldsMap) {
        fieldsMap[farmId] = fieldsMap[farmId].filter(field => field.id !== fieldId);
    }
    const imagesMap = getImagesMapLocal();
    delete imagesMap[fieldId];
    saveFieldsMapLocal(fieldsMap);
    saveImagesMapLocal(imagesMap);
    return true;
}

async function fetchField(fieldId) {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('fields')
            .select('id,farm_id,name')
            .eq('id', fieldId)
            .single();
        if (error) throw new Error(normalizeError(error));
        return data;
    }
    const map = getFieldsMapLocal();
    for (const farmId in map) {
        const field = map[farmId].find(item => item.id === fieldId);
        if (field) return { ...field, farm_id: farmId };
    }
    return null;
}

async function uploadImage(fieldId, file) {
    if (supabaseEnabled()) {
        const path = `${fieldId}/${Date.now()}_${file.name}`;
        const { error: uploadError } = await supabase
            .storage
            .from(SUPABASE_IMAGE_BUCKET)
            .upload(path, file);
        if (uploadError) throw new Error(normalizeError(uploadError));

        const { data: publicData, error: publicError } = supabase
            .storage
            .from(SUPABASE_IMAGE_BUCKET)
            .getPublicUrl(path);
        if (publicError) throw new Error(normalizeError(publicError));

        const publicUrl = publicData?.publicUrl || '';
        const { data, error: imageError } = await supabase
            .from('images')
            .insert({ field_id: fieldId, name: file.name, storage_path: path, public_url: publicUrl })
            .select()
            .single();
        if (imageError) throw new Error(normalizeError(imageError));
        return data;
    }

    const imagesMap = getImagesMapLocal();
    imagesMap[fieldId] = imagesMap[fieldId] || [];
    const dataUrl = await readFileAsDataUrl(file);
    const image = {
        id: generateId(),
        name: file.name,
        dataUrl,
        uploadedAt: new Date().toISOString(),
    };
    imagesMap[fieldId].push(image);
    saveImagesMapLocal(imagesMap);
    return image;
}

async function fetchImages(fieldId) {
    if (supabaseEnabled()) {
        const { data, error } = await supabase
            .from('images')
            .select('id,field_id,name,public_url,uploaded_at')
            .eq('field_id', fieldId)
            .order('uploaded_at', { ascending: false });
        if (error) throw new Error(normalizeError(error));
        return (data || []).map(item => ({
            id: item.id,
            name: item.name,
            url: item.public_url,
            uploadedAt: item.uploaded_at,
        }));
    }

    const images = getImagesMapLocal();
    return (images[fieldId] || []).slice().sort((a, b) => b.uploadedAt.localeCompare(a.uploadedAt));
}
