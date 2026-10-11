# sysmon

A live system dashboard for your terminal. Per-core CPU load, RAM, swap, disk, network speed and the hungriest processes — all on one colourful screen that updates in real time.

Built with [`psutil`](https://github.com/giampaolo/psutil) and [`rich`](https://github.com/Textualize/rich). Single file, under 200 lines, works on Windows, macOS and Linux.

## Features

- **Per-core CPU bars** with a traffic-light scheme (green → yellow → red)
- **Sparklines** showing recent CPU load and download speed (`▁▂▃▅▇█`)
- **RAM, swap and disk** usage at a glance
- **Live network speed** (download / upload)
- **Top processes** by CPU, normalised so 100% means *the whole machine*
- **SVG export** — save a snapshot as an image, perfect for a README or a post

## Install

```bash
git clone https://github.com/l0n3lyy/sysmon.git
cd sysmon
pip install -r requirements.txt
```

Requires Python 3.9+.

## Usage

```bash
python sysmon.py                  # live dashboard, Ctrl+C to quit
python sysmon.py -i 0.5           # refresh twice per second
python sysmon.py --once           # print a single snapshot and exit
python sysmon.py --svg shot.svg   # save a snapshot as an SVG image
```

## How it works

- `psutil` reads raw numbers from the operating system.
- CPU load and network speed are *rates*, so they are computed from the difference between two consecutive samples.
- `rich` turns those numbers into panels, tables and progress bars, and `rich.live.Live` redraws them in place on the terminal's alternate screen, so your shell history stays untouched.
- The sparklines are just the last 30 samples mapped onto eight block characters.

## Ideas for the future

- GPU and temperature sensors
- Sorting processes by RAM with a keypress
- A `--log` flag that writes stats to CSV
