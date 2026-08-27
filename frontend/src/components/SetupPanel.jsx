import React, { useState, useEffect } from 'react';
import { fetchSetupSources, fetchSetupContributors, fetchSetupCapabilities, collectSource, resetSetupData, getRagConfluenceSettings, saveRagConfluenceSettings, syncRagConfluence, ingestPagerDuty } from '../services/api';
import './SetupPanel.css';

export default function SetupPanel({ onDataIngested, onGoToDashboard }) {
  const [sources, setSources] = useState([]);
  const [contributors, setContributors] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);

  // Expanded accordion source ID
  const [expandedSourceId, setExpandedSourceId] = useState(null);

  // Form input states
  const [githubUrl, setGithubUrl] = useState('https://github.com/Rakshak29/acmepay-engineering-monorepo');
  const [githubToken, setGithubToken] = useState('');
  
  const [jiraUrl, setJiraUrl] = useState('https://acmepay-engineering.atlassian.net');
  const [jiraEmail, setJiraEmail] = useState('rakshak.s@somaiya.edu');
  const [jiraToken, setJiraToken] = useState('');
  const [jiraIssueKey, setJiraIssueKey] = useState('SCRUM');

  const [confluenceUrl, setConfluenceUrl] = useState('');
  const [confluenceEmail, setConfluenceEmail] = useState('');
  const [confluenceToken, setConfluenceToken] = useState('');
  const [confluenceSpaces, setConfluenceSpaces] = useState('');
  const [confluenceTokenSaved, setConfluenceTokenSaved] = useState(false);

  const [pagerdutyUrl, setPagerdutyUrl] = useState('');
  const [pagerdutyToken, setPagerdutyToken] = useState('');

  const [collectingSourceId, setCollectingSourceId] = useState(null);
  const [feedback, setFeedback] = useState(null);

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

  const loadConfluenceSettings = async () => {
    try {
      const res = await getRagConfluenceSettings();
      const c = res?.settings || {};
      if (c.base_url) setConfluenceUrl(c.base_url);
      if (c.email) setConfluenceEmail(c.email);
      if (Array.isArray(c.space_keys)) setConfluenceSpaces(c.space_keys.join(', '));
      setConfluenceTokenSaved(!!c.api_token_set);
    } catch (e) {
      // Not fatal: the drawer still works, it just starts empty.
      console.warn('Could not read saved Confluence settings:', e);
    }
  };

  useEffect(() => {
    loadData();
    loadConfluenceSettings();
  }, []);

  const toggleExpand = (sourceId) => {
    setFeedback(null);
    setExpandedSourceId(prev => (prev === sourceId ? null : sourceId));
  };

  const handleCollect = async (sourceId) => {
    setCollectingSourceId(sourceId);
    setFeedback(null);

    let payload = {};
    if (sourceId === 'github') {
      payload = {
        url: githubUrl.trim(),
        token: githubToken.trim() || undefined
      };
    } else if (sourceId === 'jira') {
      payload = {
        base_url: jiraUrl.trim(),
        email: jiraEmail.trim() || undefined,
        api_token: jiraToken.trim() || undefined,
        issue_key: jiraIssueKey.trim() || undefined
      };
    }

    if (sourceId === 'pd') {
      try {
        const res = await ingestPagerDuty(pagerdutyUrl.trim(), pagerdutyToken.trim());
        setFeedback({
          type: 'success',
          sourceId,
          message: `Fetched ${res.total_incidents_fetched} incident(s) for service ${res.service_id}. Raw and normalized datasets written.`
        });
        setPagerdutyToken('');
        await loadData();
        if (onDataIngested) onDataIngested();
      } catch (e) {
        setFeedback({
          type: 'error',
          sourceId,
          message: e.response?.data?.detail || e.message || 'PagerDuty ingestion failed'
        });
      } finally {
        setCollectingSourceId(null);
      }
      return;
    }

    if (sourceId === 'confluence') {
      try {
        await saveRagConfluenceSettings({
          base_url: confluenceUrl.trim(),
          email: confluenceEmail.trim(),
          // Blank means "keep the token already saved" rather than clear it.
          api_token: confluenceToken.trim() || undefined,
          space_keys: confluenceSpaces.trim()
        });

        const sync = await syncRagConfluence(false);

        // Report the state of the index, not just what this run re-parsed.
        // sections_written is 0 whenever nothing changed, and showing that
        // alone read as "0 searchable sections" — i.e. like a failure — even
        // though the whole wiki was already indexed.
        const pages = sync.indexed_pages ?? sync.pages_fetched ?? 0;
        const sections = sync.indexed_sections ?? sync.sections_written ?? 0;
        const links = sync.capability_links ?? 0;
        const created = sync.pages_created ?? 0;
        const updated = sync.pages_updated ?? 0;
        const unchanged = sync.pages_unchanged ?? 0;

        let changeNote;
        if (created || updated) {
          const parts = [];
          if (created) parts.push(`${created} new`);
          if (updated) parts.push(`${updated} updated`);
          changeNote = `${parts.join(', ')}${unchanged ? `, ${unchanged} unchanged` : ''}`;
        } else {
          changeNote = 'already up to date';
        }

        let message = `Confluence indexed: ${pages} page(s), ${sections} searchable section(s), ${links} capability link(s) — ${changeNote}.`;
        if (sync.pages_without_capability) {
          message += ` ${sync.pages_without_capability} page(s) had no label or space match and will be found by keyword search only.`;
        }

        setFeedback({ type: 'success', sourceId, message });
        setConfluenceToken('');
        setConfluenceTokenSaved(true);
        await loadData();
        if (onDataIngested) onDataIngested();
      } catch (e) {
        setFeedback({
          type: 'error',
          sourceId,
          message: e.response?.data?.detail || e.message || 'Confluence connection failed'
        });
      } finally {
        setCollectingSourceId(null);
      }
      return;
    }

    try {
      const res = await collectSource(sourceId, payload);
      if (res.success) {
        setFeedback({
          type: 'success',
          sourceId: sourceId,
          message: res.message || `Successfully ingested telemetry from ${sourceId}`
        });

        // Update local status
        setSources(prev => prev.map(s => s.id === sourceId ? { ...s, action: 'COLLECTING', status: 'connected' } : s));

        // Reload data
        await loadData();

        // Notify parent to refresh graph data
        if (onDataIngested) {
          onDataIngested();
        }
      } else {
        setFeedback({
          type: 'error',
          sourceId: sourceId,
          message: res.message || `Failed to collect from ${sourceId}`
        });
      }
    } catch (e) {
      setFeedback({
        type: 'error',
        sourceId: sourceId,
        message: e.response?.data?.detail || e.message || 'Connection error'
      });
    } finally {
      setCollectingSourceId(null);
    }
  };

  const handleReset = async () => {
    if (!window.confirm("Are you sure you want to reset all telemetry and restore clean baseline database state?")) {
      return;
    }
    setResetting(true);
    setFeedback(null);
    try {
      const res = await resetSetupData();
      if (res.success) {
        setFeedback({
          type: 'success',
          message: res.message || 'Telemetry pipeline and database successfully reset!'
        });
        await loadData();
        if (onDataIngested) {
          onDataIngested();
        }
      } else {
        setFeedback({
          type: 'error',
          message: res.message || 'Reset failed.'
        });
      }
    } catch (err) {
      setFeedback({
        type: 'error',
        message: err.message || 'Failed to execute reset.'
      });
    } finally {
      setResetting(false);
    }
  };

  if (loading) {
    return <div className="setup-loading mono">Loading Setup Data...</div>;
  }

  const totalRecords = capabilities.reduce((sum, c) => sum + (c.records || 0), 0);
  const connectedSourcesCount = sources.filter(s => s.status === 'connected').length;

  return (
    <div id="tab-setup">
      
      {/* Top Banner Toolbar with Reset Button */}
      <div className="setup-top-bar">
        <div className="setup-top-info">
          <div className="setup-pipeline-badge mono">TELEMETRY PIPELINE CONFIGURATION</div>
          <div className="setup-pipeline-sub">Connect code repositories, ticketing systems, and incident feeds to map engineering capabilities.</div>
        </div>
        <div className="setup-top-actions">
          <button 
            className="reset-pipeline-btn mono" 
            onClick={handleReset} 
            disabled={resetting}
            title="Wipe dynamic ingestion records and reset knowledge graph to clean baseline"
          >
            {resetting ? (
              <>
                <span className="spinner mini"></span> Resetting Pipeline...
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
                Reset Pipeline
              </>
            )}
          </button>
        </div>
      </div>

      {feedback && (
        <div className={`alert-box ${feedback.type === 'success' ? 'success' : 'error'}`}>
          <span>{feedback.message}</span>
          {feedback.type === 'success' && onGoToDashboard && (
            <button className="goto-dash-inline-btn mono" onClick={onGoToDashboard}>
              View in Dashboard →
            </button>
          )}
        </div>
      )}

      {/* STEP 1: Connect sources */}
      <div className="setup-step">
        <div className="step-header">
          <div className="step-title-group">
            <div className="step-number">1</div>
            <h2 className="step-title">Connect sources</h2>
            <span className="step-meta mono">
              {connectedSourcesCount} connected · {totalRecords} total records
            </span>
          </div>
          <div className={`step-status ${connectedSourcesCount > 0 ? 'done' : ''}`}>
            {connectedSourcesCount > 0 ? 'CONNECTED' : 'ACTION REQUIRED'}
          </div>
        </div>
        
        <div className="step-description">
          <p>
            Connect the software systems where your engineering telemetry resides. Code commits and pull requests show what engineers built, Jira issues show ownership and delivery, and incidents show who resolved critical outages.
          </p>
        </div>

        <div className="step-section">
          <div className="section-label mono">TOTAL INGESTED EVIDENCE RECORDS</div>
          <div className="section-value">{totalRecords}</div>
        </div>

        <div className="source-list">
          {sources.map(s => {
            const isExpanded = expandedSourceId === s.id;
            const isCollecting = collectingSourceId === s.id;

            return (
              <div className={`source-card-wrapper ${isExpanded ? 'expanded' : ''}`} key={s.id}>
                <div className="source-row" onClick={() => toggleExpand(s.id)}>
                  <div className="source-info">
                    <div className="source-icon-title">
                      <span className="source-name">{s.name}</span>
                      <span className={`status-badge mono ${s.status === 'connected' ? 'connected' : 'disconnected'}`}>
                        {s.status}
                      </span>
                    </div>
                    <span className="source-meta mono">{s.type}</span>
                  </div>

                  <div className="source-actions-group">
                    <button 
                      className={`source-action ${s.action === 'COLLECTING' ? 'collecting' : 'setup'} ${isExpanded ? 'active-toggle' : ''}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleExpand(s.id);
                      }}
                    >
                      {isExpanded ? 'CLOSE' : (s.status === 'connected' ? 'CONFIGURE' : s.action)}
                    </button>
                  </div>
                </div>

                {/* EXPANDED LINK PASTER & CONFIGURATION DRAWER */}
                {isExpanded && (
                  <div className="source-drawer">
                    {s.id === 'github' && (
                      <div className="drawer-content">
                        <div className="drawer-title">GitHub Repository Connection</div>
                        <p className="drawer-desc">
                          Paste your repository URL below. ECE will automatically extract commits, pull requests, file touched paths, and reviews to map engineering capabilities.
                        </p>

                        <div className="input-group">
                          <label className="input-label mono">REPOSITORY URL</label>
                          <input 
                            type="text" 
                            className="text-input" 
                            placeholder="https://github.com/owner/repository"
                            value={githubUrl}
                            onChange={(e) => setGithubUrl(e.target.value)}
                          />
                        </div>

                        <div className="input-group">
                          <label className="input-label mono">PERSONAL ACCESS TOKEN (OPTIONAL)</label>
                          <input 
                            type="password" 
                            className="text-input" 
                            placeholder="ghp_... (Leave blank for public repositories or default .env)"
                            value={githubToken}
                            onChange={(e) => setGithubToken(e.target.value)}
                          />
                        </div>

                        <div className="drawer-actions">
                          <button 
                            className="submit-collect-btn" 
                            disabled={isCollecting || !githubUrl.trim()}
                            onClick={() => handleCollect('github')}
                          >
                            {isCollecting ? (
                              <span className="btn-loading">
                                <span className="spinner"></span> Scanning & Ingesting Repository...
                              </span>
                            ) : (
                              'Connect & Ingest GitHub Data'
                            )}
                          </button>
                        </div>
                      </div>
                    )}

                    {s.id === 'jira' && (
                      <div className="drawer-content">
                        <div className="drawer-title">Atlassian Jira Connection</div>
                        <p className="drawer-desc">
                          Connect your Jira Cloud instance to ingest issues, assigned tickets, and sprint deliveries.
                        </p>

                        <div className="input-group">
                          <label className="input-label mono">JIRA BASE URL</label>
                          <input 
                            type="text" 
                            className="text-input" 
                            placeholder="https://your-domain.atlassian.net"
                            value={jiraUrl}
                            onChange={(e) => setJiraUrl(e.target.value)}
                          />
                        </div>

                        <div className="input-row">
                          <div className="input-group flex-1">
                            <label className="input-label mono">ATLASSIAN EMAIL</label>
                            <input 
                              type="email" 
                              className="text-input" 
                              placeholder="engineer@company.com"
                              value={jiraEmail}
                              onChange={(e) => setJiraEmail(e.target.value)}
                            />
                          </div>
                          <div className="input-group flex-1">
                            <label className="input-label mono">API TOKEN</label>
                            <input 
                              type="password" 
                              className="text-input" 
                              placeholder="Leave blank to use .env JIRA_API_TOKEN"
                              value={jiraToken}
                              onChange={(e) => setJiraToken(e.target.value)}
                            />
                          </div>
                        </div>

                        <div className="input-group">
                          <label className="input-label mono">ISSUE KEY TO INGEST (OPTIONAL)</label>
                          <input 
                            type="text" 
                            className="text-input" 
                            placeholder="e.g. PAY-101"
                            value={jiraIssueKey}
                            onChange={(e) => setJiraIssueKey(e.target.value)}
                          />
                        </div>

                        <div className="drawer-actions">
                          <button 
                            className="submit-collect-btn" 
                            disabled={isCollecting || !jiraUrl.trim()}
                            onClick={() => handleCollect('jira')}
                          >
                            {isCollecting ? (
                              <span className="btn-loading">
                                <span className="spinner"></span> Connecting & Syncing Jira...
                              </span>
                            ) : (
                              'Connect & Ingest Jira Tickets'
                            )}
                          </button>
                        </div>
                      </div>
                    )}

                    {s.id === 'confluence' && (
                      <div className="drawer-content">
                        <div className="drawer-title">Confluence Documentation Connection</div>
                        <p className="drawer-desc">
                          Index your team's Confluence wiki so knowledge transfer packages can cite real runbooks. Unlike the other sources, Confluence creates no evidence records and never changes a capability score — it supplies the documentation attached to each capability gap.
                        </p>

                        <div className="input-group">
                          <label className="input-label mono">CONFLUENCE BASE URL</label>
                          <input
                            type="text"
                            className="text-input"
                            placeholder="https://your-domain.atlassian.net/wiki"
                            value={confluenceUrl}
                            onChange={(e) => setConfluenceUrl(e.target.value)}
                          />
                        </div>

                        <div className="input-row">
                          <div className="input-group flex-1">
                            <label className="input-label mono">ATLASSIAN EMAIL</label>
                            <input
                              type="email"
                              className="text-input"
                              placeholder="engineer@company.com"
                              value={confluenceEmail}
                              onChange={(e) => setConfluenceEmail(e.target.value)}
                            />
                          </div>
                          <div className="input-group flex-1">
                            <label className="input-label mono">API TOKEN</label>
                            <input
                              type="password"
                              className="text-input"
                              placeholder={confluenceTokenSaved ? 'Saved — leave blank to keep it' : 'Atlassian API token'}
                              value={confluenceToken}
                              onChange={(e) => setConfluenceToken(e.target.value)}
                            />
                          </div>
                        </div>

                        <div className="input-group">
                          <label className="input-label mono">SPACE KEYS (OPTIONAL)</label>
                          <input
                            type="text"
                            className="text-input"
                            placeholder="e.g. ACMEPAY, DBOPS — blank indexes every readable space"
                            value={confluenceSpaces}
                            onChange={(e) => setConfluenceSpaces(e.target.value)}
                          />
                        </div>

                        <div className="drawer-actions">
                          <button
                            className="submit-collect-btn"
                            disabled={isCollecting || !confluenceUrl.trim()}
                            onClick={() => handleCollect('confluence')}
                          >
                            {isCollecting ? (
                              <span className="btn-loading">
                                <span className="spinner"></span> Indexing Confluence Pages...
                              </span>
                            ) : (
                              'Connect & Index Confluence'
                            )}
                          </button>
                        </div>
                      </div>
                    )}

                    {s.id === 'pd' && (
                      <div className="drawer-content">
                        <div className="drawer-title">PagerDuty Incident Ingestion</div>
                        <p className="drawer-desc">
                          Paste the service URL from your PagerDuty service directory. ECE extracts the service ID, pulls its incidents through the PagerDuty REST API, and writes the raw and normalized datasets.
                        </p>

                        <div className="input-group">
                          <label className="input-label mono">PAGERDUTY SERVICE URL</label>
                          <input
                            type="text"
                            className="text-input"
                            placeholder="https://your-org.pagerduty.com/service-directory/PXXXXXX/activity"
                            value={pagerdutyUrl}
                            onChange={(e) => setPagerdutyUrl(e.target.value)}
                          />
                        </div>

                        <div className="input-group">
                          <label className="input-label mono">REST API TOKEN</label>
                          <input
                            type="password"
                            className="text-input"
                            placeholder="PagerDuty REST API read token"
                            value={pagerdutyToken}
                            onChange={(e) => setPagerdutyToken(e.target.value)}
                          />
                        </div>

                        <div className="drawer-actions">
                          <button
                            className="submit-collect-btn"
                            disabled={isCollecting || !pagerdutyUrl.trim() || !pagerdutyToken.trim()}
                            onClick={() => handleCollect('pd')}
                          >
                            {isCollecting ? (
                              <span className="btn-loading">
                                <span className="spinner"></span> Fetching Incidents...
                              </span>
                            ) : (
                              'Connect & Ingest PagerDuty'
                            )}
                          </button>
                        </div>
                      </div>
                    )}

                    {s.id === 'self' && (
                      <div className="drawer-content">
                        <div className="drawer-title">{s.name} Configuration</div>
                        <p className="drawer-desc">
                          Connect incident management feeds to capture high-pressure problem resolution evidence.
                        </p>

                        <div className="input-group">
                          <label className="input-label mono">ENDPOINT OR WEBHOOK URL</label>
                          <input
                            type="text"
                            className="text-input"
                            placeholder="https://your-incident-feed/..."
                          />
                        </div>

                        <div className="drawer-actions">
                          <button
                            className="submit-collect-btn"
                            disabled={isCollecting}
                            onClick={() => handleCollect(s.id)}
                          >
                            {isCollecting ? 'Syncing...' : 'Save & Connect Feed'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* STEP 2: Map contributors */}
      <div className="setup-step">
        <div className="step-header">
          <div className="step-title-group">
            <div className="step-number">2</div>
            <h2 className="step-title">Map contributors</h2>
            <span className="step-meta mono">{contributors.length} mapped contributors</span>
          </div>
          <div className={`step-status ${totalRecords > 0 ? 'done' : ''}`}>
            {totalRecords > 0 ? 'ACTIVE' : 'PENDING'}
          </div>
        </div>

        <div className="step-description">
          <p>
            Every author or assignee discovered across your connected systems is unified here into an engineering team member profile.
          </p>
        </div>

        {totalRecords > 0 ? (
          <div className="alert-box success">
            ✓ {contributors.length} active contributors attributed across repository commits, PRs, and tickets.
          </div>
        ) : (
          <div className="alert-box">
            <span>No evidence records ingested yet. Connect GitHub or Jira above to attribute contributors.</span>
          </div>
        )}

        <div className="step-section" style={{marginTop: '20px', marginBottom: '15px'}}>
          <div className="section-label mono">MAPPED CONTRIBUTORS — {contributors.length}</div>
        </div>

        <div className="contributor-list">
          {contributors.map((c, i) => (
            <div className="contributor-row" key={c.id || i}>
              <div className="contributor-name">{c.name}</div>
              <div className="contributor-email mono">{c.email}</div>
              <div className="contributor-records mono">{c.records} records</div>
              <button className="unmap-btn mono">view details</button>
            </div>
          ))}
        </div>
      </div>

      {/* STEP 3: Build capability tree */}
      <div className="setup-step">
        <div className="step-header">
          <div className="step-title-group">
            <div className="step-number">3</div>
            <h2 className="step-title">Capability clusters</h2>
            <span className="step-meta mono">{capabilities.length} active capabilities</span>
          </div>
          <div className={`step-status ${totalRecords > 0 ? 'done' : ''}`}>
            {totalRecords > 0 ? 'READY' : 'PENDING'}
          </div>
        </div>

        <div className="step-description">
          <p>
            Telemetry signals are automatically clustered by service module and mapped into capability nodes on the knowledge graph.
          </p>
        </div>

        <div className="metrics-grid">
          <div className="metric-box">
            <div className="metric-label mono">EVIDENCE RECORDS</div>
            <div className="metric-value">{totalRecords}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">TEAM MEMBERS</div>
            <div className="metric-value">{contributors.length}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label mono">CAPABILITIES</div>
            <div className="metric-value">{capabilities.length}</div>
          </div>
        </div>

        {onGoToDashboard && (
          <div className="dash-cta-card">
            <div className="dash-cta-text">
              <div className="dash-cta-title">Telemetry & Knowledge Graph Ready</div>
              <div className="dash-cta-sub">Explore capability coverage, single points of failure, and simulate engineer unavailabilities on the live dashboard.</div>
            </div>
            <button className="goto-dash-large-btn" onClick={onGoToDashboard}>
              Open Dashboard →
            </button>
          </div>
        )}

        <div className="step-section" style={{marginTop: '30px', marginBottom: '20px'}}>
          <div className="section-label mono">DISCOVERED CAPABILITY CLUSTERS — {capabilities.length}</div>
        </div>

        <div className="capability-list">
          {capabilities.map((cap, i) => (
            <div className="capability-card" key={cap.id || i}>
              <div className="cap-card-header">
                <label className="checkbox-label">
                  <input type="checkbox" defaultChecked />
                  <span className="mono">active</span>
                </label>
                <div className="cap-tag mono">{cap.tag}</div>
                <div className="cap-card-meta mono">{cap.records} records · {cap.source}</div>
              </div>
              
              <div className="cap-inputs">
                <input type="text" className="cap-input primary" defaultValue={cap.name} />
                <input type="text" className="cap-input" defaultValue={cap.domain} />
                <input type="text" className="cap-input" defaultValue={cap.key} />
              </div>

              {cap.commits && cap.commits.length > 0 && (
                <div className="cap-commits">
                  {cap.commits.map((commit, j) => (
                    <div className="commit-line mono" key={j}>{commit}</div>
                  ))}
                </div>
              )}

              <div className="cap-footer mono">
                mapped to capability module · evidence verified
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
