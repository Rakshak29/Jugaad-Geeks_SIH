import axios from 'axios';

const API_URL = 'http://localhost:8000/api';

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
export const collectSource = async (sourceId) => { const response = await axios.post(`${API_URL}/setup/sources/${sourceId}/collect`); return response.data; };
