import json
import os
import platform
import shutil
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TransferSpeedColumn,
)

from core.rotator import WallpaperRotator
from core.web_server import start_web_ui


class Orientation(str, Enum):
    normal = "normal"
    vertical = "vertical"
    all = "all"


class SortMode(str, Enum):
    relevance = "relevance"
    latest = "latest"
    hot = "hot"
    toplist = "toplist"
    random = "random"


SORT_MAP = {
    SortMode.relevance: "relevance",
    SortMode.latest: "date_added",
    SortMode.hot: "hot",
    SortMode.toplist: "toplist",
    SortMode.random: "random",
}

app = typer.Typer(
    name="termpaper",
    help="[bold cyan]TermPaper[/bold cyan] - Terminal-first wallpaper manager.",
    rich_markup_mode="rich",
    add_completion=False,
)
console = Console()

WALLHAVEN_SEARCH_URL = "https://wallhaven.cc/api/v1/search"
CONFIG_DIR = Path.home() / ".config" / "termpaper"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def get_local_images(directory: Path) -> List[Path]:
    """Retrieves all supported image files from a folder."""
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(
        [
            p
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ]
    )


def set_desktop_wallpaper(image_path: Path) -> bool:
    """Sets the given image as desktop wallpaper across Windows, macOS, and Linux DEs."""
    resolved_path = image_path.resolve()
    if not resolved_path.exists():
        console.print(f"[bold red]Image file not found:[/bold red] {resolved_path}")
        return False

    sys_os = platform.system()

    try:
        if sys_os == "Windows":
            import ctypes

            return bool(
                ctypes.windll.user32.SystemParametersInfoW(20, 0, str(resolved_path), 3)
            )

        elif sys_os == "Darwin":  # macOS
            apple_script = f'tell application "System Events" to set picture of every desktop to "{resolved_path}"'
            subprocess.run(["osascript", "-e", apple_script], check=True)
            return True

        elif sys_os == "Linux":
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            file_uri = resolved_path.as_uri()

            if any(
                de in desktop for de in ["gnome", "ubuntu", "cinnamon", "mate", "pop"]
            ):
                subprocess.run(
                    [
                        "gsettings",
                        "set",
                        "org.gnome.desktop.background",
                        "picture-uri",
                        file_uri,
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        "gsettings",
                        "set",
                        "org.gnome.desktop.background",
                        "picture-uri-dark",
                        file_uri,
                    ],
                    check=False,
                )
                return True

            if "kde" in desktop:
                js_script = f"""
                var allDesktops = desktops();
                for (i=0;i<allDesktops.length;i++) {{
                    d = allDesktops[i];
                    d.wallpaperPlugin = "org.kde.image";
                    d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");
                    d.writeConfig("Image", "{file_uri}");
                }}
                """
                subprocess.run(
                    [
                        "qdbus",
                        "org.kde.plasmashell",
                        "/PlasmaShell",
                        "org.kde.PlasmaShell.evaluateScript",
                        js_script,
                    ],
                    check=True,
                )
                return True

            if shutil.which("swww"):
                subprocess.run(["swww", "img", str(resolved_path)], check=True)
                return True

            if shutil.which("feh"):
                subprocess.run(["feh", "--bg-fill", str(resolved_path)], check=True)
                return True
            elif shutil.which("nitrogen"):
                subprocess.run(
                    ["nitrogen", "--set-zoom-fill", str(resolved_path)], check=True
                )
                return True

            subprocess.run(
                [
                    "gsettings",
                    "set",
                    "org.gnome.desktop.background",
                    "picture-uri",
                    file_uri,
                ],
                check=True,
            )
            return True

    except Exception as e:
        console.print(
            f"[bold red]Failed to set wallpaper automatically:[/bold red] {e}"
        )
        return False

    return False


def load_config() -> dict[str, Any]:
    """Loads configuration settings from disk."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(data: dict[str, Any]) -> None:
    """Saves settings to local JSON configuration file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = load_config()
    current.update(data)
    with open(CONFIG_FILE, "w") as f:
        json.dump(current, f, indent=4)


def matches_orientation(item: dict[str, Any], orientation: Orientation) -> bool:
    if orientation == Orientation.all:
        return True

    width = item.get("dimension_x", 0)
    height = item.get("dimension_y", 0)

    if orientation == Orientation.normal:
        return width >= height
    elif orientation == Orientation.vertical:
        return height > width

    return True


def download_wallpapers(
    query: Optional[str],
    output_dir: Path,
    count: int = 1,
    page: int = 1,
    orientation: Orientation = Orientation.all,
    sort: SortMode = SortMode.relevance,
    api_key: Optional[str] = None,
) -> List[Path]:
    current_page = page
    filtered_items: List[dict[str, Any]] = []

    # Fetch pages until we reach the requested image count or run out of API results
    while len(filtered_items) < count:
        params: dict[str, Any] = {
            "sorting": SORT_MAP[sort],
            "purity": "100",
            "page": current_page,
        }

        if query:
            params["q"] = query

        if api_key:
            params["apikey"] = api_key

        response = requests.get(WALLHAVEN_SEARCH_URL, params=params, timeout=15.0)
        response.raise_for_status()
        data = response.json()

        raw_results = data.get("data", [])
        if not raw_results:
            break

        matching_batch = [
            item for item in raw_results if matches_orientation(item, orientation)
        ]
        filtered_items.extend(matching_batch)

        # Check meta info to see if we've hit the total available pages
        meta = data.get("meta", {})
        last_page = meta.get("last_page", current_page)
        if current_page >= last_page:
            break

        current_page += 1

    # Truncate to the requested count limit
    target_items = filtered_items[:count]

    if not target_items:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded_paths: List[Path] = []

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        for idx, item in enumerate(target_items, start=1):
            image_url = item["path"]
            wallpaper_id = item["id"]
            file_extension = Path(image_url).suffix or ".jpg"
            file_path = output_dir / f"{wallpaper_id}{file_extension}"

            try:
                with requests.get(image_url, stream=True, timeout=15.0) as img_response:
                    img_response.raise_for_status()
                    total_size = int(img_response.headers.get("content-length", 0))

                    task = progress.add_task(
                        f"[{idx}/{len(target_items)}] Downloading {wallpaper_id}{file_extension}",
                        total=total_size if total_size > 0 else None,
                    )

                    with open(file_path, "wb") as f:
                        for chunk in img_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                progress.update(task, advance=len(chunk))

                    downloaded_paths.append(file_path)
            except Exception as e:
                console.print(
                    f"[bold red]Failed to download {wallpaper_id}:[/bold red] {e}"
                )

    return downloaded_paths


@app.command(
    epilog="""
[bold yellow]Examples:[/bold yellow]
  $ tp fetch "cyberpunk" -n 1 --set
  $ tp fetch "nature" -p 3 -n 10              # Start fetching from page 3
  $ tp fetch -s hot -ar normal -w
"""
)
def fetch(
    query: Optional[str] = typer.Argument(
        None,
        help="Optional search query string.",
    ),
    count: int = typer.Option(
        1,
        "-n",
        "--count",
        help="Number of wallpapers to fetch.",
        rich_help_panel="Download Options",
    ),
    page: int = typer.Option(
        1,
        "-p",
        "--page",
        help="Page number to start fetching from.",
        rich_help_panel="Download Options",
    ),
    sort: SortMode = typer.Option(
        SortMode.relevance,
        "-s",
        "--sort",
        help="Sort mode: relevance, latest, hot, toplist, or random.",
        case_sensitive=False,
        rich_help_panel="Filters",
    ),
    orientation: Orientation = typer.Option(
        Orientation.all,
        "-ar",
        "--orientation",
        help="Filter image orientation: normal, vertical, or all.",
        case_sensitive=False,
        rich_help_panel="Filters",
    ),
    set_bg: bool = typer.Option(
        False,
        "-w",
        "--set",
        help="Automatically set the first downloaded image as desktop wallpaper.",
        rich_help_panel="Action Options",
    ),
    output_dir: Path = typer.Option(
        Path("./wallpapers"),
        "-o",
        "--output-dir",
        help="Target directory where images are saved.",
        rich_help_panel="Download Options",
    ),
):
    """
    [bold green]Fetch wallpapers from Wallhaven.[/bold green]
    """
    cfg = load_config()
    api_key = cfg.get("api_key")

    search_label = f"'{query}'" if query else "ALL"
    console.print(
        f"[bold cyan]Fetching Wallhaven wallpapers:[/bold cyan] [yellow]{search_label}[/yellow] "
        f"[dim](sort: {sort.value}, count: {count}, page: {page}, orientation: {orientation.value})[/dim]..."
    )

    try:
        downloaded = download_wallpapers(
            query=query,
            output_dir=output_dir,
            count=count,
            page=page,
            orientation=orientation,
            sort=sort,
            api_key=api_key,
        )

        if downloaded:
            file_list = "\n".join([f" • [dim]{p.resolve()}[/dim]" for p in downloaded])
            status_msg = f"[bold green]✓ Downloaded {len(downloaded)} wallpaper(s) successfully![/bold green]"

            if set_bg:
                if set_desktop_wallpaper(downloaded[0]):
                    status_msg += f"\n[bold magenta]🖼 Desktop wallpaper updated to {downloaded[0].name}![/bold magenta]"

            console.print(
                Panel(
                    f"{status_msg}\n\n{file_list}",
                    title="TermPaper Fetch Summary",
                    border_style="green",
                )
            )
        else:
            console.print("[bold red]✗ No matching wallpapers found.[/bold red]")

    except Exception as e:
        console.print(f"[bold red]Error during fetch:[/bold red] {e}")


@app.command()
def set(
    image_path: Path = typer.Argument(
        ...,
        help="Path to local image file to apply as desktop wallpaper.",
    ),
):
    """
    [bold green]Set any local image as your desktop wallpaper directly.[/bold green]
    """
    if set_desktop_wallpaper(image_path):
        console.print(
            f"[bold green]✓ Desktop wallpaper updated successfully to:[/bold green] [yellow]{image_path.resolve()}[/yellow]"
        )
    else:
        console.print("[bold red]✗ Failed to update wallpaper.[/bold red]")


@app.command(
    epilog="""
[bold yellow]Examples:[/bold yellow]
  $ tp rotate ./wallpapers --interval 5        # Change wallpaper every 5 seconds
  $ tp rotate ./wallpapers -i 30 -t            # Run in system tray with controls
  $ tp rotate ./wallpapers -i 10 --shuffle     # Randomize order before cycling
  $ tp rotate ./wallpapers -i 5 --once         # Stop after displaying all images once
"""
)
def rotate(
    folder: Path = typer.Argument(
        Path("./wallpapers"),
        help="Path to folder containing wallpapers. Defaults to ./wallpapers.",
    ),
    interval: int = typer.Option(
        10,
        "-i",
        "--interval",
        help="Delay between wallpaper changes in seconds.",
        rich_help_panel="Rotation Options",
    ),
    loop: bool = typer.Option(
        True,
        "--loop/--once",
        help="Continuously loop through the pictures indefinitely.",
        rich_help_panel="Rotation Options",
    ),
    shuffle: bool = typer.Option(
        False,
        "-s",
        "--shuffle",
        help="Shuffle picture order before cycling.",
        rich_help_panel="Rotation Options",
    ),
    tray: bool = typer.Option(
        False,
        "-t",
        "--tray",
        help="Run in system tray with Pause, Next, and Previous controls.",
        rich_help_panel="Rotation Options",
    ),
):
    """
    [bold green]Cycle through all wallpapers in a folder on a timer.[/bold green]
    """
    resolved = folder.resolve()
    images = get_local_images(resolved)

    if not images:
        console.print(
            f"[bold red]No supported images found in folder:[/bold red] {resolved}"
        )
        return

    console.print(
        f"[bold cyan]🔄 Starting wallpaper rotation from:[/bold cyan] [yellow]{resolved}[/yellow]"
    )
    console.print(
        f"[dim]Interval: {interval}s | Images count: {len(images)}"
        f"{' | System Tray active' if tray else ' | Press Ctrl+C to stop'}[/dim]\n"
    )

    def on_change(img: Path) -> None:
        console.print(
            f"[bold green]▶ Set wallpaper:[/bold green] [yellow]{img.name}[/yellow] "
            f"[dim](next change in {interval}s...)[/dim]"
        )

    rotator = WallpaperRotator(
        folder_path=resolved,
        interval=interval,
        loop=loop,
        shuffle=shuffle,
        on_change_callback=on_change,
    )

    if tray:
        try:
            rotator.run_in_tray()
        except KeyboardInterrupt:
            pass
        finally:
            rotator.stop()
            console.print("\n[bold yellow]⏹ Wallpaper rotation stopped.[/bold yellow]")
    else:
        if not rotator.start():
            console.print(
                "[bold red]✗ Failed to start rotator (already running).[/bold red]"
            )
            return

        try:
            while rotator.is_running():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            rotator.stop()
            console.print("\n[bold yellow]⏹ Wallpaper rotation stopped.[/bold yellow]")

@app.command(
    epilog="""
[bold yellow]Examples:[/bold yellow]
  $ tp ui                     # Open Web UI on default port 5000
  $ tp ui --port 8080         # Open Web UI on port 8080
  $ tp ui --tray              # Launch Web UI in system tray mode
"""
)
def ui(
    port: int = typer.Option(
        5000,
        "-p",
        "--port",
        help="Port number to serve Web UI on.",
        rich_help_panel="Web Options",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host address to bind server to.",
        rich_help_panel="Web Options",
    ),
    tray: bool = typer.Option(
        False,
        "-t",
        "--tray",
        help="Run Web UI in system tray mode.",
        rich_help_panel="Web Options",
    ),
):
    """
    [bold green]Launch the TermPaper Web Gallery in your browser.[/bold green]
    """
    if tray:
        console.print("[bold cyan]📌 Starting TermPaper Web UI in System Tray mode...[/bold cyan]")
    else:
        console.print(f"[bold cyan]🌐 Starting TermPaper Web UI at:[/bold cyan] [yellow]http://{host}:{port}[/yellow]")

    start_web_ui(host=host, port=port, tray=tray)

@app.command(
    epilog="""
[bold yellow]Examples:[/bold yellow]
  $ tp config -k YOUR_API_KEY
  $ tp config --show
"""
)
def config(
    api_key: Optional[str] = typer.Option(
        None,
        "-k",
        "--api-key",
        help="Wallhaven API key to store persistently in ~/.config/termpaper/config.json.",
        rich_help_panel="Settings",
    ),
    show: bool = typer.Option(
        False,
        "--show",
        help="Display currently stored configuration values and file path.",
        rich_help_panel="Settings",
    ),
):
    """
    [bold green]Manage local application configuration.[/bold green]
    """
    if api_key:
        save_config({"api_key": api_key})
        console.print(
            "[bold green]✓ Wallhaven API key saved successfully![/bold green]"
        )

    if show:
        cfg = load_config()
        key_val = cfg.get("api_key")
        masked = f"{key_val[:4]}...{key_val[-4:]}" if key_val else "Not set"
        console.print("[bold cyan]TermPaper Config:[/bold cyan]")
        console.print(f" • File: [dim]{CONFIG_FILE}[/dim]")
        console.print(f" • API Key: [yellow]{masked}[/yellow]")

    if not api_key and not show:
        console.print(
            "Use [bold cyan]tp config -k YOUR_KEY[/bold cyan] to save an API key."
        )


if __name__ == "__main__":
    app()
