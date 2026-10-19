import axiosClient from "./axiosClient";

function hasAnySymptoms(symptoms) {
  if (!symptoms) return false;
  const hasSub = Object.values(symptoms.subSymptoms || {}).some((list) => list.length > 0);
  const hasOther = (symptoms.otherSymptoms || []).length > 0;
  return hasSub || hasOther;
}

export function uploadPrescription(file, prescriptionName, symptoms, prescriptionType) {
  const formData = new FormData();
  formData.append("file", file);
  if (prescriptionName) {
    formData.append("prescription_name", prescriptionName);
  }
  if (hasAnySymptoms(symptoms)) {
    formData.append("symptoms", JSON.stringify(symptoms));
  }
  if (prescriptionType) {
    formData.append("prescription_type", prescriptionType);
  }
  return axiosClient.post("/api/prescriptions/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function listPrescriptions() {
  return axiosClient.get("/api/prescriptions");
}

export function getPrescription(id) {
  return axiosClient.get(`/api/prescriptions/${id}`);
}

export function deletePrescription(id) {
  return axiosClient.delete(`/api/prescriptions/${id}`);
}

// The plain-language summary of one analysis (written by Gemini when it passes the server's checks, otherwise by PharmaCompare).
export function getReportSummary(id) {
  return axiosClient.get(`/api/prescriptions/${id}/summary`);
}

export function downloadSmartReport(id) {
  return axiosClient.get(`/api/prescriptions/${id}/report`, { responseType: "blob" });
}

export function explainMedicine(medicineId) {
  return axiosClient.get(`/api/medicines/${medicineId}/explain`);
}

// What pharmacies have REPORTED for one medicine (price, stock, when, which feed). Never the dataset's reference price.
export function getMedicineOffers(medicineId) {
  return axiosClient.get(`/api/medicines/${medicineId}/offers`);
}

// Reads a photo of a medicine pack and returns possible products for its text. Never a confirmation; the photo is not kept.
export function scanMedicine(file) {
  const formData = new FormData();
  formData.append("file", file);
  return axiosClient.post("/api/medicines/scan", formData, { headers: { "Content-Type": "multipart/form-data" } });
}

// Medical stores and Jan Aushadhi Kendras near a (rounded) position. POST, so the position never appears in a URL or a server access log.
export function findNearbyStores({ lat, lon, radiusKm, scope }) {
  return axiosClient.post("/api/stores/nearby", { lat, lon, radius_km: radiusKm, scope });
}

// Turns a typed place name or PIN code into positions. Only called when the person submits the form.
export function findPlace(query) {
  return axiosClient.post("/api/stores/geocode", { q: query });
}

export function searchMedicines(query) {
  return axiosClient.get("/api/medicines/search", { params: { q: query } });
}

// `acknowledgeWarnings` is only ever true after the person has been shown the backend's conflict warnings
// (a 409 from this same call) and chose to go ahead; it is never sent on the first attempt.
export function correctDetectedMedicine(prescriptionId, pmId, medicineId, acknowledgeWarnings = false) {
  return axiosClient.patch(`/api/prescriptions/${prescriptionId}/medicines/${pmId}`, {
    medicine_id: medicineId,
    ...(acknowledgeWarnings ? { acknowledge_warnings: true } : {}),
  });
}

// "None of these": the person reviewed the line and says it is not a medicine we can identify.
export function markMedicineUnmatched(prescriptionId, pmId) {
  return axiosClient.post(`/api/prescriptions/${prescriptionId}/medicines/${pmId}/unmatched`);
}

// The person types in a medicine the dataset cannot identify (name, strength, form, schedule, duration). Saved as "entered by you":
// never matched to a product, never priced or safety-checked.
export function enterMedicineDetails(prescriptionId, pmId, details) {
  return axiosClient.post(`/api/prescriptions/${prescriptionId}/medicines/${pmId}/details`, details);
}

// Every verification decision recorded for a prescription (what was decided, when, and what the person saw).
export function getVerificationLog(prescriptionId) {
  return axiosClient.get(`/api/prescriptions/${prescriptionId}/verification-log`);
}

export function addMedicineManually(prescriptionId, medicineId, dosageText) {
  return axiosClient.post(`/api/prescriptions/${prescriptionId}/medicines`, {
    medicine_id: medicineId,
    dosage_text: dosageText || undefined,
  });
}

export function removeDetectedMedicine(prescriptionId, pmId) {
  return axiosClient.delete(`/api/prescriptions/${prescriptionId}/medicines/${pmId}`);
}
