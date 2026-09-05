import sys
p = sys.argv[1]
with open(p, 'r', encoding='utf-8') as f:
    c = f.read()

# Fix API keys page navigation - wait for login check
old = '''        if not api_key:
            logger.info(\"[API KEY] REST creation failed, trying UI fallback...\")
            await page.goto(f\"{HOPLITE_APP}/settings/api-keys\", wait_until=\"domcontentloaded\", timeout=20000)
            await asyncio.sleep(4)
            await page.screenshot(path=str(SCREENSHOTS_DIR / f\"api_keys_page_{login}_{ts()}.png\"))
            m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
            if m:
                api_key = m.group(0)
                logger.info(f\"[API KEY] Extracted from UI: {api_key[:16]}...{api_key[-6:]}\")'''

new = '''        if not api_key:
            logger.info(\"[API KEY] REST creation failed, trying UI fallback...\")
            await page.goto(f\"{HOPLITE_APP}/settings/api-keys\", wait_until=\"networkidle\", timeout=30000)
            await asyncio.sleep(3)
            # Check if we're logged in - look for login page
            if \"Sign In\" in await page.title() or \"Login\" in await page.title() or await page.locator('button:has-text(\"Sign In\")').count() > 0:
                logger.warning(\"[!] Not logged in to Hoplite, can't access API keys page\")
            else:
                await page.screenshot(path=str(SCREENSHOTS_DIR / f\"api_keys_page_{login}_{ts()}.png\"))
                # Try to find API key in page content
                page_html = await page.content()
                m = re.search(r'hop_[a-zA-Z0-9_-]{40,}', page_html)
                if m:
                    api_key = m.group(0)
                    logger.info(f\"[API KEY] Extracted from UI: {api_key[:16]}...{api_key[-6:]}\")
                else:
                    # Try clicking create button
                    create_btn = page.locator('button:has-text(\"Create\")')
                    if await create_btn.count() > 0:
                        await create_btn.first.click()
                        await asyncio.sleep(2)
                        name_input = page.locator('input[placeholder*=\"name\"]')
                        if await name_input.count() > 0:
                            await name_input.first.fill(f\"{login}-key\")
                            confirm = page.locator('button:has-text(\"Create\"):not(:has-text(\"Repository\"))')
                            if await confirm.count() > 0:
                                await confirm.last.click()
                                await asyncio.sleep(3)
                                m2 = re.search(r'hop_[a-zA-Z0-9_-]{40,}', await page.content())
                                if m2:
                                    api_key = m2.group(0)
                                    logger.info(f\"[API KEY] Created via UI: {api_key[:16]}...{api_key[-6:]}\")'''

if old in c:
    c = c.replace(old, new)
    print('APIKEYS_FIXED')
else:
    print('APIKEYS_NOT_FOUND')

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)
print('DONE')