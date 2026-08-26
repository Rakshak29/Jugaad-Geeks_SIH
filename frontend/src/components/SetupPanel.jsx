import React, { useState, useEffect } from 'react';
import { fetchSetupSources, fetchSetupContributors, fetchSetupCapabilities } from '../services/api';
import './SetupPanel.css';

export default function SetupPanel() {
  const [sources, setSources] = useState([]);
  const [contributors, setContributors] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [srcRes, contRes, capRes] = await Promise.all([
          fetchSetupSources(),
          fetchSetupContributors(),
          fetchSetupCapabilities()
        ]);
        
        if (srcRes.success) setSources(srcRes.data);
        if (contRes.success) setContributors(contRes.data);
        if (capRes.success) setCapabilities(capRes.data);
        
      } catch (err) {
        console.error("Failed to load setup data:", err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) {
    return <div style={{ color: '#aaa', padding: '40px', textAlign: 'center' }}>Loading Setup Data...</div>;
  }


  return (
    <div id="tab-setup">
      
      {/* STEP 1 */}
      <div className="setup-step">
        <div className="step-header">
          <div className="step-title-group">
            <div className="step-number">1</div>
            <h2 className="step-title">Connect sources</h2>
            <span className="step-meta mono">1 connected · github 338</span>
          </div>
          <div className="step-status done">DONE</div>
        </div>
        
        <div className="step-description">
          <p>Every system the evidence is read from. Each one contributes different rungs — code shows what somebody built, tickets show what they drove, and incidents show who others turned to under pressure, which is the only signal that reaches HIGH and the only one invisible to Git.</p>
        </div>

        <div className="step-section">
          <div className="section-label mono">GITHUB RECORDS</div>
          <div className="section-value">{capabilities.reduce((sum, c) => sum + (c.records || 0), 0)}</div>
        </div>

        <div className="source-list">
          {sources.map(s => (
            <div className="source-row" key={s.id}>
              <div className="source-info">
                <span className="source-name">{s.name}</span>
                <span className="source-meta mono">{s.type} · {s.status}</span>
              </div>
              <button className={`source-action ${s.action === 'COLLECTING' ? 'collecting' : 'setup'}`}>
                {s.action}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* STEP 2 */}
      <div className="setup-step">
        <div className="step-header">
          <div className="step-title-group">
            <div className="step-number">2</div>
            <h2 className="step-title">Map contributors</h2>
            <span className="step-meta mono">{contributors.length} people · no evidence unattributed</span>
          </div>
          <div className="step-status done">DONE</div>
        </div>

        <div className="step-description">
          <p>Every identifier the repository contains, grouped where two of them are plausibly one person. Confirm each group — grouping is only ever proposed here, never applied, because merging two people invents a coverer who does not exist, which is worse than leaving one unmapped.</p>
        </div>

        <div className="alert-box success">
          No eligible evidence is unattributed. Every record the repository contains reaches a person.
        </div>

        <div className="step-section" style={{marginTop: '30px', marginBottom: '15px'}}>
          <div className="section-label mono">MAPPED — {contributors.length}</div>
        </div>

        <div className="contributor-list">
          {contributors.map((c, i) => (
            <div className="contributor-row" key={i}>
              <div className="contributor-name">{c.name}</div>
              <div className="contributor-email mono">{c.email}</div>
              <div className="contributor-records mono">{c.records} records</div>
              <button className="unmap-btn mono">unmap</button>
            </div>
          ))}
        </div>
      </div>

      {/* STEP 3 */}
      <div className="setup-step">
        <div className="step-header">
          <div className="step-title-group">
            <div className="step-number">3</div>
            <h2 className="step-title">Build capability tree</h2>
            <span className="step-meta mono">{capabilities.length} capabilities</span>
          </div>
          <div className="step-status done">DONE</div>
        </div>

        <div className="step-description">
          <p>Clustering groups records that touched the same directories, and the namer labels each group. Neither decides whether a group is a responsibility your organisation actually tracks — that is a claim about your company, not about your data, so it is yours to make below.</p>
        </div>

        <div className="metrics-grid">
          <div className="metric-box">
            <div className="metric-label mono">RECORDS</div>
            <div className="metric-value">{capabilities.reduce((sum, c) => sum + (c.records || 0), 0)}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">ITEMS</div>
            <div className="metric-value">{capabilities.reduce((sum, c) => sum + (c.records || 0), 0)}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">PEOPLE</div>
            <div className="metric-value">{contributors.length}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">CAPABILITIES</div>
            <div className="metric-value">{capabilities.length}</div>
          </div>
        </div>

        <button className="rerun-btn">Re-run clustering</button>

        <div className="step-section" style={{marginTop: '40px', marginBottom: '20px'}}>
          <div className="section-label mono">CANDIDATES — {capabilities.length} found, {capabilities.length} selected</div>
        </div>

        <div className="info-box">
          These groups were found in your own records, and the namer labelled them — both are yours to change. Anything you un-tick is not a capability you track: its records stay in the evidence store, but nothing reports on them. Nothing outside this list can become a capability, and nothing on it becomes one until you confirm.
        </div>

        <div className="capability-list">
          {capabilities.map((cap, i) => (
            <div className="capability-card" key={i}>
              <div className="cap-card-header">
                <label className="checkbox-label">
                  <input type="checkbox" defaultChecked />
                  <span className="mono">track</span>
                </label>
                <div className="cap-tag mono">{cap.tag}</div>
                <div className="cap-card-meta mono">{cap.records} records · {cap.source}</div>
              </div>
              
              <div className="cap-inputs">
                <input type="text" className="cap-input primary" defaultValue={cap.name} />
                <input type="text" className="cap-input" defaultValue={cap.domain} />
                <input type="text" className="cap-input" defaultValue={cap.key} />
              </div>

              <div className="cap-commits">
                {cap.commits.map((commit, j) => (
                  <div className="commit-line mono" key={j}>{commit}</div>
                ))}
              </div>

              <div className="cap-footer mono">
                named by the model namer · kept from your last review
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
