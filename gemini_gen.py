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
        "Look at the character image I just uploaded. "
        "Create a SINGLE cohesive Pixar/Disney 3D animated film still — "
        "the character AND the entire background environment must share "
        "the EXACT same 3D rendered art style, like a frame from a Pixar movie. "
        "NO photorealistic backgrounds. The whole image — sky, ground, objects, "
        "lighting, textures — must look like it was rendered in the same 3D animation "
        "software as the character. "
        "Character details to match exactly: dark brown skin, blue hair, "
        "orange hoodie, purple shorts, blue sneakers, same face. "
        "Scene: " + topic + ". "
        "Full body visible, warm cinematic Pixar lighting, "
        "9:16 vertical format, no text, no watermarks, no photorealism anywhere."
    )
async def _wait_stable(page, prev_count, timeout=90):
    """Wait for response to appear and stabilize."""
    deadline = time.time() + timeout
    
    # Phase 1: Wait for a NEW response to appear
    print(f"[Wait] Waiting for response (currently {prev_count} responses)...")
    while time.time() < deadline:
        current = await page.locator(RESPONSE_SEL).count()
        if current > prev_count:
            print(f"[Wait] Response appeared! Now {current} responses")
            break
        await asyncio.sleep(1)
    else:
        print("[Wait] ✗ No response appeared within timeout")
        return False
    
    # Phase 2: Wait for response text to stabilize
    await asyncio.sleep(2)  # Give Gemini time to start rendering
    
    last = page.locator(RESPONSE_SEL).last
    prev_text = ""
    ticks = 0
    deadline2 = time.time() + 60
    
    print("[Wait] Waiting for text to stabilize...")
    while time.time() < deadline2:
        try:
            cur = await last.inner_text(timeout=5000)  # Add timeout to inner_text
            if cur == prev_text and cur.strip():
                ticks += 1
                if ticks >= 3:
                    print(f"[Wait] ✓ Text stabilized ({len(cur)} chars)")
                    return True
            else:
                if cur.strip():
                    print(f"[Wait] Text changed... ({len(cur)} chars)")
                ticks = 0
            prev_text = cur
        except Exception as e:
            print(f"[Wait] inner_text error: {e}")
            await asyncio.sleep(1)
            continue
        
        await asyncio.sleep(1)
    
    print("[Wait] ✗ Text did not stabilize")
    return False


async def _upload_file(page):
    """
    Upload character reference.
    Confirmed aria-label: 'Open upload file menu'
    Clicks the menu, then intercepts the file chooser from the menu item.
    """
    print("[Upload] Starting upload flow...")

    # ── Step 1: Click the confirmed '+' button ────────────────────────────────
    upload_btn = page.locator('button[aria-label="Open upload file menu"]')
    try:
        await upload_btn.wait_for(state="visible", timeout=5000)
    except:
        print("[Upload] ✗ 'Open upload file menu' button not found")
        return False

    print("[Upload] Found 'Open upload file menu' ✓")

    # ── Step 2: Click and wait for menu to animate in ─────────────────────────
    await upload_btn.click()
    await asyncio.sleep(1.0)

    # Save menu screenshot for debugging
    try:
        await page.screenshot(path=os.path.join(OUTPUT_DIR, "upload_menu_debug.png"))
        print("[Upload] Menu screenshot saved")
    except:
        pass

    # ── Step 3: Click the image upload menu item → intercept file chooser ─────
    menu_item_texts = [
        "Add image",
        "Upload image",
        "Image",
        "Add file",
        "Upload file",
        "File",
        "Photo",
        "Add photo",
    ]

    clicked = False
    for text in menu_item_texts:
        try:
            item = page.locator(f'[role="menuitem"]:has-text("{text}")').first
            if await item.is_visible(timeout=800):
                print(f"[Upload] Clicking menu item: '{text}'")
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await item.click()
                fc = await fc_info.value
                await fc.set_files(CHAR_REF)
                await asyncio.sleep(4)
                print("[Upload] ✓ File staged via menu item")
                clicked = True
                break
        except:
            continue

    if not clicked:
        # Fallback: log all visible menuitems and click the first
        print("[Upload] Known menu texts not found — trying first visible menuitem")
        try:
            items = page.locator('[role="menuitem"]')
            count = await items.count()
            print(f"[Upload] Found {count} menuitem(s)")
            for i in range(count):
                item = items.nth(i)
                text = await item.inner_text()
                print(f"[Upload]   [{i}] '{text.strip()}'")
            if count > 0:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await items.first.click()
                fc = await fc_info.value
                await fc.set_files(CHAR_REF)
                await asyncio.sleep(4)
                print("[Upload] ✓ Fallback first menuitem")
                clicked = True
        except Exception as e:
            print(f"[Upload] Fallback failed: {e}")

    if not clicked:
        print("[Upload] ✗ All upload approaches failed")
        return False

    # ── Step 4: Verify thumbnail appeared in composer ─────────────────────────
    await asyncio.sleep(2)
    preview_found = await page.evaluate("""() => {
        const composer = document.querySelector('div[role="textbox"]')?.closest('form')
                      || document.querySelector('div[role="textbox"]')?.parentElement?.parentElement;
        if (!composer) return false;
        const imgs = [...composer.querySelectorAll('img')];
        return imgs.some(img =>
            img.naturalWidth > 30 ||
            img.src.startsWith('blob:') ||
            (img.getAttribute('alt') || '').toLowerCase().includes('upload')
        );
    }""")

    if preview_found:
        print("[Upload] ✓ Preview thumbnail confirmed in composer")
    else:
        print("[Upload] ⚠️  No thumbnail detected — file may not have attached")

    return True
async def _wait_for_image(page, timeout=300, progress_cb=None):
    """
    Wait for Gemini's generated image.
    Uses multiple detection strategies since Gemini's DOM structure varies.
    """
    deadline = time.time() + timeout
    start = time.time()
    last_update = time.time()
    update_interval = 30
    # Record the upload ref blob URL so we can exclude it
    ref_blob_url = await page.evaluate("""() => {
        const imgs = [...document.querySelectorAll('img')];
        const ref = imgs.find(img => img.src.startsWith('blob:') && img.naturalWidth > 30);
        return ref ? ref.src : null;
    }""")
    print(f"[Image] Ref blob to exclude: {ref_blob_url}")
    print(f"[Image] Waiting up to {timeout}s...")

    while time.time() < deadline:
        # Scroll last response into view
        try:
            await page.locator(RESPONSE_SEL).last.scroll_into_view_if_needed(timeout=2000)
        except:
            pass

        src = await page.evaluate(f"""() => {{
            const refused = ["can't generate", "cannot create", "unable to generate",
                             "i'm not able", "i can't help", "i'm unable",
                             "i apologize", "i'm sorry"];
            const REF_BLOB = {f'"{ref_blob_url}"' if ref_blob_url else 'null'};

            const rs = document.querySelectorAll('{RESPONSE_SEL}');
            if (!rs.length) return null;
            const last = rs[rs.length - 1];
            const txt = (last.innerText || '').toLowerCase();

            if (refused.some(r => txt.includes(r))) return 'REFUSED';
            if (txt.includes('creating your image')) return 'GENERATING';

            // Strategy 1: direct img inside model-response
            const direct = [...last.querySelectorAll('img')].filter(img => {{
                const s = img.src || '';
                if (!s || s === REF_BLOB) return false;
                if (s.includes('avatar') || s.includes('icon') ||
                    s.includes('logo') || s.includes('favicon')) return false;
                const tooSmall = img.naturalWidth > 0 && img.naturalWidth < 100
                              && img.naturalHeight > 0 && img.naturalHeight < 100;
                if (tooSmall) return false;
                return img.naturalWidth >= 200 || img.naturalHeight >= 200
                    || img.width >= 200 || img.height >= 200
                    || s.startsWith('blob:');
            }});
            if (direct.length) {{
                direct.sort((a,b) =>
                    (b.naturalWidth||b.width||0)*(b.naturalHeight||b.height||0) -
                    (a.naturalWidth||a.width||0)*(a.naturalHeight||a.height||0));
                return direct[0].src;
            }}

            // Strategy 2: walk shadow roots under model-response
            function findImgsDeep(root) {{
                const results = [];
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                let node;
                while (node = walker.nextNode()) {{
                    if (node.shadowRoot) {{
                        results.push(...findImgsDeep(node.shadowRoot));
                    }}
                    if (node.tagName === 'IMG') results.push(node);
                }}
                return results;
            }}
            const deep = findImgsDeep(last).filter(img => {{
                const s = img.src || '';
                if (!s || s === REF_BLOB) return false;
                if (s.includes('avatar') || s.includes('icon') || s.includes('logo')) return false;
                return img.naturalWidth >= 150 || img.width >= 150 || s.startsWith('blob:');
            }});
            if (deep.length) {{
                deep.sort((a,b) =>
                    (b.naturalWidth||b.width||0)*(b.naturalHeight||b.height||0) -
                    (a.naturalWidth||a.width||0)*(a.naturalHeight||a.height||0));
                return deep[0].src;
            }}

            // Strategy 3: all blobs on page EXCEPT the ref blob and tiny ones
            // (generated image sometimes renders outside model-response in a portal)
            const allBlobs = [...document.querySelectorAll('img')].filter(img => {{
                const s = img.src || '';
                if (!s.startsWith('blob:') || s === REF_BLOB) return false;
                // Must be bigger than the ref thumbnail
                return (img.naturalWidth >= 300 || img.width >= 300);
            }});
            if (allBlobs.length) {{
                allBlobs.sort((a,b) =>
                    (b.naturalWidth||b.width||0)*(b.naturalHeight||b.height||0) -
                    (a.naturalWidth||a.width||0)*(a.naturalHeight||a.height||0));
                return allBlobs[0].src;
            }}

            return null;
        }}""")

        if src == 'REFUSED':
            print("[Image] Gemini refused")
            return None
        if src and src != 'GENERATING' and src != 'null':
            elapsed = int(time.time() - start)
            print(f"[Image] Done in {elapsed}s ✓  src={src[:80]}")
            return src

        now = time.time()
        if progress_cb and (now - last_update) >= update_interval:
            elapsed = int(now - start)
            remaining = int(deadline - now)
            status = "🖌️ Gemini is painting..." if src == 'GENERATING' else "⏳ Starting generation..."
            await progress_cb(f"{status}\n_{elapsed}s elapsed, up to {remaining}s remaining_")
            last_update = now

        remaining = int(deadline - time.time())
        print(f"[Image] {'Generating' if src == 'GENERATING' else 'Waiting'}... {remaining}s left")
        await asyncio.sleep(3)

    # Timeout — dump all img srcs to terminal for diagnosis
    print("[Image] TIMEOUT — dumping all imgs on page:")
    all_imgs = await page.evaluate("""() =>
        [...document.querySelectorAll('img')].map(img => ({
            src: img.src?.slice(0,80),
            w: img.naturalWidth || img.width,
            h: img.naturalHeight || img.height
        }))
    """)
    for img in all_imgs:
        print(f"  {img}")

    return None

async def _download_image(page, context, img_src, save_path):
    """Download just the image pixels — no UI chrome."""

    # Blob URLs: must use in-page fetch or canvas (not context.request.get)
    if img_src.startswith('blob:'):
        print("[Download] Blob URL — using in-page fetch")
        try:
            safe = img_src.replace('`', '\\`')
            b64 = await page.evaluate(f"""async () => {{
                const src = `{safe}`;
                try {{
                    const resp = await fetch(src);
                    const buf = await resp.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let bin = '';
                    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
                    return btoa(bin);
                }} catch(e) {{
                    const img = [...document.querySelectorAll('img')].find(i => i.src === src);
                    if (!img) return null;
                    await new Promise(r => {{ if(img.complete) r(); else {{img.onload=r;img.onerror=r;}} }});
                    const c = document.createElement('canvas');
                    c.width = img.naturalWidth || img.width || 512;
                    c.height = img.naturalHeight || img.height || 512;
                    c.getContext('2d').drawImage(img, 0, 0);
                    return c.toDataURL('image/png').split(',')[1];
                }}
            }}""")
            if b64:
                raw = base64.b64decode(b64)
                if len(raw) > 10000:
                    with open(save_path, "wb") as f:
                        f.write(raw)
                    print(f"[Download] Blob ✓ — {len(raw):,}b")
                    return True
        except Exception as e:
            print(f"[Download] Blob failed: {e}")
        return False

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

    # Method 2: Navigate to URL in new page
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

    # Method 3: Canvas export
    try:
        safe = img_src.replace('`', '\\`')
        b64 = await page.evaluate(f"""async () => {{
            const img = [...document.querySelectorAll('img')].find(i => i.src===`{safe}`);
            if (!img) return null;
            await new Promise(r => {{ if(img.complete) r(); else {{img.onload=r;img.onerror=r;}} }});
            const c = document.createElement('canvas');
            c.width = img.naturalWidth || img.width || 512;
            c.height = img.naturalHeight || img.height || 512;
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

    # Method 4: Element screenshot
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

        # Large viewport so images load eagerly (not lazy off-screen)
        await page.set_viewport_size({"width": 1280, "height": 900})

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

            # ── Step 2: Fresh chat for image ──────────────────────────────
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

            # Wait for Gemini to register the upload before sending prompt
            if uploaded:
                print("[Upload] Waiting for thumbnail to appear in DOM...")
                try:
                    await page.wait_for_function("""() => {
                        const imgs = [...document.querySelectorAll('img')];
                        return imgs.some(img =>
                            img.src.startsWith('blob:') && img.naturalWidth > 30
                        );
                    }""", timeout=10000)
                    print("[Upload] Thumbnail confirmed ✓")
                except:
                    print("[Upload] Thumbnail wait timed out — sending anyway")
                    await asyncio.sleep(2)

            # Send the image prompt
            prev = await page.locator(RESPONSE_SEL).count()
            await page.fill(box, image_prompt(topic))
            await page.keyboard.press("Enter")

            # Wait for response element to appear (don't use _wait_stable here —
            # Gemini goes straight to image gen with no stable text phase)
            deadline_appear = time.time() + 15
            while time.time() < deadline_appear:
                if await page.locator(RESPONSE_SEL).count() > prev:
                    break
                await asyncio.sleep(0.5)

            # Wait for the generated image
            img_src = await _wait_for_image(page, timeout=300, progress_cb=progress_cb)

            if not img_src:
                debug = os.path.join(OUTPUT_DIR, "debug_timeout.png")
                await page.screenshot(path=debug, full_page=True)
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