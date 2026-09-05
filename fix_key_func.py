import sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

old = '''def create_api_key_via_rest(hop_cookies: dict, org_id: str, login: str) -> Optional[str]:
    \"\"\"Directly calls Better-Auth REST API to generate an organization API key.\"\"\"
    logger.info(f\"[API KEY] Generating via Better-Auth REST for org {org_id}...\")
    cookie_header = \"; \".join(f\"{k}={v}\" for k, v in hop_cookies.items())
    headers = {
        \"Cookie\": cookie_header,
        \"Origin\": \"https://app.hoplite.sh\",
        \"Referer\": \"https://app.hoplite.sh/settings/api-keys\",
        \"Content-Type\": \"application/json\",
        \"User-Agent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\"
    }
    payload = {
        \"name\": f\"{login}-gateway-key\",
        \"organizationId\": org_id
    }
    try:
        r = requests.post(f\"{HOPLITE_API}/api/auth/api-key/create\", headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            key = data.get(\"key\")
            if key:
                logger.info(f\"\\U0001f525 [API KEY] CREATED: {key[:16]}...{key[-6:]} \\U0001f525\")
                return key
            else:
                logger.warning(f\"[API KEY] Response OK but no key: {data}\")
        else:
            logger.warning(f\"[API KEY] Creation failed ({r.status_code}): {r.text[:200]}\")
    except Exception as e:
        logger.error(f\"[API KEY] Creation error: {e}\")
    return None'''

new = '''def create_api_key_via_rest(hop_cookies: dict, org_id: Optional[str], login: str) -> Optional[str]:
    \"\"\"Directly calls Better-Auth REST API to generate an organization API key.\"\"\"
    if not org_id:
        logger.warning(\"[API KEY] No org_id, cannot create via REST\")
        return None
    logger.info(f\"[API KEY] Generating via Better-Auth REST for org {org_id}...\")
    cookie_header = \"; \".join(f\"{k}={v}\" for k, v in hop_cookies.items())
    headers = {
        \"Cookie\": cookie_header,
        \"Origin\": \"https://app.hoplite.sh\",
        \"Referer\": \"https://app.hoplite.sh/settings/api-keys\",
        \"Content-Type\": \"application/json\",
        \"User-Agent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\"
    }
    payload = {
        \"name\": f\"{login}-gateway-key\",
        \"organizationId\": org_id
    }
    try:
        r = requests.post(f\"{HOPLITE_API}/api/auth/api-key/create\", headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            key = data.get(\"key\")
            if key:
                logger.info(f\"\\U0001f525 [API KEY] CREATED: {key[:16]}...{key[-6:]} \\U0001f525\")
                return key
            else:
                logger.warning(f\"[API KEY] Response OK but no key: {data}\")
        else:
            logger.warning(f\"[API KEY] Creation failed ({r.status_code}): {r.text[:200]}\")
    except Exception as e:
        logger.error(f\"[API KEY] Creation error: {e}\")
    return None'''

if old in c:
    c = c.replace(old, new)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print('FIXED')
else:
    print('NOT FOUND')
    # Try to find the function
    idx = c.find('def create_api_key_via_rest')
    if idx >= 0:
        lines = c[:idx+200].split('\\n')
        line_num = c[:idx].count('\\n') + 1
        print(f'Found at line {line_num}')
        for i in range(max(0, line_num-1), min(len(lines), line_num+10)):
            print(f'{i+1}: {repr(lines[i])}')