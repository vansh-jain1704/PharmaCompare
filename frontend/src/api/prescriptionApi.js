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

export function downloadSmartReport(id) {
  return axiosClient.get(`/api/prescriptions/${id}/report`, { responseType: "blob" });
}

export function explainMedicine(medicineId) {
  return axiosClient.get(`/api/medicines/${medicineId}/explain`);
}

export function searchMedicines(query) {
  return axiosClient.get("/api/medicines/search", { params: { q: query } });
}

export function correctDetectedMedicine(prescriptionId, pmId, medicineId) {
  return axiosClient.patch(`/api/prescriptions/${prescriptionId}/medicines/${pmId}`, {
    medicine_id: medicineId,
  });
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
