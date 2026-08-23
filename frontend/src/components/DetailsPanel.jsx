import React, { useState } from 'react';
import { calculateEvidenceBand, getCoverageStatus, findMinimumCoverageTeam } from '../services/coverageEngine';
import './DetailsPanel.css';

const DetailsPanel = ({ selectedNode, graphData, onClose, simulationState, setSimulationState }) => {
  const [selectedCapability, setSelectedCapability] = useState(null);

  if (!selectedNode) return null;

  const data = selectedNode.data || {};
  const isTechnical = selectedNode.type === 'SYSTEM' || selectedNode.type === 'COMPONENT';
  const isKnowledge = selectedNode.type === 'EMPLOYEE' || selectedNode.type === 'CAPABILITY' || selectedNode.type === 'EVIDENCE';

  const incoming = [];
  const outgoing = [];
  graphData.links.forEach(l => {
    const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
    const targetId = typeof l.target === 'object' ? l.target.id : l.target;
    
    if (sourceId === selectedNode.id) {
      outgoing.push({ edge: l.type, node: graphData.nodes.find(n => n.id === targetId) });
    }
    if (targetId === selectedNode.id) {
      incoming.push({ edge: l.type, node: graphData.nodes.find(n => n.id === sourceId) });
    }
  });

  const simulateFailure = () => {
    const failedNodes = new Set([selectedNode.id]);
    const affectedNodes = new Set();
    const explanations = {};

    const queue = [selectedNode.id];
    while (queue.length > 0) {
      const current = queue.shift();
      const currentLabel = graphData.nodes.find(n => n.id === current).label;

      const dependents = graphData.links.filter(l => {
        const targetId = typeof l.target === 'object' ? l.target.id : l.target;
        return targetId === current && l.type === 'DEPENDS_ON';
      });

      for (const edge of dependents) {
        const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
        if (!failedNodes.has(sourceId) && !affectedNodes.has(sourceId)) {
          affectedNodes.add(sourceId);
          explanations[sourceId] = `${graphData.nodes.find(n => n.id === sourceId).label} depends on ${currentLabel}.`;
          queue.push(sourceId);
        }
      }
    }

    const totalTechnical = graphData.nodes.filter(n => n.type === 'SYSTEM' || n.type === 'COMPONENT').length;
    const blastRadius = (((affectedNodes.size + failedNodes.size) / totalTechnical) * 100).toFixed(1);

    setSimulationState({
      type: 'technical',
      failedNodes: Array.from(failedNodes),
      affectedNodes: Array.from(affectedNodes),
      explanations,
      blastRadius,
      totalTechnical
    });
  };

  const getCapabilityEvidence = (capId, excludeEmployeeId = null) => {
    const records = [];
    graphData.links.forEach(l => {
      const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
      const targetId = typeof l.target === 'object' ? l.target.id : l.target;
      
      if (targetId === capId && l.type === 'HAS_CAPABILITY') {
        if (sourceId !== excludeEmployeeId) {
          records.push({
            employeeId: sourceId,
            band: calculateEvidenceBand(l.data.evidence_strength, l.data.evidence_recency)
          });
        }
      }
    });

    const bandOrder = { 'HIGH': 4, 'MODERATE': 3, 'LOW': 2, 'NONE': 1 };
    let maxBand = 'NONE';
    records.forEach(r => {
      if (bandOrder[r.band] > bandOrder[maxBand]) maxBand = r.band;
    });

    return { maxBand, records };
  };

  const markUnavailable = () => {
    const unavailableId = selectedNode.id;
    
    // 1. Find all capabilities this employee contributed to
    const employeeCapabilities = new Set();
    const ecData = [];
    
    graphData.links.forEach(l => {
      const sourceId = typeof l.source === 'object' ? l.source.id : l.source;
      const targetId = typeof l.target === 'object' ? l.target.id : l.target;
      
      if (l.type === 'HAS_CAPABILITY') {
        if (sourceId === unavailableId) {
          employeeCapabilities.add(targetId);
        }
        ecData.push({
          employee_id: sourceId,
          capability_id: targetId,
          evidence_strength: l.data.evidence_strength,
          evidence_recency: l.data.evidence_recency
        });
      }
    });

    // 2. Before/After Coverage Analysis
    const capabilityAnalysis = [];
    const gaps = [];
    
    employeeCapabilities.forEach(capId => {
      const before = getCapabilityEvidence(capId).maxBand;
      const after = getCapabilityEvidence(capId, unavailableId).maxBand;
      const status = getCoverageStatus(before, after);
      
      capabilityAnalysis.push({
        capability_id: capId,
        capability_label: graphData.nodes.find(n => n.id === capId).label,
        before,
        after,
        status
      });

      if (status === 'Lost' || status === 'Degraded') {
        gaps.push(capId);
      }
    });

    // 3. Exact Optimizer for Coverage Team
    const availableEmployees = graphData.nodes
      .filter(n => n.type === 'EMPLOYEE' && n.id !== unavailableId)
      .map(n => ({ employee_id: n.id, name: n.label, team_id: n.data.team_id }));
    
    const coveragePlan = findMinimumCoverageTeam(gaps, availableEmployees, ecData);

    // 4. Evidence-Ranked Transfer Package
    const transferActions = coveragePlan.residualGaps.map(gapId => {
      const capName = graphData.nodes.find(n => n.id === gapId).label;
      return `Review ${selectedNode.label}'s previous incident records and runbooks for ${capName}`;
    });

    setSimulationState({
      type: 'knowledge',
      unavailableEmployees: [unavailableId],
      capabilityAnalysis,
      coveragePlan,
      transferActions,
      gaps,
      covered: [] // Not used in this version, handled by analysis
    });
  };

  const getStatusDisplay = () => {
    if (simulationState) {
      if (simulationState.type === 'technical') {
        if (simulationState.failedNodes.includes(selectedNode.id)) return <div className="status red">🔴 UNAVAILABLE</div>;
        if (simulationState.affectedNodes.includes(selectedNode.id)) return <div className="status orange">🟠 AFFECTED</div>;
      } else if (simulationState.type === 'knowledge') {
        if (simulationState.unavailableEmployees.includes(selectedNode.id)) return <div className="status red">🔴 UNAVAILABLE</div>;
        if (simulationState.gaps.includes(selectedNode.id)) return <div className="status red">🚨 CAPABILITY GAP</div>;
      }
    }
    return <div className="status green">🟢 Operational / Available</div>;
  };

  return (
    <div className="details-panel">
      <div className="details-header">
        <div>
          <h3>{selectedNode.type}</h3>
          <h2>{selectedNode.label}</h2>
        </div>
        <button className="close-btn" onClick={() => {
          setSelectedCapability(null);
          onClose();
        }}>×</button>
      </div>
      
      <div className="details-content">
        
        <div className="card">
          <h4>STATUS</h4>
          {getStatusDisplay()}
        </div>

        {simulationState && simulationState.type === 'technical' && simulationState.failedNodes.includes(selectedNode.id) && (
          <div className="card impact-card">
            <h4>TECHNICAL IMPACT</h4>
            <p><strong>{simulationState.affectedNodes.length}</strong> directly/indirectly affected nodes.</p>
            <p><strong>Blast radius: {simulationState.blastRadius}%</strong> ({simulationState.affectedNodes.length + simulationState.failedNodes.length} of {simulationState.totalTechnical})</p>
          </div>
        )}

        {simulationState && simulationState.type === 'technical' && simulationState.affectedNodes.includes(selectedNode.id) && (
          <div className="card impact-card">
            <h4>WHY IS THIS AFFECTED?</h4>
            <p>{simulationState.explanations[selectedNode.id]}</p>
          </div>
        )}

        {simulationState && simulationState.type === 'knowledge' && simulationState.unavailableEmployees.includes(selectedNode.id) && (
          <div className="card impact-card">
            <h4>COVERAGE ANALYSIS</h4>
            <table className="analysis-table">
              <thead>
                <tr>
                  <th>Capability</th>
                  <th>Before</th>
                  <th>After</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {simulationState.capabilityAnalysis.map(cap => (
                  <tr key={cap.capability_id} onClick={() => setSelectedCapability(cap.capability_id)} style={{cursor:'pointer'}}>
                    <td>{cap.capability_label}</td>
                    <td>{cap.before}</td>
                    <td>{cap.after}</td>
                    <td className={cap.status === 'Lost' ? 'red-text' : cap.status === 'Degraded' ? 'orange-text' : 'green-text'}>{cap.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted" style={{marginTop:10}}>* Click a capability to see lost evidence analysis.</p>

            {selectedCapability && (() => {
              const capAnalysis = simulationState.capabilityAnalysis.find(c => c.capability_id === selectedCapability);
              const unavailableId = simulationState.unavailableEmployees[0];

              // Lost: the unavailable employee's own link for this capability
              const lostLink = graphData.links.find(l => {
                const src = typeof l.source === 'object' ? l.source.id : l.source;
                const tgt = typeof l.target === 'object' ? l.target.id : l.target;
                return src === unavailableId && tgt === selectedCapability && l.type === 'HAS_CAPABILITY';
              });
              const lostScore = lostLink ? lostLink.data?.evidence_strength : null;

              // Remaining: all OTHER employees who have a link to this capability
              const remainingLinks = graphData.links.filter(l => {
                const src = typeof l.source === 'object' ? l.source.id : l.source;
                const tgt = typeof l.target === 'object' ? l.target.id : l.target;
                return src !== unavailableId && tgt === selectedCapability && l.type === 'HAS_CAPABILITY';
              }).map(l => {
                const src = typeof l.source === 'object' ? l.source.id : l.source;
                const emp = graphData.nodes.find(n => n.id === src);
                const score = l.data?.evidence_strength ?? 0;
                const band = score >= 0.75 ? 'HIGH' : score >= 0.45 ? 'MODERATE' : score >= 0.20 ? 'LOW' : 'NONE';
                return { name: emp?.label ?? src, score, band };
              }).sort((a, b) => b.score - a.score);

              const bandColor = b => b === 'HIGH' ? '#4caf50' : b === 'MODERATE' ? '#ff9800' : b === 'LOW' ? '#2196f3' : '#888';

              return (
                <div className="evidence-lost-box">
                  <h4>EVIDENCE ANALYSIS — {graphData.nodes.find(n => n.id === selectedCapability)?.label}</h4>

                  <div style={{marginBottom: 10}}>
                    <strong style={{color: '#f44336'}}>Lost Evidence</strong>
                    <div style={{marginTop: 4, paddingLeft: 8, borderLeft: '2px solid #f44336'}}>
                      <span style={{color: '#eee'}}>{selectedNode.label}</span>
                      {lostScore !== null && (
                        <span style={{marginLeft: 8, color: '#aaa', fontSize: 12}}>
                          score: <strong style={{color: '#eee'}}>{lostScore.toFixed(4)}</strong>
                          {' '}[<span style={{color: bandColor(capAnalysis.before)}}>{capAnalysis.before}</span>]
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <strong style={{color: '#4caf50'}}>Remaining Evidence</strong>
                    {remainingLinks.length === 0 ? (
                      <p style={{color: '#888', marginTop: 4, fontSize: 13}}>No remaining coverage.</p>
                    ) : (
                      <div style={{marginTop: 4, paddingLeft: 8, borderLeft: '2px solid #4caf50'}}>
                        {remainingLinks.map((r, i) => (
                          <div key={i} style={{display: 'flex', justifyContent: 'space-between', padding: '3px 0', fontSize: 13}}>
                            <span style={{color: '#eee'}}>{r.name}</span>
                            <span style={{color: '#aaa'}}>
                              score: <strong style={{color: '#eee'}}>{r.score.toFixed(4)}</strong>
                              {' '}[<span style={{color: bandColor(r.band)}}>{r.band}</span>]
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {simulationState && simulationState.type === 'knowledge' && simulationState.unavailableEmployees.includes(selectedNode.id) && (
          <div className="card">
            <h4>MINIMUM COVERAGE TEAM</h4>
            {simulationState.coveragePlan.team.length === 0 ? (
              <p className="muted">No alternative team can be formed.</p>
            ) : (
              <ul className="team-list">
                {simulationState.coveragePlan.team.map((t, i) => (
                  <li key={i}>
                    <strong>{t.name}</strong>
                    <p className="rationale">{t.rationale}</p>
                  </li>
                ))}
              </ul>
            )}

            {simulationState.coveragePlan.residualGaps.length > 0 && (
              <div style={{marginTop: 15}}>
                <h4>RESIDUAL GAPS (NO COVERAGE)</h4>
                <ul className="rel-list">
                  {simulationState.coveragePlan.residualGaps.map(gId => (
                    <li key={gId} style={{color: '#f44336'}}>
                      {graphData.nodes.find(n => n.id === gId).label}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {simulationState && simulationState.type === 'knowledge' && simulationState.unavailableEmployees.includes(selectedNode.id) && simulationState.transferActions.length > 0 && (
          <div className="card">
            <h4>EVIDENCE-RANKED TRANSFER PACKAGE</h4>
            <ul className="transfer-list">
              {simulationState.transferActions.map((action, i) => (
                <li key={i}>{i+1}. {action}</li>
              ))}
            </ul>
            <div style={{marginTop:10}}>
              <strong>Readiness Scenario:</strong> <span style={{color: '#ff9800'}}>Not Identified</span>
            </div>
          </div>
        )}

        <div className="actions">
          {isTechnical && !simulationState && (
            <button className="action-btn" onClick={simulateFailure}>Simulate Failure</button>
          )}
          {selectedNode.type === 'EMPLOYEE' && !simulationState && (
            <button className="action-btn" onClick={markUnavailable}>Mark Unavailable</button>
          )}
        </div>

        <div className="card">
          <h4>RELATIONSHIPS</h4>
          {outgoing.length > 0 && (
            <div>
              <strong style={{color: '#aaa', fontSize: 12}}>Outgoing:</strong>
              <ul className="rel-list">
                {outgoing.map((r, i) => (
                  <li key={`out-${i}`}>→ {r.edge}: <span>{r.node?.label}</span></li>
                ))}
              </ul>
            </div>
          )}
          {incoming.length > 0 && (
            <div style={{marginTop: 10}}>
              <strong style={{color: '#aaa', fontSize: 12}}>Incoming:</strong>
              <ul className="rel-list">
                {incoming.map((r, i) => (
                  <li key={`in-${i}`}>← {r.edge}: <span>{r.node?.label}</span></li>
                ))}
              </ul>
            </div>
          )}
          {outgoing.length === 0 && incoming.length === 0 && <p className="muted">No direct relationships</p>}
        </div>

        <div className="card">
          <h4>DATABASE RECORD</h4>
          <details>
            <summary>View Raw Data</summary>
            <pre>{JSON.stringify(data, null, 2)}</pre>
          </details>
        </div>
        
      </div>
    </div>
  );
};

export default DetailsPanel;
