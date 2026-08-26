import React, { useState, useEffect, useMemo } from 'react';
import { fetchTechnicalGraph, fetchKnowledgeGraph } from './services/api';
import GraphCanvas from './components/GraphCanvas';
import DetailsPanel from './components/DetailsPanel';
import SetupPanel from './components/SetupPanel';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('setup');
  const [techGraphData, setTechGraphData] = useState(null);
  const [knowledgeGraphData, setKnowledgeGraphData] = useState(null);
  
  const [selectedNode, setSelectedNode] = useState(null);
  const [simulationState, setSimulationState] = useState(null);
  const [selectedEmployeeFilter, setSelectedEmployeeFilter] = useState('');
  
  useEffect(() => {
    fetchTechnicalGraph().then(setTechGraphData).catch(console.error);
    fetchKnowledgeGraph().then(data => {
      setKnowledgeGraphData(data);
      const emps = data.nodes.filter(n => n.type === 'EMPLOYEE');
      if (emps.length > 0) setSelectedEmployeeFilter(emps[0].id);
    }).catch(console.error);
  }, []);

  const employees = useMemo(() => {
    if (!knowledgeGraphData) return [];
    return knowledgeGraphData.nodes.filter(n => n.type === 'EMPLOYEE');
  }, [knowledgeGraphData]);

  const capabilities = useMemo(() => {
    if (!knowledgeGraphData) return [];
    return knowledgeGraphData.nodes.filter(n => n.type === 'CAPABILITY');
  }, [knowledgeGraphData]);

  const capabilityCoverage = useMemo(() => {
    if (!knowledgeGraphData) return {};
    const map = {};
    capabilities.forEach(c => map[c.id] = []);
    knowledgeGraphData.links.forEach(l => {
      if (l.type === 'HAS_CAPABILITY') {
        const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
        const targetId = typeof l.target === 'object' ? l.target.id : l.target;
        if (map[targetId]) {
          const emp = knowledgeGraphData.nodes.find(n => n.id === sourceId);
          if (emp) map[targetId].push(emp.label);
        }
      }
    });
    return map;
  }, [knowledgeGraphData, capabilities]);

  const getFilteredGraphData = () => {
    if (!knowledgeGraphData || !selectedEmployeeFilter) return knowledgeGraphData;

    const nodes = [];
    const links = [];
    const nodeIds = new Set();

    const empNode = knowledgeGraphData.nodes.find(n => n.id === selectedEmployeeFilter);
    if (empNode) {
      nodes.push(empNode);
      nodeIds.add(empNode.id);
    }

    knowledgeGraphData.links.forEach(l => {
      const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
      const targetId = typeof l.target === 'object' ? l.target.id : l.target;

      if (sourceId === selectedEmployeeFilter || targetId === selectedEmployeeFilter) {
        links.push(l);
        const connectedId = sourceId === selectedEmployeeFilter ? targetId : sourceId;
        if (!nodeIds.has(connectedId)) {
          const n = knowledgeGraphData.nodes.find(n => n.id === connectedId);
          if (n) {
            nodes.push(n);
            nodeIds.add(connectedId);
          }
        }
      }
    });

    return { ...knowledgeGraphData, nodes, links };
  };

  const filteredGraphData = getFilteredGraphData();
  const selectedEmpObj = employees.find(e => e.id === selectedEmployeeFilter);

  return (
    <div className="app-container">
      <div className="chrome">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><rect x="3" y="4" width="18" height="14" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/></svg>
        ECE | Payment Service Dashboard
      </div>

      <div className="navbar">
        <div className="navbar-left">
          <div className="brand">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3 L20 6 V11 C20 16 16.5 19.5 12 21 C7.5 19.5 4 16 4 11 V6 Z"/></svg>
            ECE
          </div>
          <div className="navlinks">
            <span className={`navlink ${activeTab === 'setup' ? 'active' : ''}`} onClick={() => setActiveTab('setup')}>Setup Pipeline</span>
            <span className={`navlink ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>Dashboard</span>
            <span className={`navlink ${activeTab === 'simulation' ? 'active' : ''}`} onClick={() => setActiveTab('simulation')}>Simulation</span>
          </div>
        </div>
        <div className="navbar-right">
          <div className="service-badge">Service: Payment Service</div>
          <svg className="icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/></svg>
          <svg className="icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 2-3 4"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        </div>
      </div>

      <div className="app-main">
        <div className="shell-scroll">
          <div className="shell">
            
            {activeTab === 'setup' && <SetupPanel />}
            
            {activeTab === 'dashboard' && (
              <div id="tab-dashboard">
                <div className="page-title">Payment Service</div>
                <div className="page-meta mono">Team Size: {employees.length} Members &nbsp;·&nbsp; <span>Active Capabilities: {capabilities.length} &nbsp;·&nbsp; Last Scan: 2026-08-21 09:14 UTC</span></div>

                <div className="cap-grid">
                  {capabilities.map(c => {
                    const coveredBy = capabilityCoverage[c.id] || [];
                    const isMissingSelected = simulationState?.type === 'knowledge' && simulationState.unavailableEmployees.includes(selectedEmployeeFilter) && coveredBy.includes(selectedEmpObj?.label);
                    
                    let status = "Maintained";
                    let remaining = coveredBy;
                    if (isMissingSelected) {
                      remaining = coveredBy.filter(n => n !== selectedEmpObj?.label);
                      status = remaining.length === 0 ? "Lost" : "Degraded";
                    }

                    return (
                      <div className="cap-card" key={c.id}>
                        <div className="cap-head">
                          <span className="cap-name">{c.label}</span>
                          <span className={`status-pill status-${status.toLowerCase()}`}>{status}</span>
                        </div>
                        <div className="cap-covered">Covered by: <b>{remaining.length ? remaining.join(", ") : "none remaining"}</b></div>
                      </div>
                    );
                  })}
                </div>

                <div className="sim-panel">
                  <div className="sim-title">
                    <div className="sim-title-left">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M9 2v6l-5 10a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3L15 8V2"/><line x1="9" y1="2" x2="15" y2="2"/><line x1="6" y1="15" x2="18" y2="15"/></svg>
                      Simulate unavailability
                    </div>
                    {simulationState && (
                      <button className="reset-sim-btn" onClick={() => setSimulationState(null)}>RESET SIMULATION</button>
                    )}
                  </div>
                  <div className="sim-desc">Select an engineer to model coverage impact if they are unavailable. Click "Mark Unavailable" in their Intelligence Panel.</div>
                  <div className="sim-row">
                    <div className="sim-field">
                      <div className="sim-label mono">TARGET ENGINEER</div>
                      <select value={selectedEmployeeFilter} onChange={e => { setSelectedEmployeeFilter(e.target.value); setSimulationState(null); }}>
                        <option value="">All Employees (Full Graph)</option>
                        {employees.map(e => <option key={e.id} value={e.id}>{e.label}</option>)}
                      </select>
                    </div>
                  </div>
                </div>

                <div className="graph-section">
                  <div className="graph-title">Human graph — {selectedEmpObj?.label || 'All'}</div>
                  <div className="graph-sub">What this engineer is capable of, and what they're currently working on.</div>
                  <div className="legend">
                    <span className="legend-item"><span className="dot" style={{background:'#5b9cf2'}}></span>engineer</span>
                    <span className="legend-item"><span className="dot" style={{background:'#4ade80'}}></span>capability (skill)</span>
                    <span className="legend-item"><span className="line-sample" style={{borderColor:'#68675f'}}></span>has evidence for</span>
                  </div>
                  <div className="graph-canvas-container">
                    {filteredGraphData ? (
                      <GraphCanvas 
                        data={{...filteredGraphData, graphType: 'knowledge'}} 
                        selectedNodeId={selectedNode?.id} 
                        onNodeClick={setSelectedNode}
                        simulationState={simulationState}
                      />
                    ) : (
                      <div style={{position:'relative', height:'100%', display:'flex', alignItems:'center', justifyContent:'center', color:'#888'}}>Loading Graph...</div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'simulation' && (
              <div id="tab-simulation">
                <div className="page-title">Technical graph</div>
                <div className="page-meta mono"><span>Project structure — how features decompose into their underlying needs</span></div>
                <div className="legend">
                  <span className="legend-item"><span className="dot" style={{background:'#5b9cf2'}}></span>system</span>
                  <span className="legend-item"><span className="dot" style={{background:'#f2b84b'}}></span>component</span>
                  <span className="legend-item"><span className="line-sample" style={{borderColor:'#68675f'}}></span>requires</span>
                </div>
                <div className="graph-canvas-container" style={{height: 600}}>
                  {techGraphData ? (
                    <GraphCanvas 
                      data={{...techGraphData, graphType: 'technical'}} 
                      selectedNodeId={selectedNode?.id} 
                      onNodeClick={setSelectedNode}
                      simulationState={simulationState}
                    />
                  ) : (
                    <div style={{position:'relative', height:'100%', display:'flex', alignItems:'center', justifyContent:'center', color:'#888'}}>Loading Graph...</div>
                  )}
                </div>
              </div>
            )}

          </div>
        </div>

        {selectedNode && (
          <DetailsPanel 
            selectedNode={selectedNode} 
            graphData={activeTab === 'dashboard' ? knowledgeGraphData : techGraphData}
            onClose={() => setSelectedNode(null)}
            simulationState={simulationState}
            setSimulationState={setSimulationState}
          />
        )}

      </div>
    </div>
  );
}

export default App;
