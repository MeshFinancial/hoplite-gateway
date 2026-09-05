import sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix: extract session from page cookies via JS, NOT via separate requests call
old = '''        cookie_header = \"; \".join(f\"{k}={v}\" for k, v in hop_cookies.items())
        r_sess = requests.get(\"https://api.hoplite.sh/api/auth/get-session\", headers={
            \"Cookie\": cookie_header,
            \"Origin\": \"https://app.hoplite.sh\",
            \"User-Agent\": \"Mozilla/5.0\"
        }, timeout=10)

        org_id = None
        user_id = None
        session_data = {}
        if r_sess.status_code == 200:
            try:
                sess_data = r_sess.json()
                if isinstance(sess_data, dict):
                    s = sess_data.get('session') or sess_data.get('data', {}).get('session') or sess_data
                    if isinstance(s, dict):
                        org_id = s.get('activeOrganizationId') or s.get('organizationId') or sess_data.get('organizationId')
                        user_id = s.get('userId') or s.get('user', {}).get('id') or sess_data.get('userId')
                logger.info(f'[+] Session: org_id={org_id}, user_id={user_id}')
            except Exception as e:
                logger.warning(f'[!] Session parse error: {e}')
        else:
            logger.warning(f'[!] Session query failed: {r_sess.status_code}')'''

new = '''        # Try to get session info from page JS context
        org_id = None
        user_id = None
        try:
            session_info = await page.evaluate(''' + "'''" + '''() => {
                try {
                    const req = new XMLHttpRequest();
                    req.open('GET', 'https://api.hoplite.sh/api/auth/get-session', false);
                    req.withCredentials = true;
                    req.send();
                    return JSON.parse(req.responseText);
                } catch(e) { return {error: e.message}; }
            }''' + "'''" + ''')
            if isinstance(session_info, dict) and 'error' not in session_info:
                s = session_info.get('session') or session_info.get('data', {}).get('session') or session_info
                if isinstance(s, dict):
                    org_id = s.get('activeOrganizationId') or s.get('organizationId') or session_info.get('organizationId')
                    user_id = s.get('userId') or s.get('user', {}).get('id') or session_info.get('userId')
                logger.info(f'[+] Session (JS): org_id={org_id}, user_id={user_id}')
            else:
                logger.warning(f'[!] Session JS fetch failed: {session_info}')
        except Exception as e:
            logger.warning(f'[!] Session JS error: {e}')'''

if old in c:
    c = c.replace(old, new)
    print('SESSION_FIXED')
else:
    print('SESSION_NOT_FOUND')

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('DONE')