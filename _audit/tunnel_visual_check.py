"""Recette navigateur ciblée du tunnel de découverte des formations."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:8011"
AUDIT_DIR = Path(__file__).resolve().parent
DIRECT_URL = (
    f"{BASE_URL}/admissions/?step=3&branch=bamako-centre"
    "&formation=licence-sciences-infirmieres"
)


def main():
    results = {"viewports": {}, "draft_restore": {}, "classic": {}, "errors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        for name, width, height in (
            ("mobile", 390, 844),
            ("tablet", 820, 1180),
            ("desktop", 1440, 1000),
        ):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on(
                "console",
                lambda message, viewport=name: results["errors"].append(
                    f"{viewport}:console:{message.type}:{message.text}"
                )
                if message.type == "error"
                else None,
            )
            page.on(
                "pageerror",
                lambda error, viewport=name: results["errors"].append(
                    f"{viewport}:page:{error}"
                ),
            )
            response = page.goto(DIRECT_URL, wait_until="networkidle")
            reject_button = page.get_by_role("button", name="Refuser")
            if reject_button.is_visible():
                reject_button.click()
            page.locator("#step3-documents-list").wait_for(state="visible")
            page.screenshot(
                path=AUDIT_DIR / f"tunnel_{name}.png",
                full_page=False,
                animations="disabled",
            )
            body_text = page.locator("body").inner_text()
            dimensions = page.evaluate(
                """() => ({
                    clientWidth: document.documentElement.clientWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    clientHeight: document.documentElement.clientHeight,
                    scrollHeight: document.documentElement.scrollHeight
                })"""
            )
            results["viewports"][name] = {
                "status": response.status if response else None,
                "title": page.title(),
                "programme_visible": "Licence en sciences infirmieres" in body_text,
                "documents_visible": page.get_by_text(
                    "Copie du diplome", exact=False
                ).first.is_visible(),
                "horizontal_overflow": dimensions["scrollWidth"]
                > dimensions["clientWidth"] + 1,
                "dimensions": dimensions,
            }
            page.close()

        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{BASE_URL}/admissions/", wait_until="networkidle")
        page.get_by_role("button", name="Commencer ma candidature").click()
        page.locator('input[data-field="last_name"]').fill("Traore")
        page.locator('input[data-field="first_name"]').fill("Awa")
        page.locator('input[data-field="city"]').fill("Bamako")
        page.get_by_role("button", name="Suivant").click()
        page.locator('input[data-field="email"]').fill("awa.visual@example.com")
        page.locator('input[data-field="phone"]').fill("+22370000000")
        page.locator('input[data-field="birth_date"]').fill("2002-05-20")
        page.get_by_role("button", name="Féminin").click()
        page.locator("button").filter(has_text="Licence").first.click()
        page.reload(wait_until="networkidle")
        results["draft_restore"] = {
            "step_two_visible": page.get_by_text("Dites-nous en un peu plus", exact=False).is_visible(),
            "last_name": page.locator('input[name="last_name"]').input_value(),
            "email": page.locator('input[name="email"]').input_value(),
            "gender": page.locator('input[name="gender"]').input_value(),
            "level": page.locator('input[name="current_level"]').input_value(),
        }
        page.close()

        page = browser.new_page(viewport={"width": 1280, "height": 900})
        list_response = page.goto(f"{BASE_URL}/formations/", wait_until="networkidle")
        list_visible = "Licence en sciences infirmieres" in page.locator("body").inner_text()
        detail_response = page.goto(
            f"{BASE_URL}/formations/licence-sciences-infirmieres/",
            wait_until="networkidle",
        )
        results["classic"] = {
            "list_status": list_response.status if list_response else None,
            "list_programme_visible": list_visible,
            "detail_status": detail_response.status if detail_response else None,
            "detail_programme_visible": "Licence en sciences infirmieres"
            in page.locator("body").inner_text(),
        }
        page.close()
        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
