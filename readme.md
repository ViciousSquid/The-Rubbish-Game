#### Run a UK borough's bin service without going bankrupt.

Buy the lorries, hire the crews, choose which waste streams to collect — and keep
the residents happy and the recycling targets met before the council slides into
a Section 114 notice.

Part Transport Tycoon logistics, part local-government black comedy, in an isometric town that keeps living whether you're watching
or not.

[**Download version 1.1 for Windows and Android**](https://github.com/ViciousSquid/The-Rubbish-Game/releases)

[![Watch the game in action](https://img.youtube.com/vi/kwl9lmTJ-dg/0.jpg)](https://www.youtube.com/watch?v=kwl9lmTJ-dg)

---

## Why you'll like it

### 🏙️ A living borough

Every game takes place in a procedurally-generated isometric UK town filled with
terraces, semis, bungalows, flats, shops, offices and tower blocks.

The borough is divided into collection rounds, and every property contributes
to the simulation. Buildings have different populations and waste-generation
rates, so a quiet street of bungalows creates a very different problem from a
tower-block estate.

The town doesn't stop being a town when you open a menu. Day and night, seasons,
weather, traffic and pedestrians continue to bring it to life.

### 🚛 Run the fleet

Your fleet is the heart of the operation.

Buy and manage five different RCVs, each with its own strengths and weaknesses.
Vehicles have to navigate the actual road network and service the rounds you've
scheduled.

Getting the right truck is only half the problem. You also have to get it to
the right place at the right time.

Need a vehicle immediately?

Procurement offers three tiers:

* **Factory orders** — cheap, but slow.
* **Dealer stock** — faster, but more expensive.
* **Emergency rentals** — available when you desperately need them, at an
  eye-watering price.

### ♻️ Waste policy actually matters

You decide what your borough collects.

Balance:

* Black-bin waste
* Recycling
* Food waste
* Garden waste
* Landfill tax
* Recycling credits
* Contamination
* Statutory diversion targets

Collecting everything isn't necessarily the right answer.

Collect too little and residents suffer.

Collect too much and the council's finances do.

Miss the statutory recycling/diversion target and the penalties start to hurt.

### 💷 Run the council

This is a management game, not just a routing puzzle.

You start with a limited budget and a startup loan, then have to balance:

* Fleet purchases
* Crew and operating costs
* Daily overheads
* Landfill costs
* Procurement
* Recycling income
* Public satisfaction
* Waste policy

Landfill tax escalates over time, making an inefficient waste strategy
progressively more expensive.

There are two ways to lose.

Neither is particularly dignified.

### 🏗️ Build your own borough

The built-in city editor lets you create your own waste-management nightmare.

Drag-paint:

* Residential zones
* Commercial zones
* Parks and green space
* Roads
* Landfill sites

The editor understands the same city used by the simulation. There is no
separate level-building pipeline.

Build a city, save it, and **Play This City**.

The game will even warn you when buildings are unreachable by the road network,
so you can discover your planning mistakes before the bins do.

### 📊 Manage it your way

Prefer spreadsheets to buttons?

Export your entire collection plan to a spreadsheet, make your changes there,
and import it back into the game.

The borough is data, not just scenery.

---

## The simulation

The Rubbish Game is built around a simple chain of cause and effect:

**Buildings produce waste → rounds need servicing → vehicles collect it →
waste streams affect the finances → policy affects recycling performance →
the council reacts.**

Every part of the system feeds into another.

A tower block creates more waste.

More waste requires more collection capacity.

More vehicles cost more money.

Sending everything to landfill costs more as landfill tax rises.

Switching to recycling can improve your diversion performance — but introduces
contamination and processing considerations.

And meanwhile, the residents still expect their bins to disappear on collection
day.

---

## The city editor

The editor is not a separate development tool. It is part of the game.

You can start with:

* A complete procedurally-generated borough
* A partially-developed city
* A blank map

Then reshape it yourself.

Roads, zones, parks and infrastructure can be painted directly onto the
isometric map. Brush size can be changed while working, and reach warnings show
you which properties cannot be serviced.

When you're finished, hit **Play This City**.

The exact city you built becomes the simulation.

---

## Spreadsheet management

For players who want to plan their borough outside the game, collection plans
can be exported and imported as spreadsheets.

This makes it possible to:

1. Build or generate a borough.
2. Export the collection plan.
3. Optimise it in a spreadsheet.
4. Import the changes.
5. Run the resulting schedule in-game.

The spreadsheet isn't just an export of statistics — it can be part of the
management workflow.

---

## Android

The same codebase builds for Android with Buildozer (SDL2).

The game adapts its controls for touch:

* Tap to select
* Drag to pan
* Pinch to zoom
* On-screen controls for windows and simulation speed

See `docs/ANDROID.md` for build instructions, or grab the APK from the
**Build Android APK** GitHub Actions workflow.

---

## Quick start

```bash
git clone https://github.com/ViciousSquid/the-rubbish-game.git
cd the-rubbish-game
pip install pygame Pillow      # pyexcel-ods too, if you want .ods export
python main.py
```

Only `pygame` is required.

`Pillow` provides the truck sprite support and `pyexcel-ods` enables `.ods`
import/export. Both are optional and degrade gracefully.

Everything else uses the Python standard library.

On some Linux distributions you may also need `python3-tk` for file dialogs.

---

## Controls

### Play

| Control        | Action       |
| -------------- | ------------ |
| Left click     | Select       |
| Drag           | Pan          |
| Mouse wheel    | Zoom         |
| `1–6`          | Open windows |
| `F5`           | Quick-save   |
| `F9`           | Quick-load   |
| `Ctrl+Shift+D` | Debug        |

### Editor

| Control    | Action             |
| ---------- | ------------------ |
| Drag       | Paint              |
| Right-drag | Pan                |
| `R`        | Residential zone   |
| `C`        | Commercial zone    |
| `P`        | Park / green space |
| `D`        | Road               |
| `E`        | Erase road         |
| `B`        | Bulldoze           |
| `L`        | Landfill           |
| `[` / `]`  | Brush size         |
| `W`        | Reach warnings     |
| `H`        | Help               |

---

## Technology

The game is written in Python and uses Pygame.

The simulation, city editor and renderer operate on the same underlying city
state, allowing a city to move directly from **editing to playing** without an
intermediate map conversion or compilation step.

It is designed to remain lightweight enough to run on both desktop and mobile
hardware.

---

## The objective

- Keep the borough running.

- Keep the rubbish moving.

- Keep the residents happy.

- Hit the recycling targets.

- Don't run out of money.

And above all:

**Don't let the bins win.**
