import axios from 'axios';

const API_URL = 'http://localhost:8000/api';
const API_BASE = 'http://localhost:8000';

export const fetchTechnicalGraph = async () => {
  const response = await axios.get(`${API_URL}/graph/technical`);
  return response.data;
};

export const fetchKnowledgeGraph = async () => {
  const response = await axios.get(`${API_URL}/graph/knowledge`);
  return response.data;
};

export const fetchSetupSources = async () => {
  const response = await axios.get(`${API_URL}/setup/sources`);
  return response.data;
};

export const fetchSetupContributors = async () => {
  const response = await axios.get(`${API_URL}/setup/contributors`);
  return response.data;
};

export const fetchSetupCapabilities = async () => {
  const response = await axios.get(`${API_URL}/setup/capabilities`);
  return response.data;
};

export const collectSource = async (sourceId, payload = {}) => {
  const response = await axios.post(`${API_URL}/setup/sources/${sourceId}/collect`, payload);
  return response.data;
};

export const resetSetupData = async () => {
  const response = await axios.post(`${API_URL}/setup/reset`);
  return response.data;
};

// --- Capability Gap RAG (Confluence knowledge transfer) ---

export const getRagConfluenceStatus = async () => {
  const response = await axios.get(`${API_URL}/rag/confluence/status`);
  return response.data;
};

export const getRagConfluenceSettings = async () => {
  const response = await axios.get(`${API_URL}/rag/confluence/settings`);
  return response.data;
};

export const saveRagConfluenceSettings = async (payload) => {
  const response = await axios.post(`${API_URL}/rag/confluence/settings`, payload);
  return response.data;
};

export const syncRagConfluence = async (force = false) => {
  const response = await axios.post(`${API_URL}/rag/confluence/sync`, { force });
  return response.data;
};

export const generateTransferPackage = async (employeeIds, formats = ['md', 'pdf', 'docx']) => {
  const response = await axios.post(`${API_URL}/rag/transfer-package`, {
    employee_ids: employeeIds,
    formats
  });
  return response.data;
};

export const listPackages = async () => {
  const response = await axios.get(`${API_URL}/rag/packages`);
  return response.data;
};

// download_base looks like /api/rag/transfer-package/{slug}/download.
// Kept for scripts and bookmarks. The dashboard uses downloadTransferPackage
// instead: a link like this points at a file on the server, and 404s the
// moment that file is gone -- data/rag/packages/ is gitignored, so a git
// clean, a branch switch or a fresh clone removes it while the page is still
// holding the old slug.
export const packageDownloadUrl = (base, format) =>
  `${API_BASE}${base}?format=${encodeURIComponent(format)}`;

// Asks the server to build the package and hand back the bytes, then saves
// them from memory. Depends on nothing but the database, so it cannot fail
// because of a file that has since been cleaned up.
export const downloadTransferPackage = async (employeeIds, format) => {
  const response = await axios.post(
    `${API_URL}/rag/transfer-package/download`,
    { employee_ids: employeeIds, format },
    { responseType: 'blob' }
  );

  const disposition = response.headers['content-disposition'] || '';
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const filename = match
    ? decodeURIComponent(match[1])
    : `transfer-package-${employeeIds.join('-')}.${format}`;

  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);

  return filename;
};

// --- PagerDuty --------------------------------------------------------------

// Posts to /api/ingestion/pagerduty, which fetches incidents for the service in
// the URL and writes the raw + normalized datasets. This is a different shape
// from the other sources: they go through /api/setup/sources/{id}/collect, but
// PagerDuty has its own ingestion route, and the Setup drawer was never wired
// to it -- it posted to the generic collect endpoint, which has no PagerDuty
// branch and so returned a success that did nothing.
export const ingestPagerDuty = async (pagerdutyUrl, apiToken) => {
  const response = await axios.post(`${API_URL}/ingestion/pagerduty`, {
    pagerduty_url: pagerdutyUrl,
    api_token: apiToken
  });
  return response.data;
};
