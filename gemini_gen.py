"""
gemini_gen.py — Gemini generation with live Telegram progress updates
"""
import os
import asyncio
import time
import base64
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

BRAVE_PATH   = "/usr/bin/brave-browser"
RESPONSE_SEL = "model-response"
OUTPUT_DIR   = os.path.expanduser("~/AURA-Automation/outputs")
CHAR_REF     = "/home/pratay-karali/Downloads/aura_new.jpeg"


def caption_prompt(topic):
    return (
        "Write a short punchy Instagram caption (no title, no intro, "
        "just 3-4 lines + hashtags) for a Pixar animated girl in this scene: " + topic
    )


def image_prompt(topic):
    return (
        "Look at the character image I just uploaded. Generate a Pixar/Disney 3D render "
        "of THIS EXACT same girl (same face, dark brown skin, blue hair, "
        "orange hoodie, purple shorts, blue sneakers) in this scene: "
        + topic +
        ". Full body visible, cinematic lighting, 9:16 vertical format, no text, no watermarks."
    )


async def _wait_stable(page, prev_count, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await page.locator(RESPONSE_SEL).count() > prev_count:
            break
        await asyncio.sleep(1)
    else:
        return False
    last = page.locator(RESPONSE_SEL).last
    prev_text, ticks = "", 0
    deadline2 = time.time() + 60
    while time.time() < deadline2:
        cur = await last.inner_text()
        if cur == prev_text and cur.strip():
            ticks += 1
            if ticks >= 3:
                return True
        else:
            ticks = 0
        prev_text = cur
        await asyncio.sleep(1)
    return False


async def _upload_file(page):
    """Upload character reference via file chooser interception."""
    print("[Upload] Looking for + button...")

    plus_selectors = [
        'button[aria-label="Add image"]',
        'button[aria-label*="Add"]',
        'button[aria-label*="attach" i]',
        'button[aria-label*="upload" i]',
        'button[aria-label*="image" i]',
    ]

    for sel in plus_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1500):
                print(f"[Upload] Clicking: {sel}")
                async with page.expect_file_chooser(timeout=6000) as fc_info:
                    await btn.click()
                fc = await fc_info.value
                await fc.set_files(CHAR_REF)
                await asyncio.sleep(5)
                print("[Upload] ✓")
                return True
        except:
            continue

    # JS fallback
    try:
        clicked = await page.evaluate("""() => {
            const box = document.querySelector('div[role="textbox"]');
            if (!box) return false;
            let container = box.parentElement;
            for (let i = 0; i < 6; i++) {
                if (!container) break;
                const btns = container.querySelectorAll('button');
                for (const btn of btns) {
                    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                    if (label.includes('add') || label.includes('attach') ||
                        label.includes('upload') || label.includes('image')) {
                        btn.click();
                        return true;
                    }
                }
                container = container.parentElement;
            }
            return false;
        }""")
        if clicked:
            async with page.expect_file_chooser(timeout=5000) as fc_info:
                pass
            fc = await fc_info.value
            await fc.set_files(CHAR_REF)
            await asyncio.sleep(5)
            print("[Upload] JS fallback ✓")
            return True
    except:
        pass

    # Direct input fallback
    try:
        fi = page.locator('input[type="file"]').first
        await fi.wait_for(state="attached", timeout=5000)
        await fi.set_input_files(CHAR_REF)
        await asyncio.sleep(5)
        print("[Upload] Direct input ✓")
        return True
    except Exception as e:
        print(f"[Upload] All failed: {e}")

    return False


async def _wait_for_image(page, timeout=300, progress_cb=None):
    """
    Wait for image generation with live progress callbacks to Telegram.
    Sends status every 30s so user isn't staring at nothing.
    """
    deadline = time.time() + timeout
    start = time.time()
    last_update = time.time()
    update_interval = 30  # send progress every 30 seconds

    print(f"[Image] Waiting up to {timeout}s...")

    while time.time() < deadline:
        src = await page.evaluate(f"""() => {{
            const rs = document.querySelectorAll('{RESPONSE_SEL}');
            if (!rs.length) return null;
            const last = rs[rs.length - 1];
            const txt = (last.innerText || '').toLowerCase();
            const refused = ["can't generate", "cannot create", "unable to generate",
                             "i'm not able", "i can't help", "i'm unable"];
            if (refused.some(r => txt.includes(r))) return 'REFUSED';
            if (txt.includes('creating your image')) return 'GENERATING';
            const imgs = [...last.querySelectorAll('img')].filter(img => {{
                const s = img.src || '';
                return img.naturalWidth >= 200 && img.naturalHeight >= 200 &&
                       !s.includes('avatar') && !s.includes('icon') && !s.includes('logo');
            }});
            if (!imgs.length) return null;
            imgs.sort((a,b) => (b.naturalWidth*b.naturalHeight)-(a.naturalWidth*a.naturalHeight));
            return imgs[0].src;
        }}""")

        if src == 'REFUSED':
            return None
        if src and src != 'GENERATING':
            elapsed = int(time.time() - start)
            print(f"[Image] Done in {elapsed}s ✓")
            return src

        # Send progress update to Telegram every 30s
        now = time.time()
        if progress_cb and (now - last_update) >= update_interval:
            elapsed = int(now - start)
            remaining = int(deadline - now)
            status = "🖌️ Gemini is painting..." if src == 'GENERATING' else "⏳ Starting generation..."
            await progress_cb(f"{status}\n_{elapsed}s elapsed, up to {remaining}s remaining_")
            last_update = now

        remaining = int(deadline - time.time())
        print(f"[Image] {'Generating' if src == 'GENERATING' else 'Waiting'}... {remaining}s left")
        await asyncio.sleep(5)

    return None


async def _download_image(page, context, img_src, save_path):
    """Download just the image pixels — no UI chrome."""

    # Method 1: Playwright context fetch
    try:
        resp = await context.request.get(img_src, timeout=30000)
        if resp.ok:
            data = await resp.body()
            if len(data) > 10000:
                with open(save_path, "wb") as f:
                    f.write(data)
                print(f"[Download] Context fetch ✓ — {len(data):,}b")
                return True
    except Exception as e:
        print(f"[Download] M1: {e}")

    # Method 2: Navigate to URL
    try:
        p2 = await context.new_page()
        r = await p2.goto(img_src, timeout=30000)
        data = await r.body()
        await p2.close()
        if len(data) > 10000:
            with open(save_path, "wb") as f:
                f.write(data)
            print(f"[Download] Navigate ✓ — {len(data):,}b")
            return True
    except Exception as e:
        print(f"[Download] M2: {e}")

    # Method 3: Canvas export — full resolution, zero chrome
    try:
        safe = img_src.replace('`', '\\`')
        b64 = await page.evaluate(f"""async () => {{
            const img = [...document.querySelectorAll('img')].find(i => i.src===`{safe}`);
            if (!img) return null;
            await new Promise(r => {{ if(img.complete) r(); else {{img.onload=r;img.onerror=r;}} }});
            const c = document.createElement('canvas');
            c.width = img.naturalWidth; c.height = img.naturalHeight;
            c.getContext('2d').drawImage(img, 0, 0);
            return c.toDataURL('image/png').split(',')[1];
        }}""")
        if b64:
            raw = base64.b64decode(b64)
            if len(raw) > 10000:
                with open(save_path, "wb") as f:
                    f.write(raw)
                print(f"[Download] Canvas ✓ — {len(raw):,}b")
                return True
    except Exception as e:
        print(f"[Download] M3: {e}")

    # Method 4: Element screenshot (crops to exact img bounds)
    try:
        el = page.locator(f'img[src="{img_src}"]').first
        await el.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await el.screenshot(path=save_path, type="png")
        size = os.path.getsize(save_path)
        if size > 10000:
            print(f"[Download] Element screenshot ✓ — {size:,}b")
            return True
    except Exception as e:
        print(f"[Download] M4: {e}")

    return False


async def generate(topic: str, progress_cb=None) -> dict:
    """
    Main entry. progress_cb(msg) is called with status updates for Telegram.
    Returns: { "caption": str, "image_path": str, "error": str|None }
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    result = {"caption": None, "image_path": None, "error": None}

    async with Stealth().use_async(async_playwright()) as p:
        context = await p.chromium.launch_persistent_context(
            os.path.abspath("./user_data"),
            executable_path=BRAVE_PATH,
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )
        page = await context.new_page()

        try:
            if progress_cb:
                await progress_cb("🌐 Connecting to Gemini...")

            await page.goto("https://gemini.google.com/app", timeout=90000)
            try:
                await page.wait_for_selector('div[role="textbox"]', timeout=20000)
            except:
                result["error"] = "session_expired"
                return result

            print("[Gemini] Logged in ✓")
            box = 'div[role="textbox"]'

            # ── Step 1: Caption ───────────────────────────────────────────
            if progress_cb:
                await progress_cb("📝 Generating caption...")

            prev = await page.locator(RESPONSE_SEL).count()
            await page.fill(box, caption_prompt(topic))
            await page.keyboard.press("Enter")
            await _wait_stable(page, prev, timeout=90)

            raw = await page.locator(RESPONSE_SEL).last.inner_text()
            lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
            skip = ["here", "sure", "okay", "of course", "great", "gemini", "creating"]
            seen, deduped = set(), []
            for l in lines:
                if l not in seen and not any(l.lower().startswith(s) for s in skip):
                    seen.add(l)
                    deduped.append(l)
            caption = "\n".join(deduped) or "Living in the moment. ✨\n#PixarVibes"
            result["caption"] = caption
            print("[Caption] Done ✓")

            # ── Step 2: Image ─────────────────────────────────────────────
            if progress_cb:
                await progress_cb("🎨 Starting fresh chat for image generation...")

            await page.goto("https://gemini.google.com/app", timeout=60000)
            await page.wait_for_selector(box, timeout=20000)
            await asyncio.sleep(2)

            if progress_cb:
                await progress_cb("📎 Uploading character reference image...")

            uploaded = await _upload_file(page)

            if progress_cb:
                ref_status = "✓ Character uploaded!" if uploaded else "⚠️ Upload failed, using text description"
                await progress_cb(f"{ref_status}\n🖌️ Sending image prompt to Gemini...")

            prev = await page.locator(RESPONSE_SEL).count()
            await page.fill(box, image_prompt(topic))
            await page.keyboard.press("Enter")
            await _wait_stable(page, prev, timeout=30)

            # Wait for image with progress updates
            img_src = await _wait_for_image(page, timeout=300, progress_cb=progress_cb)

            if not img_src:
                debug = os.path.join(OUTPUT_DIR, "debug_timeout.png")
                await page.screenshot(path=debug)
                result["error"] = f"timeout — debug saved to {debug}"
                return result

            if progress_cb:
                await progress_cb("⬇️ Downloading image...")

            save_path = os.path.join(OUTPUT_DIR, f"aura_{int(time.time())}.png")
            ok = await _download_image(page, context, img_src, save_path)

            if not ok:
                result["error"] = "download_failed"
                return result

            result["image_path"] = save_path
            print(f"[Image] Saved: {save_path}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            result["error"] = str(e)
        finally:
            await context.close()

    return result
