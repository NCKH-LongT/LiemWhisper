# Student & Admin web — pilot

```bash
cd tool/client
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Browse http://localhost:3000 (requires backend started at 8000).

### Implemented
- Consent checkbox and short survey; server issues a pseudonymous participant token.
- Course list and published prompts assigned from API.
- Browser MediaRecorder (Chrome/Edge WebM/Opus), playback, re-record and one upload per prompt.
- Basic admin tools: create courses, create/publish prompts, list review items and submit verbatim review.

### Known limitations / before real study
- Prototype admin key is entered in the browser: unsuitable for public deployment; replace with secure session-based RBAC.
- Browser holds participant token in memory only; user must copy it securely to return.
- Admin audio playback currently requires authenticated API call separately; no player in this initial interface.
- No withdraw/delete account flow or ethics-approved complete consent disclosure.
- No recording time limit or accessible/mobile microphone compatibility testing yet; server validates maximum upload bytes only.
- No authenticated export/analytics yet. Google Drive storage is configured on backend, not browser.
- Do not collect actual participant data before institutionally approved research consent and operational security controls.
