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
  
  const reloadGraphs = async () => {
    try {
      const [tech, know] = await Promise.all([
        fetchTechnicalGraph(),
        fetchKnowledgeGraph()
      ]);
      setTechGraphData(tech);
      setKnowledgeGraphData(know);
      // Keep "All Teammates" as default (do not auto-select first employee)
    } catch (err) {
      console.error("Failed loading graph data:", err);
    }
  };

  useEffect(() => {
    reloadGraphs();
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
    const activeData = activeTab === 'dashboard' ? knowledgeGraphData : techGraphData;
    if (!activeData || !activeData.nodes) return null;

    // Determine the focus ID (either clicked node or selected dropdown filter)
    let focusId = null;
    if (selectedNode) {
      focusId = selectedNode.id;
    } else if (selectedEmployeeFilter) {
      focusId = selectedEmployeeFilter;
    }

    // Default: Show full graph with all teammates and modules
    if (!focusId) {
      return activeData;
    }

    // Match focus node in current graph dataset
    const matchedNode = activeData.nodes.find(n => 
      n.id === focusId || 
      n.id === `employee:${focusId}` || 
      n.id === `capability:${focusId}` || 
      n.id === `component:${focusId}` ||
      n.data?.capability_id === focusId ||
      n.data?.employee_id === focusId
    );

    if (!matchedNode) {
      return activeData;
    }

    const actualFocusId = matchedNode.id;
    const connectedNodeIds = new Set([actualFocusId]);
    const relevantLinks = [];

    activeData.links.forEach(l => {
      const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
      const targetId = typeof l.target === 'object' ? l.target.id : l.target;

      if (sourceId === actualFocusId || targetId === actualFocusId) {
        relevantLinks.push(l);
        connectedNodeIds.add(sourceId);
        connectedNodeIds.add(targetId);
      }
    });

    const relevantNodes = activeData.nodes.filter(n => connectedNodeIds.has(n.id));

    return {
      ...activeData,
      nodes: relevantNodes,
      links: relevantLinks
    };
  };

  const filteredGraphData = getFilteredGraphData();
  const selectedEmpObj = employees.find(e => e.id === selectedEmployeeFilter || e.id === `employee:${selectedEmployeeFilter}`);

  const handleCapabilityCardClick = (cap) => {
    const capNodeId = cap.id.startsWith('capability:') ? cap.id : `capability:${cap.id}`;
    if (selectedNode && selectedNode.id === capNodeId) {
      // Toggle off
      setSelectedNode(null);
    } else {
      const nodeObj = knowledgeGraphData?.nodes.find(n => n.id === capNodeId || n.id === cap.id) || {
        id: capNodeId,
        type: 'CAPABILITY',
        label: cap.label || cap.name,
        data: cap.data || { capability_id: cap.id, name: cap.label }
      };
      setSelectedNode(nodeObj);
      setSelectedEmployeeFilter('');
    }
  };

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
            
            {activeTab === 'setup' && (
              <SetupPanel 
                onDataIngested={reloadGraphs} 
                onGoToDashboard={() => setActiveTab('dashboard')} 
              />
            )}
            
            {activeTab === 'dashboard' && (
              <div id="tab-dashboard">
                <div className="page-title">Payment Service</div>
                <div className="page-meta mono">Team Size: {employees.length} Members &nbsp;·&nbsp; <span>Active Capabilities: {capabilities.length} &nbsp;·&nbsp; Live Telemetry Graph</span></div>

                <div className="cap-grid">
                  {capabilities.map(c => {
                    const coveredBy = capabilityCoverage[c.id] || [];
                    const isMissingSelected = simulationState?.type === 'knowledge' && simulationState.unavailableEmployees.includes(selectedEmployeeFilter) && coveredBy.includes(selectedEmpObj?.label);
                    
                    let status = coveredBy.length === 0 ? "Uncovered" : "Maintained";
                    let remaining = coveredBy;
                    if (isMissingSelected) {
                      remaining = coveredBy.filter(n => n !== selectedEmpObj?.label);
                      status = remaining.length === 0 ? "Lost" : "Degraded";
                    }

                    const isCardSelected = selectedNode?.id === c.id || selectedNode?.id === `capability:${c.id}` || selectedNode?.data?.capability_id === c.id;

                    return (
                      <div 
                        className={`cap-card ${isCardSelected ? 'selected' : ''}`} 
                        key={c.id}
                        onClick={() => handleCapabilityCardClick(c)}
                        title="Click to isolate module and view connected contributors"
                      >
                        <div className="cap-head">
                          <span className="cap-name">{c.label}</span>
                          <span className={`status-pill status-${status.toLowerCase()}`}>{status}</span>
                        </div>
                        <div className="cap-covered">Covered by: <b>{remaining.length ? remaining.join(", ") : (coveredBy.length === 0 ? "No telemetry ingested" : "none remaining")}</b></div>
                      </div>
                    );
                  })}
                </div>

                <div className="sim-panel">
                  <div className="sim-title">
                    <div className="sim-title-left">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M9 2v6l-5 10a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3L15 8V2"/><line x1="9" y1="2" x2="15" y2="2"/><line x1="6" y1="15" x2="18" y2="15"/></svg>
                      Filter by Teammate / Simulate Unavailability
                    </div>
                    {simulationState && (
                      <button className="reset-sim-btn" onClick={() => setSimulationState(null)}>RESET SIMULATION</button>
                    )}
                  </div>
                  <div className="sim-desc">Select a teammate to isolate their capability connections, or click any module above to view its direct contributors.</div>
                  <div className="sim-row">
                    <div className="sim-field">
                      <div className="sim-label mono">TEAMMATE SELECTION</div>
                      <select 
                        value={selectedEmployeeFilter} 
                        onChange={e => { 
                          setSelectedEmployeeFilter(e.target.value); 
                          setSelectedNode(null);
                          setSimulationState(null); 
                        }}
                      >
                        <option value="">All Teammates (Full Graph)</option>
                        {employees.map(e => <option key={e.id} value={e.id}>{e.label}</option>)}
                      </select>
                    </div>
                  </div>
                </div>

                <div className="graph-section">
                  <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'10px'}}>
                    <div>
                      <div className="graph-title">
                        Human graph — {selectedNode ? `${selectedNode.label} (${selectedNode.type === 'CAPABILITY' ? 'Capability' : selectedNode.type})` : (selectedEmpObj?.label || 'All Teammates')}
                      </div>
                      <div className="graph-sub">
                        {selectedNode ? `Showing only ${selectedNode.label} and connected contributors.` : (selectedEmpObj ? `Showing only ${selectedEmpObj.label} and verified capability modules.` : "Full team capability network and live telemetry linkages.")}
                      </div>
                    </div>
                    {(selectedNode || selectedEmployeeFilter) && (
                      <button 
                        className="clear-filter-btn mono" 
                        onClick={() => { setSelectedNode(null); setSelectedEmployeeFilter(''); }}
                        style={{
                          background:'#1a1a1d',
                          border:'1px solid #38383e',
                          color:'#4ade80',
                          padding:'6px 12px',
                          borderRadius:'6px',
                          cursor:'pointer',
                          fontSize:'11px',
                          fontWeight:'600',
                          letterSpacing:'0.3px',
                          transition:'all 0.15s ease'
                        }}
                      >
                        ✕ Show All Teammates
                      </button>
                    )}
                  </div>

                  <div className="legend">
                    <span className="legend-item"><span className="dot" style={{background:'#5b9cf2'}}></span>engineer</span>
                    <span className="legend-item"><span className="dot" style={{background:'#4ade80'}}></span>capability (skill)</span>
                    <span className="legend-item"><span className="line-sample" style={{borderColor:'#4ade80'}}></span>has evidence for</span>
                  </div>
                  <div className="graph-canvas-container">
                    {filteredGraphData ? (
                      <GraphCanvas 
                        data={{...filteredGraphData, graphType: 'knowledge'}} 
                        selectedNodeId={selectedNode?.id || selectedEmployeeFilter} 
                        onNodeClick={(node) => {
                          setSelectedNode(node);
                          if (node && node.type === 'EMPLOYEE') {
                            setSelectedEmployeeFilter(node.id);
                          }
                        }}
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
                
                <div style={{display:'flex', alignItems:'center', justifyContent:'space-between', margin:'10px 0'}}>
                  <div className="legend" style={{marginBottom:0}}>
                    <span className="legend-item"><span className="dot" style={{background:'#5b9cf2'}}></span>system</span>
                    <span className="legend-item"><span className="dot" style={{background:'#f2b84b'}}></span>component</span>
                    <span className="legend-item"><span className="line-sample" style={{borderColor:'#68675f'}}></span>requires</span>
                  </div>
                  {selectedNode && (
                    <button 
                      className="clear-filter-btn mono" 
                      onClick={() => setSelectedNode(null)}
                      style={{
                        background:'#1a1a1d',
                        border:'1px solid #38383e',
                        color:'#5b9cf2',
                        padding:'5px 12px',
                        borderRadius:'6px',
                        cursor:'pointer',
                        fontSize:'11px',
                        fontWeight:'600'
                      }}
                    >
                      ✕ Show Full System
                    </button>
                  )}
                </div>

                <div className="graph-canvas-container" style={{height: 600}}>
                  {filteredGraphData ? (
                    <GraphCanvas 
                      data={{...filteredGraphData, graphType: 'technical'}} 
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
