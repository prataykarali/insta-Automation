#!/usr/bin/env python3
import asyncio
import os
import sys

os.chdir('/home/pratay-karali/AURA-Automation')
sys.path.insert(0, '/home/pratay-karali/AURA-Automation')

from gemini_aura_gen import generate

async def main():
    print("=" * 80)
    print("STARTING DEBUG MODE - UI INSPECTION ONLY")
    print("=" * 80)
    
    result = await generate(
        topic="Spring in Japan",
        progress_cb=None,
        debug_mode=True
    )
    
    print("\n" + "=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
