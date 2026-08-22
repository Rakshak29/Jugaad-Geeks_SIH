import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

export const fetchTechnicalGraph = async () => {
  const response = await axios.get(`${API_URL}/graph/technical`);
  return response.data;
};

export const fetchKnowledgeGraph = async () => {
  const response = await axios.get(`${API_URL}/graph/knowledge`);
  return response.data;
};
