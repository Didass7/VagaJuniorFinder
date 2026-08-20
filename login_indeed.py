from __future__ import annotations
import os
import sys
import json
import time
import logging
from typing import Optional, Dict, Any

def save_indeed_session() -> bool:
    """
    Opens a visible browser for 60 seconds to allow the user (or auto-action)
    to pass Cloudflare Turnstile once. Extracts and persists valid cookies
    to data/indeed_cookies.json for the automated pipeline.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("==================================================")
    print("🔓 Indeed Session Generator (Cloudflare Bypass)")
    print("==================================================")
    print("A abrir janela do navegador para pt.indeed.com...")
    print("👉 Se aparecer a caixa 'Verificação de Segurança / Confirme que é humano',")
    print("   clica nela na janela do navegador que se abrir.")
    print("O script detetará automaticamente a resolução e guardará a sessão.\n")

    os.makedirs("data", exist_ok=True)
    cookies_path = os.path.join("data", "indeed_cookies.json")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright não está instalado. Execute: pip install playwright && playwright install chromium")
        return False

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized"
            ]
        )
        context = browser.new_context(
            user_agent=user_agent,
            locale="pt-PT",
            viewport=None
        )
        page = context.new_page()
        page.add_init_script("delete Object.getPrototypeOf(navigator).webdriver;")

        url = "https://pt.indeed.com/jobs?q=python&l=Portugal&sort=date"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"Erro inicial ao aceder: {e}")

        start_t = time.time()
        solved = False
        print("Aguardando verificação (máx 60 segundos)...")

        while time.time() - start_t < 60:
            try:
                title = page.title()
                cards = page.query_selector_all("div.job_seen_beacon, td.resultContent, div.cardOutline")
                if len(cards) > 0 or ("Security Check" not in title and "Just a moment" not in title and "Indeed" in title):
                    solved = True
                    print(f"\n✅ Verificação ultrapassada com sucesso! ({len(cards)} vagas detetadas na página)")
                    break
            except Exception:
                pass
            time.sleep(1)

        if solved:
            cookies = context.cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            data = {
                "cookies": cookie_str,
                "user_agent": user_agent,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(cookies_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"🎉 Sessão guardada com sucesso em: {cookies_path}")
            print("Agora o IndeedScraper utilizará esta sessão automaticamente!")
            browser.close()
            return True
        else:
            print("⚠️ Tempo limite de 60s atingido sem resolução do desafio.")
            browser.close()
            return False

if __name__ == "__main__":
    save_indeed_session()
