import sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

old = '''        org_id = None
        user_id = None
        if r_sess.status_code == 200:
            sess_data = r_sess.json()
            logger.info(f\"[DEBUG] Session response type: {type(sess_data).__name__}, keys: {list(sess_data.keys()) if isinstance(sess_data, dict) else 'N/A'}\")
            # Session may be nested or flat
            session = sess_data.get(\"session\") or sess_data.get(\"data\", {}).get(\"session\") or sess_data
            if isinstance(session, dict):
                org_id = session.get(\"activeOrganizationId\") or session.get(\"organizationId\") or sess_data.get(\"organizationId\")
                user_id = session.get(\"userId\") or session.get(\"user\", {}).get(\"id\") or sess_data.get(\"userId\")
            logger.info(f\"[+] Session OK: org_id={org_id}, user_id={user_id}\")
        else:
            logger.warning(f\"[!] Session query failed: {r_sess.status_code}\")'''

new = '''        org_id = None
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

if old in c:
    c = c.replace(old, new)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print('FIXED')
else:
    print('NOT FOUND')
    lines = c.split('\n')
    for i in range(610, min(628, len(lines))):
        print(f'{i}: {repr(lines[i])}')