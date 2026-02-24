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
  const messagesEndRef = useRef<HTMLDivElement>(null);

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

    try {
      const history = messages.slice(-10).map(m => ({
        role: m.role,
        content: m.content
      }));

      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: input,
          history
        })
      });

      const data = await response.json();

      const assistantMessage: Message = {
        role: 'assistant',
        content: data.answer,
        sources: data.sources,
        officialLinks: data.official_links,
        hasAuthoritativeSources: data.has_authoritative_sources
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
                
                {msg.sources && msg.sources.length > 0 && (
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
        .no-sources-warning {
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
