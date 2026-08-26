import React, { useState } from 'react';
import './SetupPanel.css';

export default function SetupPanel() {
  const [sources] = useState([
    { id: 'github', name: 'GitHub', type: 'github', status: 'connected', action: 'COLLECTING' },
    { id: 'jira', name: 'Jira Cloud', type: 'jira', status: 'not connected', action: 'SET UP' },
    { id: 'pd', name: 'PagerDuty', type: 'incident', status: 'not connected', action: 'SET UP' },
    { id: 'self', name: 'Self-hosted incidents', type: 'incident', status: 'not connected', action: 'SET UP' }
  ]);

  const [contributors] = useState([
    { name: 'Rohan Gupta', email: 'rohan.gupta@acmepay.io', records: 35 },
    { name: 'Rakshak Shetty', email: 'rakshak@acmepay.io', records: 26 },
    { name: 'Vikram Malhotra', email: 'vikram@acmepay.io', records: 25 },
    { name: 'Krish Trivedi', email: 'krish@acmepay.io', records: 24 },
    { name: 'Keyuri Sheth', email: 'keyuri@acmepay.io', records: 22 },
    { name: 'Parth More', email: 'parth@acmepay.io', records: 22 },
    { name: 'Kshitij Naidu', email: 'kshitij@acmepay.io', records: 20 },
    { name: 'Naman Nahar', email: 'naman@acmepay.io', records: 20 }
  ]);

  const [capabilities] = useState([
    {
      id: 'cap1',
      tag: 'services/payment',
      records: 33,
      source: 'github',
      name: 'Payment Workflow Management',
      domain: 'Payment',
      key: 'payment',
      commits: [
        'fix(payment): resolve state machine deadlock during charge authorization retry',
        'fix(payment): add exponential backoff jitter to payment processor retry loop',
        'feat(payment): handle payment intent creation and idempotency verification'
      ]
    },
    {
      id: 'cap2',
      tag: 'services/auth',
      records: 46,
      source: 'github',
      name: 'Identity And Access Management',
      domain: 'Auth',
      key: 'auth',
      commits: [
        'sec(auth): enforce role-based authorization scope checking on API proxy',
        'feat(auth): implement OAuth2 authorization code token exchange',
        'feat(auth): issue bearer JWT with custom merchant roles and token signing'
      ]
    },
    {
      id: 'cap3',
      tag: 'services/user',
      records: 28,
      source: 'github',
      name: 'User Profile & Onboarding',
      domain: 'User',
      key: 'user',
      commits: [
        'feat(user): add comprehensive user profile completion wizard',
        'fix(user): correct validation logic for international phone numbers'
      ]
    }
  ]);

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
          <div className="section-value">338</div>
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
            <span className="step-meta mono">20 people · no evidence unattributed</span>
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
          <div className="section-label mono">MAPPED — 20</div>
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
            <span className="step-meta mono">16 capabilities</span>
          </div>
          <div className="step-status done">DONE</div>
        </div>

        <div className="step-description">
          <p>Clustering groups records that touched the same directories, and the namer labels each group. Neither decides whether a group is a responsibility your organisation actually tracks — that is a claim about your company, not about your data, so it is yours to make below.</p>
        </div>

        <div className="metrics-grid">
          <div className="metric-box">
            <div className="metric-label mono">RECORDS</div>
            <div className="metric-value">338</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">ITEMS</div>
            <div className="metric-value">338</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">PEOPLE</div>
            <div className="metric-value">20</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">CAPABILITIES</div>
            <div className="metric-value">16</div>
          </div>
        </div>

        <button className="rerun-btn">Re-run clustering</button>

        <div className="step-section" style={{marginTop: '40px', marginBottom: '20px'}}>
          <div className="section-label mono">CANDIDATES — 16 found, 16 selected</div>
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
