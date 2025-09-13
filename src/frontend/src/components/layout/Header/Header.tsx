import { Divider, Switch, Title2 } from "@fluentui/react-components";
import { CopyRegular } from '@fluentui/react-icons';

import "./Header.css";

interface Props {
    toggleMode: (mode: boolean) => void;
    darkMode: boolean;
    isAdmin?: boolean;
}

export const Header = ({ toggleMode, darkMode, isAdmin: propIsAdmin }: Props) => {
    // read session and MI state from localStorage (best-effort)
    const getSessionId = () => {
        try { return localStorage.getItem('session_id') || ''; } catch(e) { return ''; }
    };

    const getMiState = () => {
        try { return localStorage.getItem('use_managed_identity') === 'true'; } catch(e) { return false; }
    };

    const sessionId = getSessionId();
    const miState = getMiState();
    const injectedIsAdmin = Boolean(window.__RUNTIME_CONFIG__?.['IS_ADMIN'] === true || window.__RUNTIME_CONFIG__?.['IS_ADMIN'] === 'true');
    const isAdmin = typeof propIsAdmin === 'boolean' ? propIsAdmin : injectedIsAdmin;

    const onToggleMi = (_: any, ev: any) => {
        try { localStorage.setItem('use_managed_identity', ev.checked ? 'true' : 'false'); } catch(e) {}
        try { if (!localStorage.getItem('session_id')) { localStorage.setItem('session_id', `sid-${Date.now()}`); } } catch(e) {}

        // show a small toast by rendering a transient MessageBar in the header area.
        const toast = document.createElement('div');
        toast.className = 'mi-toast';
        toast.innerHTML = `Auth mode changed for this session`;
        const btn = document.createElement('button');
        btn.className = 'mi-toast-reload';
        btn.textContent = 'Reload';
        btn.onclick = () => { location.reload(); };
        toast.appendChild(btn);
        document.body.appendChild(toast);
        setTimeout(() => { try { toast.remove(); } catch(e) {} }, 5000);

        // Auto-reload after a short delay so long-lived connections (SSE/fetchEventSource) pick up the new auth mode
        try {
            setTimeout(() => {
                console.info('Reloading to apply session auth mode change');
                location.reload();
            }, 800);
        } catch (e) {
            // ignore
        }
    };

    const copySessionToClipboard = async () => {
        try {
            const sid = getSessionId();
            if (sid && navigator.clipboard) {
                await navigator.clipboard.writeText(sid);
                // transient feedback using a small MessageBar inserted near header
                const msg = document.createElement('div');
                msg.className = 'mi-toast';
                msg.textContent = 'Session id copied';
                document.body.appendChild(msg);
                setTimeout(() => { try { msg.remove(); } catch(e) {} }, 2000);
            }
        } catch (e) {
            // ignore
        }
    };

    return (
        <>
            <div className="header">
                <Title2> Multimodal RAG</Title2>
                <div className="header-right">
                    <div className="session-badge" title={sessionId ? sessionId : 'no session'}>
                        <span className="session-text">{sessionId ? `${sessionId}` : 'no-session'}</span>
                        <button className="copy-btn" onClick={copySessionToClipboard} aria-label="Copy session id"><CopyRegular /></button>
                        <span className={`mi-indicator ${miState ? 'on' : 'off'}`}>{miState ? 'MI: on' : 'MI: off'}</span>
                        <span className={`admin-indicator ${isAdmin ? 'admin' : 'user'}`}>{isAdmin ? 'ADMIN' : 'USER'}</span>
                    </div>

                    <Switch
                        checked={darkMode}
                        label={`Dark Mode`}
                        onChange={() => {
                            toggleMode(!darkMode);
                        }}
                    />
                    <div style={{ width: 12 }} />
                    <Switch
                        checked={miState}
                        label={`Use Managed Identity`}
                        onChange={onToggleMi}
                    />
                </div>
            </div>
            <Divider />
        </>
    );
};
