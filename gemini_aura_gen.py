"""
gemini_gen.py — AURA v6 FINAL (WITH DEBUG)
"""
import os
import asyncio
import time
import base64
import shutil
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

BRAVE_PATH = (
    shutil.which("brave-browser") or
    shutil.which("chromium-browser") or
    shutil.which("chromium") or
    "/usr/bin/brave-browser"
)

RESPONSE_SEL = "model-response"
OUTPUT_DIR   = os.path.expanduser("~/AURA-Automation/outputs")

CHAR_REF = None
for _p in [
    os.path.expanduser("~/AURA-Automation/aura_new.jpeg"),
    os.path.expanduser("~/Downloads/aura_new.jpeg"),
    os.path.expanduser("~/AURA-Automation/character_ref.png"),
]:
    if os.path.exists(_p):
        CHAR_REF = _p
        break
if not CHAR_REF:
    CHAR_REF = os.path.expanduser("~/AURA-Automation/aura_new.jpeg")


ATTACHMENT_SELECTORS = [
    'div[data-test-id="upload-thumbnail"]',
    'div[aria-label*="uploaded"]',
    'img[alt*="uploaded"]',
    '.upload-image-chip',
    'div[class*="attachment"]',
    'div[class*="chip"] img',
    'div[class*="upload"] img',
]


def caption_prompt(topic):
    return (
        "Write a short punchy Instagram caption. "
        "Output ONLY the caption text and hashtags — no title, no intro, "
        "no 'here is', no 'sure', just 3-4 lines then hashtags. "
        "Scene: Pixar animated girl in this situation: " + topic
    )


def image_prompt(topic):
    return (
        "Look at the character image I just uploaded — she is the main character. "
        "Recreate HER exactly in a SINGLE cohesive Pixar/Disney 3D animated film still. "
        "The character AND the entire background must share the EXACT same "
        "3D rendered art style, like a frame from a Pixar movie. "
        "NO photorealistic backgrounds. "
        "CRITICAL — match this FEMALE character exactly: "
        "young GIRL with dark brown skin, shoulder-length wavy BLUE hair, "
        "orange hoodie with white drawstrings, purple/magenta shorts, "
        "blue sneakers, round expressive eyes, same cute face as the reference. "
        "She must look like a GIRL, not a boy. Do NOT change her gender. "
        "Scene: " + topic + ". "
        "Full body visible, warm cinematic Pixar lighting, "
        "9:16 vertical format, no text, no watermarks."
    )


async def _debug_upload_ui(page, debug_dir):
    """
    Comprehensive UI inspection to find the upload mechanism.
    Saves findings to debug_dir for analysis.
    """
    print("\n" + "="*80)
    print("[DEBUG] GEMINI UPLOAD UI INSPECTION")
    print("="*80)
    
    debug_file = os.path.join(debug_dir, "debug_upload_inspection.txt")
    with open(debug_file, "w") as f:
        f.write("GEMINI UPLOAD UI DEBUG INSPECTION\n")
        f.write("="*80 + "\n\n")
        
        # ────────────────────────────────────────────────────────────────
        # 1. Find all buttons with attributes
        # ────────────────────────────────────────────────────────────────
        f.write("SECTION 1: ALL VISIBLE BUTTONS\n")
        f.write("-"*80 + "\n")
        
        try:
            buttons = await page.locator('button').all()
            print(f"[DEBUG] Total buttons found: {len(buttons)}")
            f.write(f"Total buttons found: {len(buttons)}\n\n")
            
            for i, btn in enumerate(buttons):
                try:
                    aria_label = await btn.get_attribute('aria-label')
                    title = await btn.get_attribute('title')
                    cls = await btn.get_attribute('class')
                    visible = await btn.is_visible(timeout=500)
                    text = await btn.inner_text(timeout=500)
                    
                    if visible:
                        entry = f"Button {i}: [VISIBLE]\n"
                        entry += f"  aria-label: {aria_label}\n"
                        entry += f"  title: {title}\n"
                        entry += f"  text: {text[:100]}\n"
                        entry += f"  class: {cls[:150]}\n\n"
                        
                        print(f"[DEBUG] {entry}")
                        f.write(entry)
                except Exception as e:
                    pass
        except Exception as e:
            err = f"Error scanning buttons: {e}\n"
            print(f"[DEBUG] {err}")
            f.write(err)
        
        # ────────────────────────────────────────────────────────────────
        # 2. Search for upload-related keywords
        # ────────────────────────────────────────────────────────────────
        f.write("\nSECTION 2: UPLOAD-RELATED ELEMENTS\n")
        f.write("-"*80 + "\n")
        
        keywords = ["upload", "attach", "file", "image", "photo", "add"]
        for kw in keywords:
            try:
                # Buttons with keyword
                btns = await page.locator(f'button:has-text("{kw}")').all()
                if btns:
                    entry = f"\nButtons with text '{kw}': {len(btns)}\n"
                    print(f"[DEBUG] {entry.strip()}")
                    f.write(entry)
                    for btn in btns:
                        try:
                            txt = await btn.inner_text(timeout=500)
                            aria = await btn.get_attribute('aria-label')
                            f.write(f"  - text: {txt}, aria-label: {aria}\n")
                        except:
                            pass
                
                # Elements with keyword in aria-label
                elems = await page.locator(f'[aria-label*="{kw}"]').all()
                if elems:
                    entry = f"Elements with aria-label containing '{kw}': {len(elems)}\n"
                    print(f"[DEBUG] {entry.strip()}")
                    f.write(entry)
                    for elem in elems[:5]:  # Show first 5
                        try:
                            tag = await elem.evaluate("el => el.tagName")
                            aria = await elem.get_attribute('aria-label')
                            visible = await elem.is_visible(timeout=500)
                            f.write(f"  - {tag}: aria-label='{aria}' visible={visible}\n")
                        except:
                            pass
            except:
                pass
        
        # ────────────────────────────────────────────────────────────────
        # 3. Hidden file inputs
        # ────────────────────────────────────────────────────────────────
        f.write("\n\nSECTION 3: FILE INPUT ELEMENTS\n")
        f.write("-"*80 + "\n")
        
        try:
            file_inputs = await page.locator('input[type="file"]').all()
            print(f"[DEBUG] Hidden file inputs found: {len(file_inputs)}")
            f.write(f"Hidden file inputs found: {len(file_inputs)}\n\n")
            
            for i, inp in enumerate(file_inputs):
                try:
                    accept = await inp.get_attribute('accept')
                    id_attr = await inp.get_attribute('id')
                    name = await inp.get_attribute('name')
                    visible = await inp.is_visible(timeout=500)
                    
                    parent_html = await inp.evaluate(
                        "el => el.parentElement?.outerHTML?.slice(0, 300)"
                    )
                    
                    entry = f"File Input {i}:\n"
                    entry += f"  accept: {accept}\n"
                    entry += f"  id: {id_attr}\n"
                    entry += f"  name: {name}\n"
                    entry += f"  visible: {visible}\n"
                    entry += f"  parent html: {parent_html}\n\n"
                    
                    print(f"[DEBUG] {entry}")
                    f.write(entry)
                except Exception as e:
                    f.write(f"  Error: {e}\n")
        except Exception as e:
            err = f"Error scanning file inputs: {e}\n"
            print(f"[DEBUG] {err}")
            f.write(err)
        
        # ────────────────────────────────────────────────────────────────
        # 4. Menu items (for menu-based upload)
        # ────────────────────────────────────────────────────────────────
        f.write("\n\nSECTION 4: MENU ITEMS\n")
        f.write("-"*80 + "\n")
        
        try:
            menuitems = await page.locator('[role="menuitem"]').all()
            print(f"[DEBUG] Menu items found: {len(menuitems)}")
            f.write(f"Menu items found: {len(menuitems)}\n\n")
            
            for i, item in enumerate(menuitems[:10]):  # Show first 10
                try:
                    text = await item.inner_text(timeout=500)
                    aria = await item.get_attribute('aria-label')
                    f.write(f"MenuItem {i}: text='{text}' aria-label='{aria}'\n")
                except:
                    pass
        except Exception as e:
            err = f"Error scanning menu items: {e}\n"
            print(f"[DEBUG] {err}")
            f.write(err)
        
        # ────────────────────────────────────────────────────────────────
        # 5. Textbox and surrounding elements
        # ────────────────────────────────────────────────────────────────
        f.write("\n\nSECTION 5: TEXTBOX AREA\n")
        f.write("-"*80 + "\n")
        
        try:
            textbox = page.locator('div[role="textbox"]').first
            visible = await textbox.is_visible(timeout=500)
            f.write(f"Textbox visible: {visible}\n\n")
            
            # Find siblings/parent buttons
            parent_html = await textbox.evaluate(
                "el => el.parentElement?.outerHTML?.slice(0, 500)"
            )
            f.write(f"Parent container HTML:\n{parent_html}\n")
        except Exception as e:
            err = f"Error checking textbox: {e}\n"
            print(f"[DEBUG] {err}")
            f.write(err)
    
    print(f"[DEBUG] Inspection complete. Results saved to: {debug_file}")
    print("="*80 + "\n")
    
    # ────────────────────────────────────────────────────────────────
    # Screenshot
    # ────────────────────────────────────────────────────────────────
    screenshot_path = os.path.join(debug_dir, "gemini_upload_ui.png")
    await page.screenshot(path=screenshot_path, full_page=True)
    print(f"[DEBUG] Screenshot saved: {screenshot_path}")


async def _verify_upload(page, blobs_before: set, timeout=8) -> bool:
    """
    Three-tier verification that Gemini actually received the file:
      1. Known attachment chip/thumbnail selectors
      2. New blob: img appeared that wasn't there before upload
      3. DOM text cue ("image attached", "1 file", etc.)
    Returns True if ANY tier passes.
    """
    deadline = time.time() + timeout

    # Tier 1 + 2 — poll until deadline
    while time.time() < deadline:
        # Tier 1: attachment chip selectors
        for sel in ATTACHMENT_SELECTORS:
            try:
                if await page.locator(sel).count() > 0:
                    el = page.locator(sel).first
                    box = await el.bounding_box()
                    if box and box["width"] > 0:
                        print(f"[Upload] ✓ Verified via selector '{sel}' "
                              f"({box['width']:.0f}×{box['height']:.0f})")
                        return True
            except Exception:
                continue

        # Tier 2: new blob img that wasn't there before
        try:
            blobs_now: set = set(await page.evaluate(
                "() => [...document.querySelectorAll('img[src^=\"blob:\"]')].map(i=>i.src)"
            ))
            new_blobs = blobs_now - blobs_before
            if new_blobs:
                print(f"[Upload] ✓ Verified via {len(new_blobs)} new blob img(s)")
                return True
        except Exception:
            pass

        await asyncio.sleep(0.5)

    # Tier 3: text cue (last resort, outside poll loop)
    try:
        page_text = (await page.evaluate("() => document.body.innerText")).lower()
        for cue in ["image attached", "file attached", "1 file", "attachment"]:
            if cue in page_text:
                print(f"[Upload] ✓ Verified via text cue: '{cue}'")
                return True
    except Exception:
        pass

    print("[Upload] ✗ Verification failed — Gemini UI shows no attachment")
    return False


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


async def _upload_file(page, debug_dir=None) -> bool:
    """
    Upload character reference with multiple fallback approaches.
    NEW: Tries direct hidden input approach first, then menu, then drag-drop.
    """
    print(f"[Upload] Using: {CHAR_REF} (exists={os.path.exists(CHAR_REF)})")
    if not os.path.exists(CHAR_REF):
        print("[Upload] ✗ File not found")
        return False

    # Snapshot blob imgs BEFORE upload
    try:
        blobs_before: set = set(await page.evaluate(
            "() => [...document.querySelectorAll('img[src^=\"blob:\"]')].map(i=>i.src)"
        ))
    except Exception:
        blobs_before = set()
    print(f"[Upload] Blob imgs before upload: {len(blobs_before)}")

    # ── Approach 1: Direct hidden file input ──────────────────────────────
    try:
        print("[Upload] Approach 1: Hidden file input...")
        await page.evaluate("""() => {
            if (!document.getElementById('aura-upload-hidden')) {
                const input = document.createElement('input');
                input.type = 'file';
                input.id = 'aura-upload-hidden';
                input.accept = 'image/*';
                input.style.display = 'none';
                document.body.appendChild(input);
            }
        }""")
        
        file_input = page.locator('#aura-upload-hidden')
        await file_input.set_input_files(CHAR_REF)
        print("[Upload] File set via hidden input, waiting for Gemini to process...")
        await asyncio.sleep(3)
        
        if await _verify_upload(page, blobs_before, timeout=12):
            print("[Upload] ✓ Hidden input approach verified")
            return True
        print("[Upload] Hidden input approach: unverified, trying next...")
    except Exception as e:
        print(f"[Upload] Approach 1 failed: {e}")

    # ── Approach 2: Menu flow ─────────────────────────────────────────────
    try:
        print("[Upload] Approach 2: Menu flow...")
        btn = page.locator('button[aria-label="Open upload file menu"]')
        await btn.wait_for(state="visible", timeout=4000)
        await btn.click()
        await asyncio.sleep(1.0)

        for text in ["Add image", "Upload image", "Image", "Photo", "Add photo"]:
            try:
                item = page.locator(f'[role="menuitem"]:has-text("{text}")').first
                if await item.is_visible(timeout=500):
                    print(f"[Upload] Clicking menu item '{text}'")
                    async with page.expect_file_chooser(timeout=5000) as fc_info:
                        await item.click()
                    fc = await fc_info.value
                    await fc.set_files(CHAR_REF)
                    print("[Upload] File set via menu, waiting...")
                    await asyncio.sleep(3)
                    
                    if await _verify_upload(page, blobs_before, timeout=12):
                        print("[Upload] ✓ Menu approach verified")
                        return True
                    print("[Upload] Menu item unverified, trying next...")
                    break
            except Exception as e:
                print(f"[Upload] Menu item '{text}' failed: {e}")
                continue

    except Exception as e:
        print(f"[Upload] Approach 2 failed: {e}")
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await asyncio.sleep(0.5)

    # ── Approach 3: Drag and drop ─────────────────────────────────────────
    try:
        print("[Upload] Approach 3: Drag-and-drop...")
        with open(CHAR_REF, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = "jpeg" if CHAR_REF.lower().endswith((".jpg", ".jpeg")) else "png"
        mime = f"image/{ext}"
        
        result = await page.evaluate(f"""async () => {{
            try {{
                const bytes = Uint8Array.from(atob(`{b64}`), c => c.charCodeAt(0));
                const file = new File([bytes], 'ref.{ext}', {{type:'{mime}'}});
                const dt = new DataTransfer();
                dt.items.add(file);
                const box = document.querySelector('div[role="textbox"]') || 
                            document.querySelector('[contenteditable="true"]');
                if (!box) return 'no-box';
                const rect = box.getBoundingClientRect();
                ['dragenter','dragover','drop'].forEach(t =>
                    box.dispatchEvent(new DragEvent(t, {{
                        bubbles:true, 
                        cancelable: true,
                        clientX: rect.x + 50,
                        clientY: rect.y + 50,
                        dataTransfer:dt
                    }})));
                return 'ok';
            }} catch(e) {{ return 'error:' + e.message; }}
        }}""")
        
        print(f"[Upload] Drag-drop result: {result}")
        if result == 'ok':
            await asyncio.sleep(3)
            if await _verify_upload(page, blobs_before, timeout=12):
                print("[Upload] ✓ Drag-drop approach verified")
                return True
            print("[Upload] Drag-drop unverified")
    except Exception as e:
        print(f"[Upload] Approach 3 failed: {e}")

    print("[Upload] ✗ ALL APPROACHES FAILED")
    return False


async def _wait_for_image(page, timeout=300, progress_cb=None):
    deadline    = time.time() + timeout
    start       = time.time()
    last_update = time.time()

    ref_blob = await page.evaluate("""() => {
        const r = [...document.querySelectorAll('img')]
            .find(i => i.src.startsWith('blob:') && i.naturalWidth > 30);
        return r ? r.src : null;
    }""")
    print(f"[Image] Ref blob excluded: {ref_blob}")
    print(f"[Image] Waiting up to {timeout}s...")

    while time.time() < deadline:
        try:
            await page.locator(RESPONSE_SEL).last.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        src = await page.evaluate(f"""() => {{
            const refused = ["can't generate","cannot create","unable to generate",
                             "i'm not able","i can't help","i'm unable","i apologize"];
            const REF = {f'"{ref_blob}"' if ref_blob else 'null'};
            const rs = document.querySelectorAll('{RESPONSE_SEL}');
            if (!rs.length) return null;
            const last = rs[rs.length - 1];
            const txt = (last.innerText || '').toLowerCase();
            if (refused.some(r => txt.includes(r))) return 'REFUSED';
            if (txt.includes('creating your image')) return 'GENERATING';

            function good(img) {{
                const s = img.src || '';
                if (!s || s === REF) return false;
                if (s.includes('avatar')||s.includes('icon')||
                    s.includes('logo')||s.includes('favicon')) return false;
                if (img.naturalWidth>0&&img.naturalWidth<100&&
                    img.naturalHeight>0&&img.naturalHeight<100) return false;
                return img.naturalWidth>=200||img.naturalHeight>=200||
                       img.width>=200||img.height>=200||s.startsWith('blob:');
            }}
            function biggest(arr) {{
                arr.sort((a,b)=>
                    (b.naturalWidth||b.width||0)*(b.naturalHeight||b.height||0)-
                    (a.naturalWidth||a.width||0)*(a.naturalHeight||a.height||0));
                return arr[0].src;
            }}
            const d=[...last.querySelectorAll('img')].filter(good);
            if(d.length) return biggest(d);
            function di(root){{
                const o=[];
                const w=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT);
                let n; while(n=w.nextNode()){{
                    if(n.shadowRoot) o.push(...di(n.shadowRoot));
                    if(n.tagName==='IMG') o.push(n);
                }}
                return o;
            }}
            const dp=di(last).filter(good);
            if(dp.length) return biggest(dp);
            const bl=[...document.querySelectorAll('img')].filter(i=>{{
                const s=i.src||'';
                return s.startsWith('blob:')&&s!==REF&&
                       (i.naturalWidth>=300||i.width>=300);
            }});
            if(bl.length) return biggest(bl);
            return null;
        }}""")

        if src == 'REFUSED':
            return None
        if src and src != 'GENERATING' and src != 'null':
            print(f"[Image] Found ✓ in {int(time.time()-start)}s")
            return src

        now = time.time()
        if progress_cb and (now - last_update) >= 30:
            elapsed = int(now - start)
            remaining = int(deadline - now)
            s = "🖌️ Gemini is painting..." if src=='GENERATING' else "⏳ Starting..."
            await progress_cb(f"{s}\n_{elapsed}s elapsed, {remaining}s left_")
            last_update = now

        print(f"[Image] {'Generating' if src=='GENERATING' else 'Waiting'}... {int(deadline-time.time())}s left")
        await asyncio.sleep(3)

    print("[Image] TIMEOUT")
    imgs = await page.evaluate("""() =>
        [...document.querySelectorAll('img')].map(i=>({
            src:i.src?.slice(0,80),w:i.naturalWidth||i.width,h:i.naturalHeight||i.height
        }))""")
    for i in imgs:
        print(f"  {i}")
    return None


async def _download_image(page, context, img_src, save_path):
    if img_src.startswith('blob:'):
        try:
            safe = img_src.replace('`','\\`')
            b64 = await page.evaluate(f"""async()=>{{
                const src=`{safe}`;
                try{{
                    const r=await fetch(src);
                    const buf=await r.arrayBuffer();
                    const b=new Uint8Array(buf);
                    let s='';for(let i=0;i<b.length;i++)s+=String.fromCharCode(b[i]);
                    return btoa(s);
                }}catch(e){{
                    const img=[...document.querySelectorAll('img')].find(i=>i.src===src);
                    if(!img) return null;
                    await new Promise(r=>{{if(img.complete)r();else{{img.onload=r;img.onerror=r;}}}});
                    const c=document.createElement('canvas');
                    c.width=img.naturalWidth||img.width||512;
                    c.height=img.naturalHeight||img.height||512;
                    c.getContext('2d').drawImage(img,0,0);
                    return c.toDataURL('image/png').split(',')[1];
                }}
            }}""")
            if b64:
                raw = base64.b64decode(b64)
                if len(raw) > 10000:
                    with open(save_path,"wb") as f: f.write(raw)
                    print(f"[Download] Blob ✓ {len(raw):,}b")
                    return True
        except Exception as e:
            print(f"[Download] Blob: {e}")
        return False

    try:
        r = await context.request.get(img_src, timeout=30000)
        if r.ok:
            d = await r.body()
            if len(d) > 10000:
                with open(save_path,"wb") as f: f.write(d)
                print(f"[Download] Fetch ✓ {len(d):,}b")
                return True
    except Exception as e:
        print(f"[Download] Fetch: {e}")

    try:
        safe = img_src.replace('`','\\`')
        b64 = await page.evaluate(f"""async()=>{{
            const img=[...document.querySelectorAll('img')].find(i=>i.src===`{safe}`);
            if(!img) return null;
            await new Promise(r=>{{if(img.complete)r();else{{img.onload=r;img.onerror=r;}}}});
            const c=document.createElement('canvas');
            c.width=img.naturalWidth||img.width||512;
            c.height=img.naturalHeight||img.height||512;
            c.getContext('2d').drawImage(img,0,0);
            return c.toDataURL('image/png').split(',')[1];
        }}""")
        if b64:
            raw = base64.b64decode(b64)
            if len(raw) > 10000:
                with open(save_path,"wb") as f: f.write(raw)
                print(f"[Download] Canvas ✓ {len(raw):,}b")
                return True
    except Exception as e:
        print(f"[Download] Canvas: {e}")

    try:
        el = page.locator(f'img[src="{img_src}"]').first
        await el.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await el.screenshot(path=save_path, type="png")
        if os.path.getsize(save_path) > 10000:
            print("[Download] Screenshot ✓")
            return True
    except Exception as e:
        print(f"[Download] Screenshot: {e}")

    return False


async def generate(topic: str, progress_cb=None, debug_mode=False) -> dict:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    debug_dir = os.path.join(OUTPUT_DIR, "debug")
    os.makedirs(debug_dir, exist_ok=True)
    
    result = {"caption": None, "image_path": None, "error": None}
    print(f"[Config] Browser: {BRAVE_PATH}")
    print(f"[Config] Ref: {CHAR_REF} (exists={os.path.exists(CHAR_REF)})")
    print(f"[Config] Debug mode: {debug_mode}")

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
        await page.set_viewport_size({"width": 1280, "height": 900})

        try:
            if progress_cb:
                await progress_cb("🌐 Connecting to Gemini...")

            await page.goto("https://gemini.google.com/app", timeout=90000)
            try:
                await page.wait_for_selector('div[role="textbox"]', timeout=20000)
            except Exception:
                result["error"] = "session_expired"
                return result

            print("[Gemini] Logged in ✓")
            box = 'div[role="textbox"]'

            # Step 1: Caption
            if progress_cb:
                await progress_cb("📝 Generating caption...")

            prev = await page.locator(RESPONSE_SEL).count()
            await page.fill(box, caption_prompt(topic))
            await page.keyboard.press("Enter")
            await _wait_stable(page, prev, timeout=90)

            raw = await page.locator(RESPONSE_SEL).last.inner_text()
            lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
            ui_noise = {"answer now","show drafts","copy","report","good response",
                        "bad response","share","export","volume_up","thumb_up",
                        "thumb_down","more_vert"}
            skip_starts = ["here's your caption","here is","sure, here","of course!","gemini:"]
            seen, deduped = set(), []
            for l in lines:
                low = l.lower().strip()
                if l not in seen and low not in ui_noise and not any(low.startswith(s) for s in skip_starts):
                    seen.add(l)
                    deduped.append(l)
            caption = "\n".join(deduped) or "Living in the moment. ✨\n#PixarVibes"
            result["caption"] = caption
            print(f"[Caption] Done ✓ ({len(deduped)} lines)")

            # Step 2: Image
            if progress_cb:
                await progress_cb("🎨 Opening fresh chat...")

            await page.goto("https://gemini.google.com/app", timeout=60000)
            await page.wait_for_selector(box, timeout=20000)
            await asyncio.sleep(2)

            # ──────────────────────────────────────────────────────────
            # DEBUG: Inspect upload UI before attempting upload
            # ──────────────────────────────────────────────────────────
            if debug_mode:
                if progress_cb:
                    await progress_cb("🔍 Debugging upload UI (debug mode)...")
                await _debug_upload_ui(page, debug_dir)
                result["debug_dir"] = debug_dir
                print(f"[Debug] Results saved to: {debug_dir}")
                print("[Debug] Check the following files:")
                print(f"  - Text report: {os.path.join(debug_dir, 'debug_upload_inspection.txt')}")
                print(f"  - Screenshot: {os.path.join(debug_dir, 'gemini_upload_ui.png')}")
                return result  # Exit debug mode here

            if progress_cb:
                await progress_cb("📎 Uploading character reference...")

            uploaded = await _upload_file(page, debug_dir)

            if progress_cb:
                s = "✓ Ref uploaded & verified!" if uploaded else "⚠️ Upload FAILED — text-only generation"
                await progress_cb(f"{s}\n🖌️ Sending prompt...")

            prev = await page.locator(RESPONSE_SEL).count()
            await page.fill(box, image_prompt(topic))
            await page.keyboard.press("Enter")

            t0 = time.time()
            while time.time() - t0 < 15:
                if await page.locator(RESPONSE_SEL).count() > prev:
                    break
                await asyncio.sleep(0.5)

            img_src = await _wait_for_image(page, timeout=300, progress_cb=progress_cb)

            if not img_src:
                debug = os.path.join(debug_dir, "debug_timeout.png")
                await page.screenshot(path=debug, full_page=True)
                result["error"] = f"timeout — debug at {debug}"
                return result

            if progress_cb:
                await progress_cb("⬇️ Downloading image...")

            save_path = os.path.join(OUTPUT_DIR, f"aura_{int(time.time())}.png")
            if not await _download_image(page, context, img_src, save_path):
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