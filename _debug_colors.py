import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://127.0.0.1:8000/accounts/login/")
        await page.fill('input[name="username"]', "etu_esfe9")
        await page.fill('input[name="password"]', "TestPass123!")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        await page.goto("http://127.0.0.1:8000/portal/student-dashboard/")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)
        await page.evaluate("""() => {
            const root = document.querySelector('.student-dashboard-page');
            Alpine.$data(root).toggleDarkMode();
            Alpine.$data(root).goToSection('settings', 'Parametres');
        }""")
        await page.wait_for_timeout(2000)
        res = await page.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('*')).filter(e => e.children.length === 0 && /gestion du compte|COMPTE ETUDIANT|62%/i.test(e.textContent || ''));
            return els.map(e => ({
                tag: e.tagName, cls: e.className, text: (e.textContent||'').trim().slice(0,40),
                color: getComputedStyle(e).color,
                bg: getComputedStyle(e).backgroundColor,
                parentBg: getComputedStyle(e.parentElement).backgroundColor,
                parentCls: e.parentElement.className,
            }));
        }""")
        print("count:", len(res))
        for r in res:
            print(r)
        await browser.close()


asyncio.run(main())
