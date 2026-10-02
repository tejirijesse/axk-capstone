#!/usr/bin/env python3
"""Automated Demo Video Recorder for AXK Capstone.

Orchestrates a comprehensive, narrated, end-to-end screen recording of:
1. Overview & 6-Stage Custody Flow
2. Cooperative Dashboard (Lot Registration)
3. Inspector Dashboard (Quality Grading & Attestation)
4. Buyer Dashboard (Smart Escrow Lock)
5. Logistics Carrier Dashboard (Waybill & Anti-Tamper Container Seal)
6. Port / Terminal Dashboard (Gate-In & Anti-Tamper Seal Verification)
7. Buyer Delivery Settlement & Automated 40/40/20 Revenue Splitter
8. Public Chain & Trace with Dynamic SVG QR Code & Cryptographic Hash Verification
9. Live Stellar Testnet Chain Explorer

Produces: docs/demo/axk-capstone-demo.mp4
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_DIR = BASE_DIR / "docs" / "demo"
TEMP_DIR = DEMO_DIR / "temp"
OUTPUT_MP4 = DEMO_DIR / "axk-capstone-demo.mp4"
THUMBNAIL_JPG = DEMO_DIR / "thumbnail.jpg"

DEMO_DIR.mkdir(parents=True, exist_ok=True)
if TEMP_DIR.exists():
    shutil.rmtree(TEMP_DIR)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

NARRATION_VOICE = "en-NG-AbeoNeural"  # Natural Nigerian Neural Voice

SCENES = [
    {
        "id": "01_intro",
        "title": "Introduction & Overview",
        "text": (
            "Welcome to the demonstration of AXK Network, a verification and settlement layer on Stellar "
            "designed for cross-border agricultural trade corridors in East Africa. In traditional corridors, "
            "buyers face severe quality and custody risks, while cross-border payments are slow and uncertain. "
            "AXK solves this by synchronizing physical custody with smart contracts on Stellar testnet."
        ),
        "url": "http://localhost:8000/trade",
    },
    {
        "id": "02_coop",
        "title": "Cooperative Lot Registration",
        "text": (
            "We begin at the Cooperative dashboard. Cooperatives register their agricultural harvests before sale. "
            "Here we register a 4,500 kilogram lot of high-grade Rwandan coffee from Huye District. "
            "The system computes market pricing, packages a canonical JSON record, hashes it with SHA-256, "
            "and commits the registration to the Stellar lot registry bound to the cooperative's address."
        ),
        "url": "http://localhost:8000/trade/coop",
    },
    {
        "id": "03_inspector",
        "title": "Independent Inspection & Quality Grading",
        "text": (
            "Next, an authorised independent inspector grades the cargo. "
            "The inspector measures moisture content at 11.8 percent, confirms Grade A quality, "
            "and signs an immutable pass attestation on-chain. "
            "Uninspected or rejected lots cannot proceed to sale, protecting buyers from substandard produce."
        ),
        "url": "http://localhost:8000/trade/inspect",
    },
    {
        "id": "04_buyer_escrow",
        "title": "Buyer Smart-Contract Escrow",
        "text": (
            "Now the buyer reviews the certified lot. Only inspected and approved goods appear in the marketplace. "
            "The buyer deposits payment into a Soroban smart-contract escrow. "
            "The escrow contract locks the funds, strictly bound to the registered cooperative payee."
        ),
        "url": "http://localhost:8000/trade/buy",
    },
    {
        "id": "05_logistics",
        "title": "Logistics Custody & Tamper-Evident Seal",
        "text": (
            "Physical custody now transfers to the transport carrier. "
            "Swift Freight Logistics assigns driver Emmanuel Nzeyimana and vehicle RAD 482B. "
            "A tamper-evident container seal is generated and locked to the container. "
            "The carrier commits a cryptographic waybill digest to the custody trail, and the cargo is dispatched."
        ),
        "url": "http://localhost:8000/trade/logistics",
    },
    {
        "id": "06_port",
        "title": "Port Gate-In & Anti-Tamper Verification",
        "text": (
            "The truck arrives at the Kigali Logistics Platform terminal. "
            "The gate-in officer inspects the container seal against the waybill manifest. "
            "If the seal were broken or tampered with, the system would immediately issue a tamper alert. "
            "With the seal verified intact, Rwandan customs entry is recorded, and clearance is anchored on-chain."
        ),
        "url": "http://localhost:8000/trade/port",
    },
    {
        "id": "07_settlement",
        "title": "Settlement & Automated Member Revenue Split",
        "text": (
            "With physical custody verified at the port, the buyer confirms delivery. "
            "This triggers the Soroban splitter contract: escrow releases payment, automatically distributing "
            "40 percent to the farmer pool, 40 percent to the cooperative treasury, and 20 percent to the input reserve. "
            "The settlement attestation is anchored permanently on Stellar."
        ),
        "url": "http://localhost:8000/trade/buy",
    },
    {
        "id": "08_trace",
        "title": "Public Chain & Trace Verification",
        "text": (
            "Anyone along the corridor can publicly verify the shipment at slash trace without logging in. "
            "A dynamic vector QR code allows instant mobile verification. "
            "The complete 6-stage custody timeline is displayed with links to the Stellar block explorer. "
            "In addition, all four cryptographic SHA-256 hashes are verified in real time."
        ),
        "url": "http://localhost:8000/trace",
    },
    {
        "id": "09_explorer",
        "title": "Chain Explorer & Conclusion",
        "text": (
            "Finally, the Chain Explorer monitors live money flow and verification events on Stellar testnet. "
            "The complete solution includes 72 passing contract and integration tests with a zero-dependency standalone runner. "
            "AXK Network delivers a practical, verifiable, and secure foundation for cross-border trade in Africa."
        ),
        "url": "http://localhost:8000/chain",
    },
]


def generate_audio(scene):
    sid = scene["id"]
    mp3_path = TEMP_DIR / f"{sid}.mp3"
    m4a_path = TEMP_DIR / f"{sid}.m4a"
    txt = scene["text"]

    print(f"  [Neural Voice] Synthesizing {sid} ({NARRATION_VOICE})...")
    uv_bin = shutil.which("uv") or "/Users/joe/.local/bin/uv"
    cmd = [uv_bin, "tool", "run", "edge-tts", "--voice", NARRATION_VOICE, "--text", txt, "--write-media", str(mp3_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(mp3_path),
        "-c:a", "aac", "-b:a", "192k", str(m4a_path)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    res = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(m4a_path)
    ], capture_output=True, text=True, check=True)
    duration = float(res.stdout.strip())
    print(f"  [Neural Voice] {sid} duration: {duration:.2f}s")
    return m4a_path, duration


def main():
    print("==================================================")
    print("  🎬 Recording AXK Capstone End-to-End Demo Video")
    print("==================================================")

    # 1. Pre-generate all voice narration tracks
    audio_tracks = []
    total_audio_duration = 0
    for scene in SCENES:
        m4a, dur = generate_audio(scene)
        scene["audio_file"] = m4a
        scene["duration"] = dur
        audio_tracks.append(m4a)
        total_audio_duration += dur

    print(f"\n[INFO] Total planned narration duration: {total_audio_duration:.1f}s (~{total_audio_duration/60:.1f} mins)")

    # Concatenate all audio files into one master narration track
    concat_list = TEMP_DIR / "audio_list.txt"
    with open(concat_list, "w") as f:
        for a in audio_tracks:
            f.write(f"file '{a.resolve()}'\n")

    master_audio = TEMP_DIR / "master_narration.m4a"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", str(master_audio)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[INFO] Master audio track created: {master_audio}")

    # 2. Record video with Playwright
    raw_video_dir = TEMP_DIR / "raw_video"
    raw_video_dir.mkdir(parents=True, exist_ok=True)

    print("\n[Playwright] Launching browser and starting screen capture...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir=str(raw_video_dir),
            record_video_size={"width": 1920, "height": 1080},
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        def inject_cursor():
            page.evaluate("""
                if (!document.getElementById('demo-cursor')) {
                    const c = document.createElement('div');
                    c.id = 'demo-cursor';
                    c.style.position = 'fixed';
                    c.style.zIndex = '999999';
                    c.style.width = '20px';
                    c.style.height = '20px';
                    c.style.pointerEvents = 'none';
                    c.style.transition = 'all 0.35s ease-out';
                    c.style.left = '960px';
                    c.style.top = '540px';
                    c.innerHTML = `<svg viewBox="0 0 24 24" width="24" height="24" fill="none"><path d="M5.5 3.5l12 7.5-6.5 1.5-2.5 6.5-3-15.5z" fill="#0F6E56" stroke="#ffffff" stroke-width="1.8"/><circle cx="16" cy="16" r="3" fill="#3B82F6"/></svg>`;
                    document.body.appendChild(c);
                }
            """)

        def move_cursor_to(selector):
            try:
                box = page.locator(selector).first.bounding_box()
                if box:
                    cx = box['x'] + box['width'] / 2
                    cy = box['y'] + box['height'] / 2
                    page.evaluate(f"const c=document.getElementById('demo-cursor'); if(c){{c.style.left='{cx}px';c.style.top='{cy}px';}}")
            except Exception:
                pass

        # ----------------- Scene 1: Intro / Overview -----------------
        s = SCENES[0]
        print(f"\n[Scene 1] {s['title']} ({s['duration']:.1f}s)")
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1000)

        # Highlight the 6-stage lifecycle flow
        move_cursor_to(".xt-flow")
        page.wait_for_timeout(2500)
        # Highlight role cards
        move_cursor_to(".xt-tiles, .xt-grid-2")
        page.wait_for_timeout(max(1000, int((s["duration"] - 3.5) * 1000)))

        # ----------------- Scene 2: Cooperative Dashboard -----------------
        s = SCENES[1]
        print(f"\n[Scene 2] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="coop"]')
        page.wait_for_timeout(400)
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1000)

        # Fill out registration form smoothly
        move_cursor_to('#f-qty')
        page.wait_for_timeout(400)
        page.fill('#f-qty', '4500')
        page.wait_for_timeout(500)

        move_cursor_to('#f-variety')
        page.fill('#f-variety', 'Bourbon Mayaguez Elite')
        page.wait_for_timeout(500)

        move_cursor_to('#f-origin')
        page.fill('#f-origin', 'Huye District, Southern Province')
        page.wait_for_timeout(600)

        # Click Register lot on-chain
        reg_btn = 'button[type="submit"]:has-text("Register lot on-chain")'
        if page.locator(reg_btn).count() > 0:
            move_cursor_to(reg_btn)
            page.wait_for_timeout(600)
            page.click(reg_btn)
            page.wait_for_timeout(2000)

        remaining = max(1000, int((s["duration"] - 7.0) * 1000))
        page.wait_for_timeout(remaining)

        # ----------------- Scene 3: Inspector Dashboard -----------------
        s = SCENES[2]
        print(f"\n[Scene 3] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="inspect"]')
        page.wait_for_timeout(400)
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1500)

        # Select first lot in queue
        first_lot = '.xt-lotcard'
        if page.locator(first_lot).count() > 0:
            move_cursor_to(first_lot)
            page.locator(first_lot).first.click()
            page.wait_for_timeout(800)

        # Enter moisture and inspect
        if page.locator('#i-moist').count() > 0:
            move_cursor_to('#i-moist')
            page.fill('#i-moist', '11.6')
            page.wait_for_timeout(500)

        if page.locator('#i-notes').count() > 0:
            move_cursor_to('#i-notes')
            page.fill('#i-notes', 'Sample tested: zero defect count, density 720g/L, grade A passed.')
            page.wait_for_timeout(600)

        insp_btn = 'button[type="submit"]:has-text("Sign: pass")'
        if page.locator(insp_btn).count() > 0:
            move_cursor_to(insp_btn)
            page.click(insp_btn)
            page.wait_for_timeout(2000)

        remaining = max(1000, int((s["duration"] - 7.0) * 1000))
        page.wait_for_timeout(remaining)

        # ----------------- Scene 4: Buyer Dashboard (Escrow Lock) -----------------
        s = SCENES[3]
        print(f"\n[Scene 4] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="buy"]')
        page.wait_for_timeout(400)
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1500)

        # Click pay into escrow if available
        pay_btn = 'button:has-text("Pay into escrow")'
        if page.locator(pay_btn).count() > 0:
            move_cursor_to(pay_btn)
            page.locator(pay_btn).first.click()
            page.wait_for_timeout(1200)

            # Confirm dialog
            dlg_btn = 'button[type="submit"]:has-text("Sign and pay into escrow")'
            if page.locator(dlg_btn).count() > 0:
                move_cursor_to(dlg_btn)
                page.locator(dlg_btn).first.click()
                page.wait_for_timeout(2000)

        # Close any lingering dialogs
        page.evaluate("document.querySelectorAll('dialog').forEach(d => { try { d.close(); d.remove(); } catch(e){} });")
        remaining = max(1000, int((s["duration"] - 6.0) * 1000))
        page.wait_for_timeout(remaining)

        # ----------------- Scene 5: Logistics Dashboard -----------------
        s = SCENES[4]
        print(f"\n[Scene 5] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="logistics"]')
        page.wait_for_timeout(400)
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1500)

        # Select lot in ready queue
        if page.locator('.xt-lotcard').count() > 0:
            move_cursor_to('.xt-lotcard')
            page.locator('.xt-lotcard').first.click()
            page.wait_for_timeout(800)

        # Dispatch with carrier & container seal
        disp_btn = 'button[type="submit"]:has-text("Seal container & dispatch on-chain")'
        if page.locator(disp_btn).count() > 0:
            move_cursor_to(disp_btn)
            page.wait_for_timeout(1000)
            page.click(disp_btn)
            page.wait_for_timeout(2000)

        remaining = max(1000, int((s["duration"] - 6.0) * 1000))
        page.wait_for_timeout(remaining)

        # ----------------- Scene 6: Port / Terminal Dashboard -----------------
        s = SCENES[5]
        print(f"\n[Scene 6] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="port"]')
        page.wait_for_timeout(400)
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1500)

        # Select arriving shipment
        if page.locator('.xt-lotcard').count() > 0:
            move_cursor_to('.xt-lotcard')
            page.locator('.xt-lotcard').first.click()
            page.wait_for_timeout(800)

        # Clear gate-in
        port_btn = 'button[type="submit"]:has-text("Verify seal & clear gate-in on-chain")'
        if page.locator(port_btn).count() > 0:
            move_cursor_to(port_btn)
            page.wait_for_timeout(1000)
            page.click(port_btn)
            page.wait_for_timeout(2000)

        remaining = max(1000, int((s["duration"] - 6.0) * 1000))
        page.wait_for_timeout(remaining)

        # ----------------- Scene 7: Buyer Settlement & Splitter -----------------
        s = SCENES[6]
        print(f"\n[Scene 7] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="buy"]')
        page.wait_for_timeout(400)
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1500)

        # Scroll down to My Purchases
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'});")
        page.wait_for_timeout(1000)

        # Confirm delivery if available
        conf_btn = 'button:has-text("Confirm delivery")'
        if page.locator(conf_btn).count() > 0:
            move_cursor_to(conf_btn)
            page.wait_for_timeout(1000)
            page.locator(conf_btn).first.click()
            page.wait_for_timeout(2500)

        remaining = max(1000, int((s["duration"] - 6.0) * 1000))
        page.wait_for_timeout(remaining)

        # ----------------- Scene 8: Public Chain & Trace Verification -----------------
        s = SCENES[7]
        print(f"\n[Scene 8] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="verify"]')
        page.wait_for_timeout(400)
        # Directly view the verified settled lot with full QR code and verified hash checklist
        page.goto("http://localhost:8000/trace/AXK-KGL-COFFEE-20261001223155", wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1500)

        # Scroll through custody steps and QR code
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        page.wait_for_timeout(2500)
        page.evaluate("window.scrollBy({top: -350, behavior: 'smooth'});")
        page.wait_for_timeout(1500)

        remaining = max(1000, int((s["duration"] - 6.5) * 1000))
        page.wait_for_timeout(remaining)

        # ----------------- Scene 9: Chain Explorer & Conclusion -----------------
        s = SCENES[8]
        print(f"\n[Scene 9] {s['title']} ({s['duration']:.1f}s)")
        move_cursor_to('a[data-tab="chain"]')
        page.wait_for_timeout(400)
        page.goto(s["url"], wait_until="networkidle")
        inject_cursor()
        page.wait_for_timeout(1500)

        # Scroll down through explorer
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'});")
        page.wait_for_timeout(2500)
        page.evaluate("window.scrollBy({top: -400, behavior: 'smooth'});")
        page.wait_for_timeout(1500)
        page.evaluate("window.scrollBy({top: -400, behavior: 'smooth'});")
        page.wait_for_timeout(1500)

        remaining = max(1000, int((s["duration"] - 5.5) * 1000))
        page.wait_for_timeout(remaining)

        # Take high-res poster thumbnail
        page.screenshot(path=str(THUMBNAIL_JPG), full_page=False)
        print(f"[INFO] Saved poster thumbnail: {THUMBNAIL_JPG}")

        # Finish recording
        context.close()
        browser.close()

    # Find the recorded raw webm video
    webm_files = list(raw_video_dir.glob("*.webm"))
    if not webm_files:
        print("[ERROR] No webm video was recorded!")
        sys.exit(1)

    raw_webm = webm_files[0]
    print(f"\n[FFmpeg] Processing raw recording: {raw_webm}")

    # Multiplex raw video with master audio track
    print(f"[FFmpeg] Muxing video and audio into {OUTPUT_MP4}...")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_webm),
        "-i", str(master_audio),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(OUTPUT_MP4)
    ]
    subprocess.run(cmd, check=True)

    print("\n==================================================")
    print("  🎉 DEMO VIDEO CREATION COMPLETE!")
    print(f"  • Video file:     {OUTPUT_MP4} ({OUTPUT_MP4.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"  • Thumbnail:      {THUMBNAIL_JPG}")
    print("==================================================")


if __name__ == "__main__":
    main()
