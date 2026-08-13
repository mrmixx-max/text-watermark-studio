import asyncio
import sys

sys.path.insert(0, 'src')
from ai_watermark_toolkit.ui.tui import StudioTUI


async def shot():
    app = StudioTUI()
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.pause()
        out = app.query_one('#out')
        out.write('')
        out.write('[green]Burn-in: 18/18 actions passed.[/]')
        app.query_one('#path').value = 'tests/fixtures/ai_sample_en.txt'
        await pilot.pause()
        app.save_screenshot(r'C:\Users\webma\Downloads\tws-tui.svg')


asyncio.run(shot())
print("SVG ok")
