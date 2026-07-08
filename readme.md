#### Run a UK borough's bin service without going bankrupt.

Buy the lorries, hire the crews, choose which waste streams to collect — and keep
the residents happy and the recycling targets met before the council slides into
a Section 114 notice. 

Part Transport Tycoon logistics, part local-government black comedy, in an isometric town that keeps living whether you're watching
or not.


[![Watch the game in action](https://img.youtube.com/vi/kwl9lmTJ-dg/0.jpg)](https://www.youtube.com/watch?v=kwl9lmTJ-dg)

#### Why you'll like it


* A living isometric borough — a procedurally-generated town of terraces,
flats and tower blocks split into collection rounds, with day/night, seasons,
weather, and ambient traffic and pedestrians.
*  A fleet worth agonising over — five RCVs with real trade-offs, bought
through three procurement tiers: cheap-but-slow factory orders, premium dealer
stock, or eye-wateringly expensive emergency rentals.
*  Waste policy with teeth — juggle black-bin, recycling, food and garden
collections against landfill tax, recycling credits, contamination and a
statutory diversion target that fines you when you miss it.
* Proper council economics — a startup loan, daily overheads, escalating
landfill tax, public satisfaction, and two ways to lose.
* A full SimCity-style city editor — drag-paint your own borough (zones,
parks, roads, landfill) with live warnings for any bins a lorry can't reach,
then hit Play This City.
*  Spreadsheet management — export your whole plan to a spreadsheet, tweak
it, and import it back.

--------
## Quick start

```
git clone https://github.com/ViciousSquid/the-rubbish-game.git
cd the-rubbish-game
pip install pygame Pillow      # pyexcel-ods too, if you want .ods export
python main.py
```

Only pygame is required. Pillow (truck sprite) and pyexcel-ods (.ods
import/export) are optional and degrade gracefully; everything else is Python
standard library. On some Linux distros you may need python3-tk for the file
dialogs.


-------
## Controls

Play: left-click select · drag pan · wheel zoom · 1–6 windows · F5/F9 quick-save/load · Ctrl+Shift+D debug.

Editor: drag to paint · right-drag pan · R/C zones · P park · D/E road/erase · B bulldoze · L landfill · [ ] brush size · W reach
warnings · H help.
