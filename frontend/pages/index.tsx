/**
 * Irish Workers' Rights Chatbot - Frontend
 * 
 * Responsive layout:
 * - Desktop (>768px): Sidebar + chat side by side
 * - Mobile (≤768px): Full-screen chat with slide-out sidebar drawer
 * 
 * Key UI elements:
 * 1. Persistent disclaimer banner (visible before any interaction)
 * 2. Knowledge base "last updated" date
 * 3. Official source links in sidebar/drawer
 * 4. Per-response source citations
 */
import { useState, useEffect, useRef } from 'react';
import Head from 'next/head';
import ReactMarkdown from 'react-markdown';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{ title: string; doc_type?: string; section?: string; relevance?: number }>;
  officialLinks?: Array<{ name: string; url: string; description: string }>;
  hasAuthoritativeSources?: boolean;
  isLookupOpener?: boolean;
  suppressSources?: boolean;
  lookupContextExpired?: boolean;
}

interface CompanyRecord {
  source: 'hsa' | 'wrc';
  company_name: string;
  matched_as: 'defendant' | 'mention';
  case_number?: string | null;
  case_category?: string | null;
  date?: string | null;
  court?: string | null;
  outcome?: string | null;
  outcome_status?: 'confirmed' | 'not_extracted' | 'not_applicable';
  fine_amount?: number | null;
  legislation?: string[];
  url?: string | null;
  confidence: 'high' | 'medium' | 'low';
  disclaimer?: string | null;
}

interface CompanyCheckResult {
  company: string;
  summary: {
    total_records: number;
    hsa_prosecutions: number;
    wrc_decisions: number;
    labour_court_records: number;
  };
  source_status: Record<string, string>;
  partial_results: boolean;
  records: CompanyRecord[];
  warnings: string[];
}

interface Metadata {
  disclaimer: string;
  knowledge_base_updated: string;
  knowledge_base_version: string;
  official_sources: Array<{ name: string; url: string; description: string }>;
  important_contacts: {
    wrc_info_line: string;
    wrc_online_complaints: string;
    hsa_contact: string;
    citizens_info_phone: string;
  };
  time_limits_warning: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [feedback, setFeedback] = useState<Record<number, 'up' | 'down'>>({});
  const [mode, setMode] = useState<'chat' | 'company'>('chat');
  const [companyName, setCompanyName] = useState('');
  const [includeMentions, setIncludeMentions] = useState(false);
  const [companyLoading, setCompanyLoading] = useState(false);
  const [companyError, setCompanyError] = useState('');
  const [companyResult, setCompanyResult] = useState<CompanyCheckResult | null>(null);
  const [lookupId, setLookupId] = useState<string | null>(null);
  const [lookupExpired, setLookupExpired] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch metadata on mount
  useEffect(() => {
    fetch(`${API_URL}/metadata`)
      .then(res => res.json())
      .then(setMetadata)
      .catch(console.error);
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Close sidebar on resize to desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 768) {
        setSidebarOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    const requestHadLookupId = !!lookupId;

    try {
      const history = messages.filter(m => !m.isLookupOpener).slice(-10).map(m => ({
        role: m.role,
        content: m.content
      }));

      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          history,
          lookup_id: lookupId
        })
      });

      const data = await response.json();

      if (data.lookup_context_expired) {
        setLookupExpired(true);
        setLookupId(null);
      }

      const assistantMessage: Message = {
        role: 'assistant',
        content: data.answer,
        sources: data.sources,
        officialLinks: data.official_links,
        hasAuthoritativeSources: data.has_authoritative_sources,
        suppressSources: requestHadLookupId,
        lookupContextExpired: data.lookup_context_expired
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, something went wrong. Please try again.'
      }]);
    } finally {
      setLoading(false);
    }
  };

  const startFresh = () => {
    setMessages([]);
    setInput('');
    setLookupId(null);
    setLookupExpired(false);
    setFeedback({});
  };

  const runCompanyCheck = async () => {
    if (!companyName.trim() || companyLoading) return;

    setCompanyLoading(true);
    setCompanyError('');
    setCompanyResult(null);

    try {
      const response = await fetch(`${API_URL}/api/company-check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company: companyName.trim(),
          include_mentions: includeMentions,
          limit: 10
        })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Lookup service is temporarily unavailable');
      }

      setLookupId(data.lookup_id);
      setCompanyResult(data.result);
      setLookupExpired(false);
    } catch (error) {
      console.error('Company check error:', error);
      setCompanyError(error instanceof Error ? error.message : 'Lookup service is temporarily unavailable');
    } finally {
      setCompanyLoading(false);
    }
  };

  const openChatWithResults = () => {
    if (!companyResult || !lookupId) return;

    const wrc = companyResult.summary.wrc_decisions || 0;
    const hsa = companyResult.summary.hsa_prosecutions || 0;
    setMode('chat');
    setLookupExpired(false);
    setMessages(prev => [
      ...prev,
      {
        role: 'assistant',
        content: `I can see the records you just looked up for **${companyResult.company}** (${wrc} WRC cases, ${hsa} HSA prosecutions). What would you like to ask about them?`,
        hasAuthoritativeSources: true,
        isLookupOpener: true
      }
    ]);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const formatMoney = (amount?: number | null) => {
    if (!amount) return '';
    return new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(amount);
  };

  const isHttpUrl = (url?: string | null) => !!url && /^https?:\/\//i.test(url);

  const sendFeedback = async (messageIndex: number, type: 'up' | 'down') => {
    // Find the user message that preceded this assistant message
    const assistantMsg = messages[messageIndex];
    const userMsg = messages[messageIndex - 1];
    if (!userMsg || !assistantMsg) return;

    setFeedback(prev => ({ ...prev, [messageIndex]: type }));

    try {
      await fetch(`${API_URL}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg.content,
          answer: assistantMsg.content,
          feedback: type
        })
      });
    } catch (error) {
      console.error('Feedback error:', error);
    }
  };

  return (
    <div className="app-container">
      <Head>
        <title>Irish Workers&apos; Rights Chatbot</title>
        <meta name="description" content="Get information about your employment rights in Ireland" />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
      </Head>

      {/* DISCLAIMER BANNER */}
      <header className="disclaimer-banner">
        <div className="disclaimer-content">
          <strong>⚠️ Important:</strong> {metadata?.disclaimer || 
            'This chatbot provides general information only, not legal advice. Consult the WRC, a solicitor, or your union for specific situations.'}
        </div>
        {metadata?.time_limits_warning && (
          <div className="time-limit-warning">
            {metadata.time_limits_warning}
          </div>
        )}
      </header>

      <div className="mode-toggle-wrap">
        <div className="mode-toggle" role="tablist" aria-label="Choose chatbot mode">
          <button
            className={`mode-tab ${mode === 'chat' ? 'active' : ''}`}
            onClick={() => setMode('chat')}
            type="button"
          >
            Ask a question
          </button>
          <button
            className={`mode-tab ${mode === 'company' ? 'active' : ''}`}
            onClick={() => setMode('company')}
            type="button"
          >
            Check a company
          </button>
        </div>
      </div>

      <div className="main-layout">
        {/* MOBILE: Sidebar overlay */}
        {sidebarOpen && (
          <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
        )}

        {/* SIDEBAR / DRAWER */}
        <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
          <button className="sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">
            ✕
          </button>
          <h3 className="sidebar-heading">Official Sources</h3>
          <p className="sidebar-note">Always verify information with official sources:</p>
          
          {metadata?.official_sources.map((source, i) => (
            <a 
              key={i} 
              href={source.url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="official-link"
            >
              <span className="official-link-name">{source.name}</span>
              <span className="official-link-desc">{source.description}</span>
            </a>
          ))}

          <div className="contact-box">
            <h4 className="contact-heading">Need immediate help?</h4>
            <p className="contact-item"><strong>WRC Info Line:</strong><br/>{metadata?.important_contacts.wrc_info_line}</p>
            <p className="contact-item"><strong>Citizens Info:</strong><br/>{metadata?.important_contacts.citizens_info_phone}</p>
            <a 
              href={metadata?.important_contacts.wrc_online_complaints}
              target="_blank"
              rel="noopener noreferrer"
              className="complaint-button"
            >
              Make a WRC Complaint Online →
            </a>
          </div>

          <div className="kb-info">
            <small>
              Knowledge base last updated: <strong>{metadata?.knowledge_base_updated || 'Unknown'}</strong>
              <br/>
              Version: {metadata?.knowledge_base_version}
            </small>
          </div>
        </aside>

        {/* CHAT AREA */}
        <main className="chat-area">
          {/* Mobile top bar with sidebar toggle */}
          <div className="mobile-topbar">
            <button 
              className="sidebar-toggle" 
              onClick={() => setSidebarOpen(true)}
              aria-label="Open resources panel"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6"/>
                <line x1="3" y1="12" x2="21" y2="12"/>
                <line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
              <span>Resources &amp; Contacts</span>
            </button>
          </div>

          {mode === 'chat' ? (
          <>
          <div className="chat-toolbar">
            {lookupExpired && (
              <div className="lookup-expired">
                Your lookup context has expired. Run a new check to bring those records back into the conversation.
              </div>
            )}
            {(messages.length > 0 || lookupId) && (
              <button className="start-fresh" onClick={startFresh} type="button">
                Start fresh
              </button>
            )}
          </div>

          <div className="messages">
            {messages.length === 0 && (
              <div className="welcome-message">
                <h2>Irish Workers&apos; Rights Chatbot</h2>
                <p>Ask me about your employment rights in Ireland. I can help with questions about:</p>
                <ul>
                  <li>Pay, minimum wage, and deductions</li>
                  <li>Working hours, breaks, and annual leave</li>
                  <li>Unfair dismissal and redundancy</li>
                  <li>Discrimination and equality</li>
                  <li>Sick leave, maternity/paternity leave</li>
                  <li>Making a complaint to the WRC</li>
                </ul>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`message ${msg.role}`}>
                <div className="message-content">
                  {msg.role === 'assistant' ? (
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  ) : (
                    msg.content
                  )}
                </div>
                
                {msg.role === 'assistant' && msg.hasAuthoritativeSources === false && (
                  <div className="no-sources-warning">
                    <small>
                      ⚠️ <strong>Note:</strong> This response is not based on authoritative sources from the knowledge base. 
                      Please verify with official sources.
                    </small>
                  </div>
                )}
                
                {msg.role === 'assistant' && msg.lookupContextExpired && (
                  <div className="lookup-expired-notice">
                    <small>The records from your earlier lookup are no longer available. Run a new check to continue.</small>
                  </div>
                )}

                {!msg.suppressSources && msg.sources && msg.sources.length > 0 && (
                  <div className="message-sources">
                    <small>
                      <strong>Sources:</strong>{' '}
                      {msg.sources.map((s, j) => (
                        <span key={j}>
                          {s.title}
                          {s.doc_type ? ` [${s.doc_type}]` : ''}
                          {s.section ? ` (${s.section})` : ''}
                          {s.relevance ? ` • ${Math.round(s.relevance * 100)}% match` : ''}
                          {j < msg.sources!.length - 1 ? ' | ' : ''}
                        </span>
                      ))}
                    </small>
                  </div>
                )}

                {msg.officialLinks && msg.officialLinks.length > 0 && (
                  <div className="message-links">
                    <small>
                      <strong>Learn more:</strong>{' '}
                      {msg.officialLinks.map((link, j) => (
                        <a key={j} href={link.url} target="_blank" rel="noopener noreferrer">
                          {link.name}
                        </a>
                      ))}
                    </small>
                  </div>
                )}

                {msg.role === 'assistant' && i > 0 && (
                  <div className="feedback-buttons">
                    {feedback[i] ? (
                      <span className="feedback-thanks">
                        {feedback[i] === 'up' ? '👍' : '👎'} Thanks for your feedback
                      </span>
                    ) : (
                      <>
                        <span className="feedback-label">Was this helpful?</span>
                        <button
                          className="feedback-btn"
                          onClick={() => sendFeedback(i, 'up')}
                          aria-label="Thumbs up"
                        >👍</button>
                        <button
                          className="feedback-btn"
                          onClick={() => sendFeedback(i, 'down')}
                          aria-label="Thumbs down"
                        >👎</button>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="message assistant loading">
                <div className="typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
              placeholder="Ask about your employment rights..."
              disabled={loading}
            />
            <button onClick={sendMessage} disabled={loading || !input.trim()}>
              Send
            </button>
          </div>
          </>
          ) : (
          <div className="company-panel">
            <section className="company-info-box">
              <h2>Check public employer records</h2>
              <h3>What this check does</h3>
              <p>
                This searches public records about Irish employers: prosecutions by the Health and Safety Authority
                (HSA) and cases filed at the Workplace Relations Commission (WRC).
              </p>
              <h3>What it doesn&apos;t do</h3>
              <p className="company-emphasis">
                A match means the employer&apos;s name appears in a public record. It does NOT mean the employer broke
                the law, lost a case, or treated workers badly.
              </p>
              <p>
                WRC search results show that a case was filed. They don&apos;t show what the WRC decided. For the actual
                outcome, open the linked source record.
              </p>
              <h3>Best results</h3>
              <p>
                Use the fullest company name you have, for example &quot;Tesco Ireland Limited&quot; rather than &quot;Tesco&quot;.
                Short or common names can return matches for unrelated employers.
              </p>
            </section>

            <section className="company-form">
              <label htmlFor="company-name">Company or employer name</label>
              <div className="company-form-row">
                <input
                  id="company-name"
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && runCompanyCheck()}
                  placeholder="e.g. Tesco Ireland Limited"
                  disabled={companyLoading}
                />
                <button onClick={runCompanyCheck} disabled={companyLoading || companyName.trim().length < 2} type="button">
                  {companyLoading ? 'Checking...' : 'Check'}
                </button>
              </div>
              <label className="mentions-toggle">
                <input
                  type="checkbox"
                  checked={includeMentions}
                  onChange={(e) => setIncludeMentions(e.target.checked)}
                  disabled={companyLoading}
                />
                Include indirect mentions (slower, more results, more false positives)
              </label>
              {companyLoading && <p className="company-loading">Checking public records...</p>}
              {companyError && <p className="company-error">{companyError}</p>}
            </section>

            {companyResult && (
              <section className="company-results">
                <h2>
                  Found {companyResult.summary.total_records} public records for &quot;{companyResult.company}&quot;:
                </h2>
                <p className="results-summary">
                  {companyResult.summary.hsa_prosecutions} HSA prosecutions, {companyResult.summary.wrc_decisions} WRC cases.
                </p>
                <p className="results-reminder">
                  Remember: WRC matches mean a case was filed, not that the company lost it. Open each source for the actual decision.
                </p>
                {companyResult.partial_results && (
                  <p className="partial-warning">
                    Note: one source was unavailable for this lookup. Try again in a moment for a fuller picture.
                  </p>
                )}

                <div className="record-list">
                  {companyResult.records.map((record, i) => (
                    <article key={`${record.source}-${record.case_number || record.company_name}-${i}`} className={`record-card ${record.source}`}>
                      <span className={`confidence-badge ${record.confidence}`}>{record.confidence}</span>
                      {record.source === 'wrc' ? (
                        <>
                          <p className="record-kicker">WRC adjudication record - subject not extracted</p>
                          <h3>{record.company_name}</h3>
                          <p className="record-meta">
                            Filed: {record.date || 'Date not shown'}
                            {record.case_number ? ` - Case ${record.case_number}` : ''}
                          </p>
                          <p>
                            Outcome not extracted by this search. Open the source record to see the WRC&apos;s decision and what the case was about.
                          </p>
                        </>
                      ) : (
                        <>
                          <p className="record-kicker">HSA prosecution</p>
                          <h3>{record.company_name}</h3>
                          <p className="record-meta">
                            {record.date || 'Date not shown'}
                            {record.court ? ` - ${record.court}` : ''}
                          </p>
                          {(record.outcome || record.fine_amount) && (
                            <p>
                              {record.outcome ? `Outcome: ${record.outcome}. ` : ''}
                              {record.fine_amount ? `Fine: ${formatMoney(record.fine_amount)}.` : ''}
                            </p>
                          )}
                          {record.legislation && record.legislation.length > 0 && (
                            <p>Legislation: {record.legislation.join(', ')}</p>
                          )}
                        </>
                      )}
                      {isHttpUrl(record.url) ? (
                        <a href={record.url!} target="_blank" rel="noopener noreferrer" className="source-button">
                          View source record
                        </a>
                      ) : (
                        <p className="source-unavailable">Source record link is not available online for this result.</p>
                      )}
                    </article>
                  ))}
                </div>

                <div className="chat-bridge">
                  <h3>Have questions about what these records mean?</h3>
                  <p>
                    The chatbot can help explain the records, what the case types involve, and what your options are if
                    you want to take this further. The chatbot will know about the records you just looked up.
                  </p>
                  <button onClick={openChatWithResults} disabled={!lookupId} type="button">
                    Open chat with these results
                  </button>
                </div>
              </section>
            )}
          </div>
          )}
        </main>
      </div>

      {/* FOOTER */}
      <footer className="footer">
        <p>
          This service is provided for informational purposes only and does not constitute legal advice.
          For urgent matters, contact the <a href="https://www.workplacerelations.ie">WRC</a> directly.
        </p>
      </footer>

      {/* ============================================================
          GLOBAL STYLES - using global to avoid styled-jsx scoping issues
          ============================================================ */}
      <style jsx global>{`
        /* ===========================
           RESET & BASE
           =========================== */
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }
        html, body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          height: 100%;
        }

        /* ===========================
           APP CONTAINER
           =========================== */
        .app-container {
          height: 100vh;
          height: 100dvh;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        /* ===========================
           DISCLAIMER BANNER
           =========================== */
        .disclaimer-banner {
          background: #fff3cd;
          border-bottom: 2px solid #ffc107;
          padding: 10px 16px;
          text-align: center;
          flex-shrink: 0;
        }
        .disclaimer-content {
          color: #856404;
          font-size: 14px;
          line-height: 1.4;
        }
        .time-limit-warning {
          color: #721c24;
          font-weight: bold;
          font-size: 13px;
          margin-top: 4px;
        }

        /* ===========================
           MODE TOGGLE
           =========================== */
        .mode-toggle-wrap {
          flex-shrink: 0;
          padding: 10px 16px;
          background: #ffffff;
          border-bottom: 1px solid #dee2e6;
          display: flex;
          justify-content: center;
        }
        .mode-toggle {
          display: inline-flex;
          gap: 4px;
          padding: 4px;
          background: #eef2f7;
          border: 1px solid #d8e0ea;
          border-radius: 8px;
        }
        .mode-tab {
          border: 0;
          background: transparent;
          padding: 9px 16px;
          border-radius: 6px;
          font-weight: 600;
          color: #495057;
          cursor: pointer;
        }
        .mode-tab.active {
          background: #0d6efd;
          color: white;
        }

        /* ===========================
           MAIN LAYOUT
           =========================== */
        .main-layout {
          display: flex;
          flex: 1;
          min-height: 0;
          position: relative;
        }

        /* ===========================
           SIDEBAR
           =========================== */
        .sidebar {
          width: 280px;
          background: #f8f9fa;
          padding: 20px;
          border-right: 1px solid #dee2e6;
          overflow-y: auto;
          flex-shrink: 0;
        }
        .sidebar-heading {
          margin-top: 0;
          margin-bottom: 10px;
          color: #0d6efd;
          font-size: 18px;
        }
        .sidebar-note {
          font-size: 13px;
          color: #6c757d;
          margin-bottom: 15px;
        }
        .sidebar-close {
          display: none;
        }
        .sidebar-overlay {
          display: none;
        }

        /* Official source link cards */
        .official-link {
          display: block;
          padding: 12px;
          margin-bottom: 10px;
          background: white;
          border: 1px solid #dee2e6;
          border-radius: 6px;
          text-decoration: none;
          color: inherit;
          transition: border-color 0.2s;
        }
        .official-link:hover {
          border-color: #0d6efd;
        }
        .official-link-name {
          display: block;
          color: #0d6efd;
          font-weight: 600;
          margin-bottom: 4px;
          font-size: 14px;
        }
        .official-link-desc {
          display: block;
          font-size: 12px;
          color: #6c757d;
          line-height: 1.4;
        }

        /* Contact box */
        .contact-box {
          background: #e7f1ff;
          padding: 15px;
          border-radius: 8px;
          margin-top: 20px;
        }
        .contact-heading {
          margin: 0 0 10px 0;
          color: #0d6efd;
          font-size: 15px;
        }
        .contact-item {
          margin: 8px 0;
          font-size: 14px;
          line-height: 1.4;
        }
        .complaint-button {
          display: block;
          margin-top: 12px;
          padding: 12px;
          background: #0d6efd;
          color: white;
          text-align: center;
          text-decoration: none;
          border-radius: 6px;
          font-weight: bold;
          font-size: 14px;
          min-height: 44px;
          line-height: 20px;
        }
        .complaint-button:hover {
          background: #0b5ed7;
        }

        .kb-info {
          margin-top: 20px;
          padding-top: 15px;
          border-top: 1px solid #dee2e6;
          color: #6c757d;
          font-size: 13px;
        }

        /* ===========================
           MOBILE TOPBAR (hidden on desktop)
           =========================== */
        .mobile-topbar {
          display: none;
        }

        /* ===========================
           CHAT AREA
           =========================== */
        .chat-area {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
          min-height: 0;
        }
        .chat-toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 10px 20px 0;
          flex-shrink: 0;
        }
        .lookup-expired {
          flex: 1;
          padding: 8px 12px;
          background: #fff3cd;
          border: 1px solid #ffc107;
          border-radius: 6px;
          color: #664d03;
          font-size: 13px;
        }
        .start-fresh {
          border: 1px solid #ced4da;
          background: white;
          color: #495057;
          padding: 8px 12px;
          border-radius: 6px;
          cursor: pointer;
          font-weight: 600;
          white-space: nowrap;
        }
        .start-fresh:hover {
          border-color: #0d6efd;
          color: #0d6efd;
        }
        .messages {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
          -webkit-overflow-scrolling: touch;
        }
        .welcome-message {
          background: #f8f9fa;
          padding: 30px;
          border-radius: 12px;
          max-width: 600px;
          margin: 0 auto;
        }
        .welcome-message h2 {
          color: #0d6efd;
          margin-top: 0;
          margin-bottom: 12px;
        }
        .welcome-message p {
          margin-bottom: 12px;
        }
        .welcome-message ul {
          margin-bottom: 0;
          padding-left: 24px;
        }
        .welcome-message li {
          margin-bottom: 4px;
        }

        /* Messages */
        .message {
          max-width: 80%;
          margin-bottom: 16px;
          padding: 12px 16px;
          border-radius: 12px;
          word-wrap: break-word;
          overflow-wrap: break-word;
        }
        .message.user {
          margin-left: auto;
          background: #0d6efd;
          color: white;
        }
        .message.assistant {
          background: #f8f9fa;
          border: 1px solid #dee2e6;
        }
        .message-content p {
          margin: 0 0 10px 0;
        }
        .message-content p:last-child {
          margin-bottom: 0;
        }
        .message-content ul, .message-content ol {
          margin: 8px 0;
          padding-left: 24px;
        }
        .message-content li {
          margin-bottom: 4px;
        }
        .message-content strong {
          font-weight: 600;
        }
        .message-content a {
          color: #0d6efd;
          text-decoration: underline;
        }
        .message-sources, .message-links {
          margin-top: 10px;
          padding-top: 10px;
          border-top: 1px solid #dee2e6;
          font-size: 12px;
          color: #6c757d;
        }
        .no-sources-warning, .lookup-expired-notice {
          margin-top: 10px;
          padding: 8px 12px;
          background: #fff3cd;
          border: 1px solid #ffc107;
          border-radius: 6px;
          font-size: 12px;
          color: #856404;
        }
        .message-links a {
          margin-right: 10px;
          color: #0d6efd;
        }

        /* Feedback buttons */
        .feedback-buttons {
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid #dee2e6;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .feedback-label {
          font-size: 12px;
          color: #6c757d;
        }
        .feedback-btn {
          background: none;
          border: 1px solid #dee2e6;
          border-radius: 4px;
          padding: 2px 8px;
          font-size: 16px;
          cursor: pointer;
          line-height: 1.4;
          transition: background 0.15s, border-color 0.15s;
        }
        .feedback-btn:hover {
          background: #e9ecef;
          border-color: #adb5bd;
        }
        .feedback-thanks {
          font-size: 12px;
          color: #6c757d;
        }

        /* ===========================
           INPUT AREA
           =========================== */
        .input-area {
          display: flex;
          padding: 16px 20px;
          border-top: 1px solid #dee2e6;
          background: white;
          flex-shrink: 0;
          gap: 10px;
        }
        .input-area input {
          flex: 1;
          padding: 12px 16px;
          border: 1px solid #dee2e6;
          border-radius: 8px;
          font-size: 16px;
          min-height: 44px;
          font-family: inherit;
          -webkit-appearance: none;
        }
        .input-area input:focus {
          outline: none;
          border-color: #0d6efd;
          box-shadow: 0 0 0 2px rgba(13, 110, 253, 0.15);
        }
        .input-area button {
          padding: 12px 24px;
          background: #0d6efd;
          color: white;
          border: none;
          border-radius: 8px;
          font-size: 16px;
          font-family: inherit;
          cursor: pointer;
          min-height: 44px;
          min-width: 44px;
          flex-shrink: 0;
        }
        .input-area button:disabled {
          background: #6c757d;
          cursor: not-allowed;
        }
        .input-area button:not(:disabled):hover {
          background: #0b5ed7;
        }

        /* ===========================
           COMPANY CHECK
           =========================== */
        .company-panel {
          flex: 1;
          overflow-y: auto;
          padding: 20px;
          background: #f8fafc;
        }
        .company-panel section {
          max-width: 900px;
          margin: 0 auto 18px;
        }
        .company-info-box {
          background: #eef6ff;
          border: 1px solid #b9d7f6;
          border-radius: 8px;
          padding: 18px;
          color: #17324d;
        }
        .company-info-box h2 {
          font-size: 22px;
          margin-bottom: 12px;
        }
        .company-info-box h3 {
          font-size: 14px;
          margin: 14px 0 6px;
          color: #0b5a9c;
        }
        .company-info-box p {
          line-height: 1.5;
          margin-bottom: 8px;
        }
        .company-emphasis {
          font-weight: 700;
          font-size: 16px;
        }
        .company-form {
          background: white;
          border: 1px solid #dee2e6;
          border-radius: 8px;
          padding: 18px;
        }
        .company-form label {
          display: block;
          font-weight: 700;
          margin-bottom: 8px;
        }
        .company-form-row {
          display: flex;
          gap: 10px;
        }
        .company-form-row input {
          flex: 1;
          padding: 12px 14px;
          border: 1px solid #ced4da;
          border-radius: 8px;
          font-size: 16px;
        }
        .company-form-row input:focus {
          outline: none;
          border-color: #0d6efd;
          box-shadow: 0 0 0 2px rgba(13, 110, 253, 0.15);
        }
        .company-form-row button,
        .chat-bridge button {
          padding: 12px 18px;
          background: #0d6efd;
          border: 0;
          border-radius: 8px;
          color: white;
          font-weight: 700;
          cursor: pointer;
        }
        .company-form-row button:disabled,
        .chat-bridge button:disabled {
          background: #6c757d;
          cursor: not-allowed;
        }
        .mentions-toggle {
          margin-top: 12px;
          display: flex !important;
          align-items: flex-start;
          gap: 8px;
          font-weight: 500 !important;
          color: #495057;
        }
        .mentions-toggle input {
          margin-top: 3px;
        }
        .company-loading {
          margin-top: 12px;
          color: #0d6efd;
          font-weight: 600;
        }
        .company-error,
        .partial-warning {
          margin-top: 12px;
          padding: 10px 12px;
          border-radius: 6px;
          background: #fff3cd;
          border: 1px solid #ffc107;
          color: #664d03;
        }
        .company-results {
          background: white;
          border: 1px solid #dee2e6;
          border-radius: 8px;
          padding: 18px;
        }
        .company-results h2 {
          font-size: 20px;
          margin-bottom: 6px;
        }
        .results-summary {
          font-weight: 700;
          color: #495057;
        }
        .results-reminder {
          margin-top: 8px;
          font-style: italic;
          color: #495057;
        }
        .record-list {
          margin-top: 16px;
          display: grid;
          gap: 12px;
        }
        .record-card {
          position: relative;
          border: 1px solid #dee2e6;
          border-left: 4px solid #6c757d;
          border-radius: 8px;
          padding: 16px;
          background: #ffffff;
        }
        .record-card.wrc {
          border-left-color: #0d6efd;
        }
        .record-card.hsa {
          border-left-color: #dc3545;
        }
        .record-kicker {
          text-transform: uppercase;
          letter-spacing: 0;
          font-size: 12px;
          font-weight: 800;
          color: #6c757d;
          margin-bottom: 6px;
        }
        .record-card h3 {
          padding-right: 90px;
          margin-bottom: 6px;
          font-size: 18px;
        }
        .record-meta {
          color: #495057;
          font-weight: 600;
          margin-bottom: 10px;
        }
        .confidence-badge {
          position: absolute;
          top: 14px;
          right: 14px;
          padding: 4px 8px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 800;
          text-transform: uppercase;
        }
        .confidence-badge.high {
          background: #d1e7dd;
          color: #0f5132;
        }
        .confidence-badge.medium {
          background: #fff3cd;
          color: #664d03;
        }
        .confidence-badge.low {
          background: #f8d7da;
          color: #842029;
        }
        .source-button {
          display: inline-block;
          margin-top: 12px;
          color: #0d6efd;
          font-weight: 700;
        }
        .source-unavailable {
          margin-top: 12px;
          color: #6c757d;
          font-size: 13px;
        }
        .chat-bridge {
          margin-top: 18px;
          padding: 16px;
          border-radius: 8px;
          background: #f1f5f9;
          border: 1px solid #d8e0ea;
        }
        .chat-bridge h3 {
          margin-bottom: 8px;
        }
        .chat-bridge p {
          margin-bottom: 12px;
          color: #495057;
          line-height: 1.5;
        }

        /* ===========================
           FOOTER
           =========================== */
        .footer {
          background: #f8f9fa;
          padding: 12px 20px;
          text-align: center;
          font-size: 13px;
          color: #6c757d;
          border-top: 1px solid #dee2e6;
          flex-shrink: 0;
        }
        .footer a {
          color: #0d6efd;
        }

        /* ===========================
           TYPING INDICATOR
           =========================== */
        .typing-indicator {
          display: flex;
          gap: 4px;
          padding: 4px 0;
        }
        .typing-indicator span {
          width: 8px;
          height: 8px;
          background: #6c757d;
          border-radius: 50%;
          animation: bounce 1.4s infinite;
        }
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-6px); }
        }

        /* ===========================
           MOBILE RESPONSIVE (≤768px)
           =========================== */
        @media (max-width: 768px) {
          /* Disclaimer condenses */
          .disclaimer-banner {
            padding: 8px 12px;
          }
          .disclaimer-content {
            font-size: 12px;
          }
          .time-limit-warning {
            font-size: 11px;
          }
          .mode-toggle-wrap {
            padding: 8px 12px;
          }
          .mode-toggle {
            width: 100%;
          }
          .mode-tab {
            flex: 1;
            padding: 9px 10px;
          }

          /* Sidebar becomes slide-out drawer */
          .sidebar {
            position: fixed;
            top: 0;
            left: 0;
            width: 85%;
            max-width: 320px;
            height: 100%;
            z-index: 1000;
            transform: translateX(-100%);
            transition: transform 0.3s ease;
            padding: 16px;
            padding-top: 56px;
            box-shadow: none;
            border-right: none;
          }
          .sidebar.sidebar-open {
            transform: translateX(0);
            box-shadow: 4px 0 20px rgba(0, 0, 0, 0.15);
          }
          .sidebar-close {
            display: flex;
            align-items: center;
            justify-content: center;
            position: absolute;
            top: 12px;
            right: 12px;
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            font-size: 18px;
            width: 36px;
            height: 36px;
            cursor: pointer;
            color: #6c757d;
            line-height: 1;
          }

          /* Overlay behind drawer */
          .sidebar-overlay {
            display: block;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.4);
            z-index: 999;
          }

          /* Mobile topbar with toggle */
          .mobile-topbar {
            display: flex;
            padding: 8px 12px;
            border-bottom: 1px solid #dee2e6;
            background: #f8f9fa;
            flex-shrink: 0;
          }
          .sidebar-toggle {
            display: flex;
            align-items: center;
            gap: 8px;
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 14px;
            font-family: inherit;
            color: #0d6efd;
            cursor: pointer;
            min-height: 40px;
          }
          .sidebar-toggle svg {
            flex-shrink: 0;
          }

          /* Chat messages wider on mobile */
          .message {
            max-width: 90%;
          }

          /* Welcome message adapts */
          .welcome-message {
            padding: 20px;
            margin: 0 4px;
          }
          .welcome-message h2 {
            font-size: 20px;
          }

          /* Messages area padding */
          .messages {
            padding: 12px;
          }
          .chat-toolbar {
            padding: 8px 12px 0;
            flex-direction: column;
            align-items: stretch;
          }

          /* Input area */
          .input-area {
            padding: 12px;
            gap: 8px;
          }
          .input-area input {
            padding: 10px 12px;
          }
          .input-area button {
            padding: 10px 16px;
          }

          /* Footer */
          .footer {
            padding: 10px 12px;
            font-size: 11px;
          }
          .company-panel {
            padding: 12px;
          }
          .company-info-box,
          .company-form,
          .company-results {
            padding: 14px;
          }
          .company-form-row {
            flex-direction: column;
          }
          .record-card h3 {
            padding-right: 0;
            margin-top: 28px;
          }
        }

        /* ===========================
           SMALL MOBILE (≤380px)
           =========================== */
        @media (max-width: 380px) {
          .welcome-message {
            padding: 16px;
          }
          .welcome-message h2 {
            font-size: 18px;
          }
          .welcome-message ul {
            padding-left: 20px;
            font-size: 14px;
          }
          .input-area button {
            padding: 10px 12px;
            font-size: 14px;
          }
        }
      `}</style>
    </div>
  );
}
