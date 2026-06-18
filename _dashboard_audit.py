import asyncio
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"

SECTIONS = [
    ("overview", "Tableau de bord"),
    ("courses", "Mes cours"),
    ("schedule", "Calendrier"),
    ("academics", "Academique"),
    ("messages", "Notifications"),
    ("teachers", "Encadrement"),
    ("settings", "Parametres"),
    ("shop", "Boutique"),
    ("diplomas", "Mes diplomes"),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        # login
        await page.goto(f"{BASE}/accounts/login/")
        await page.fill('input[name="username"]', "etu_esfe9")
        await page.fill('input[name="password"]', "TestPass123!")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        await page.goto(f"{BASE}/portal/student-dashboard/")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)

        has_alpine = await page.evaluate("() => typeof window.Alpine")
        print("Alpine:", has_alpine)

        # close any popup modals (cookie consent, shop required, etc.)
        for _ in range(3):
            closed = await page.evaluate("""
                () => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const btn = btns.find(b => /^(fermer|j'ai compris|compris|continuer|refuser)$/i.test((b.textContent || '').trim()));
                    if (btn) { btn.click(); return true; }
                    return false;
                }
            """)
            if not closed:
                break
            await page.wait_for_timeout(600)

        # force-remove any remaining overlay (shop required modal etc.) for clean screenshots
        await page.evaluate("""
            () => {
                document.querySelectorAll('#studentShopRequiredMount, #studentInternalRulesMount, [id*="cookie" i], [class*="cookie" i]').forEach(el => {
                    if (el.id === 'studentShopRequiredMount' || el.id === 'studentInternalRulesMount') {
                        el.innerHTML = '';
                    } else {
                        el.remove();
                    }
                });
            }
        """)

        for idx, (target, label) in enumerate(SECTIONS):
            await page.evaluate(f"""
                () => {{
                    const root = document.querySelector('.student-dashboard-page');
                    const data = Alpine.$data(root);
                    data.goToSection('{target}', '{label}');
                }}
            """)
            await page.wait_for_timeout(2200)
            await page.screenshot(path=f"_audit_light_{target}.png", full_page=True)

        # toggle dark mode
        await page.evaluate("""
            () => {
                const root = document.querySelector('.student-dashboard-page');
                const data = Alpine.$data(root);
                data.toggleDarkMode();
            }
        """)
        await page.wait_for_timeout(600)

        for idx, (target, label) in enumerate(SECTIONS):
            await page.evaluate(f"""
                () => {{
                    const root = document.querySelector('.student-dashboard-page');
                    const data = Alpine.$data(root);
                    data.goToSection('{target}', '{label}');
                }}
            """)
            await page.wait_for_timeout(2200)
            await page.screenshot(path=f"_audit_dark_{target}.png", full_page=True)

        await browser.close()


asyncio.run(main())
