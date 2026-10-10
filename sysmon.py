from __future__ import annotations

import argparse
import platform
import time
from collections import deque
from collections.abc import Iterable
from datetime import timedelta
from math import ceil, isfinite
from pathlib import Path

import psutil
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

SPARK = "▁▂▃▄▅▆▇█"
Row = tuple[str, float, str]  # (label, percent, text shown on the right)


def color(percent: float) -> str:
    """Traffic-light colour for a load percentage."""
    return "green" if percent < 60 else "yellow" if percent < 85 else "red"


def human(size: float) -> str:
    """Bytes for humans: 4_800_000 -> '4.6 MB'."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def sparkline(values: Iterable[float], top: float) -> str:
    """Tiny inline chart: [0, 50, 100] -> '▁▅█'."""
    top, last = top or 1, len(SPARK) - 1
    return "".join(SPARK[min(last, round(v / top * last))] for v in values)


def positive_interval(value: str) -> float:
    """Parse a finite, positive refresh interval."""
    try:
        interval = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive number") from error
    if not isfinite(interval) or interval <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return interval


def meters(rows: list[Row]) -> Table:
    """Aligned 'label ━━━━━━ value' rows with traffic-light bars."""
    grid = Table.grid(padding=(0, 1), expand=True)
    grid.add_column(no_wrap=True)
    grid.add_column(ratio=1, min_width=4)
    grid.add_column(justify="right", no_wrap=True)
    for label, percent, text in rows:
        style = color(percent)
        bar = ProgressBar(total=100, completed=percent, style="grey37",
                          complete_style=style, finished_style=style)
        grid.add_row(label, bar, Text(text, style=style))
    return grid


class Dashboard:
    """Reads stats from the OS (via psutil) and renders them with rich."""

    def __init__(self, history: int = 30) -> None:
        self.threads = psutil.cpu_count() or 1
        self.cpu_history: deque[float] = deque(maxlen=history)
        self.down_history: deque[float] = deque(maxlen=history)
        self.net_last = psutil.net_io_counters()
        self.net_time = time.monotonic()
        # psutil measures CPU load *between* two calls, so the first reading is
        # always 0. Take one now so the very first frame already has real data.
        psutil.cpu_percent(percpu=True)
        for _ in psutil.process_iter(["cpu_percent"]):
            pass

    def net_speed(self) -> tuple[float, float]:
        """Download and upload speed in bytes/s since the previous call."""
        now, counters = time.monotonic(), psutil.net_io_counters()
        seconds = max(now - self.net_time, 0.001)
        down = (counters.bytes_recv - self.net_last.bytes_recv) / seconds
        up = (counters.bytes_sent - self.net_last.bytes_sent) / seconds
        self.net_last, self.net_time = counters, now
        return down, up

    def header(self) -> Panel:
        uptime = timedelta(seconds=int(time.time() - psutil.boot_time()))
        info = (f"{platform.system()} {platform.release()} · {platform.machine()}"
                f" · {self.threads} threads · up {uptime}")
        return Panel(Text(info, justify="center"), title="[b cyan]sysmon[/]",
                     subtitle=time.strftime("%H:%M:%S"), border_style="cyan")

    def cpu_panel(self, cores: list[float], columns: int, height: int) -> Panel:
        total = sum(cores) / len(cores)
        self.cpu_history.append(total)
        rows = [(f"{i:>2}", load, f"{load:3.0f}%") for i, load in enumerate(cores)]
        size = ceil(len(rows) / columns)
        grid = Table.grid(expand=True, padding=(0, 2))
        for _ in range(columns):
            grid.add_column(ratio=1)
        grid.add_row(*(meters(rows[i:i + size]) for i in range(0, len(rows), size)))
        trend = Text(f" {sparkline(self.cpu_history, 100)} ", style=color(total))
        return Panel(grid, title=f"[b]CPU[/] {total:.0f}%", subtitle=trend,
                     subtitle_align="left", border_style=color(total), height=height)

    def system_panel(self, height: int) -> Panel:
        ram, swap = psutil.virtual_memory(), psutil.swap_memory()
        disk = psutil.disk_usage(Path.home().anchor)
        rows = [("RAM ", ram.percent, f"{human(ram.used)} / {human(ram.total)}")]
        if swap.total:
            rows.append(("Swap", swap.percent, f"{human(swap.used)} / {human(swap.total)}"))
        rows.append(("Disk", disk.percent, f"{human(disk.used)} / {human(disk.total)}"))

        down, up = self.net_speed()
        self.down_history.append(down)
        trend = sparkline(self.down_history, max(self.down_history))
        network = Group(
            Text.assemble(("↓ ", "green"), f"{human(down)}/s".ljust(11), (trend, "green")),
            Text.assemble(("↑ ", "red"), f"{human(up)}/s"),
        )
        return Panel(Group(meters(rows), Text(), network), title="[b]System[/]",
                     border_style="magenta", height=height)

    def process_panel(self, count: int = 6) -> Panel:
        fields = ["pid", "name", "cpu_percent", "memory_percent"]
        # pid 0 is Windows' "System Idle Process": it reports idle time, not load.
        procs = [p.info for p in psutil.process_iter(fields) if p.info["pid"] != 0]
        procs.sort(key=lambda p: (p["cpu_percent"] or 0, p["memory_percent"] or 0),
                   reverse=True)

        table = Table(box=None, expand=True, pad_edge=False, header_style="bold dim")
        table.add_column("PID", justify="right", style="dim")
        table.add_column("Process", ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column("CPU", justify="right", style="cyan")
        table.add_column("RAM", justify="right", style="magenta")
        for p in procs[:count]:
            cpu = (p["cpu_percent"] or 0) / self.threads  # share of the whole machine
            table.add_row(str(p["pid"]), p["name"] or "?", f"{cpu:.1f}%",
                          f"{p['memory_percent'] or 0:.1f}%")
        return Panel(table, title="[b]Top processes[/]", border_style="blue")

    def render(self) -> Group:
        cores = psutil.cpu_percent(percpu=True)
        columns = 2 if len(cores) > 8 else 1  # many cores -> two columns of bars
        # Both panels share one height: the taller content wins
        # (6 = the lines the System panel needs: RAM, swap, disk, gap, down, up).
        height = max(ceil(len(cores) / columns), 6) + 2
        middle = Table.grid(expand=True, padding=(0, 1))
        middle.add_column(ratio=1)
        middle.add_column(ratio=1)
        middle.add_row(self.cpu_panel(cores, columns, height), self.system_panel(height))
        return Group(self.header(), middle, self.process_panel())


def main() -> None:
    parser = argparse.ArgumentParser(description="Live system dashboard for your terminal.")
    parser.add_argument("-i", "--interval", type=positive_interval, default=1.0,
                        help="seconds between refreshes (default: 1)")
    parser.add_argument("--once", action="store_true",
                        help="print a single snapshot and exit")
    parser.add_argument("--svg", metavar="FILE",
                        help="save a snapshot as an SVG image (implies --once)")
    args = parser.parse_args()

    console = Console(record=bool(args.svg))
    dashboard = Dashboard()
    time.sleep(args.interval)  # give the counters a first real measurement window

    if args.once or args.svg:
        console.print(dashboard.render())
        if args.svg:
            console.save_svg(args.svg, title="sysmon")
        return

    try:
        with Live(console=console, screen=True, auto_refresh=False) as live:
            while True:
                live.update(dashboard.render(), refresh=True)
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
