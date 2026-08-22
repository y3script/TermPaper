import os
import platform
import random
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, List, Optional
import pystray
from PIL import Image, ImageDraw
import base64
import io

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def set_desktop_wallpaper(image_path: Path) -> bool:
    """Sets the given image as desktop wallpaper across OS platforms."""
    resolved_path = image_path.resolve()
    if not resolved_path.exists():
        return False

    sys_os = platform.system()

    try:
        if sys_os == "Windows":
            import ctypes
            return bool(ctypes.windll.user32.SystemParametersInfoW(20, 0, str(resolved_path), 3))

        elif sys_os == "Darwin":  # macOS
            apple_script = f'tell application "System Events" to set picture of every desktop to "{resolved_path}"'
            subprocess.run(["osascript", "-e", apple_script], check=True)
            return True

        elif sys_os == "Linux":
            desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            file_uri = resolved_path.as_uri()

            if any(de in desktop for de in ["gnome", "ubuntu", "cinnamon", "mate", "pop"]):
                subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", file_uri], check=True)
                subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", file_uri], check=False)
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
                    ["qdbus", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", js_script],
                    check=True,
                )
                return True

            if shutil.which("swww"):
                subprocess.run(["swww", "img", str(resolved_path)], check=True)
                return True

            if shutil.which("feh"):
                subprocess.run(["feh", "--bg-fill", str(resolved_path)], check=True)
                return True

            subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", file_uri], check=True)
            return True

    except Exception:
        return False

    return False


def get_local_images(directory: Path) -> List[Path]:
    """Retrieves all supported image files from a directory."""
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted([
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ])


def create_tray_icon_image() -> Image.Image:
    """Decodes a base64 string and returns a 64x64 PIL Image for the system tray."""
    # Decode the Base64 string to bytes
    icon_base64 = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAMAAACdt4HsAAAAgVBMVEVHcExoE+FnE+FnE+FnE+FmE+FrFuFiD+FoE+FfDeFxGuH///9kEeFyGuFnE+FtFuFhD+FvGOF1HOF+IuF4HuF7IOFqFeGCJeKGJ+KKKuLStfZfDeGxg++1h++9jfDbxPiBMeT28P2gZOv9+//t4fyNQOaXU+nk0/qqdu7NrvXAlvLOhlZVAAAAC3RSTlMA1ziQIQG07+VsbH0U4VAAAAP2SURBVFjDlZfpdqowAISDINjWsIQgLigBBYH3f8CbfWGpvfOj51QyHzOJEQKA0j74Cr0ovVGlG+LXIi/8CvZgrv3OP/ABm27DuN0O/m6GCPzo9ge7QUR+YPt33sJ+nGmBCHcL/6Z5ARE9dq7/k9tlMIcnCYHtP36UTRDz4K/bY0erKVKfrcUuUv4t8xKiQkS0xN6X/g/uGUMiaITg4PrjD3IIt0MAvpz4s7bL/uZf4fsC4cwek3aoNjS0JJ4hQuA5/pQ8Xs+fTT1fj9Ih3DwQKT8PS+qfD6rJ0dRK0wgc/8/PCNbEpEeQ2tP1YCOa+rqikapu2PWHPbUpsP3kRa+/e5RtCPZvOuBFbAIw/lPc0vlr+jjZVNzTDM+WDtUEYPyneGAVERuJ6N/Z7TkBsUka2FhFAMZ/iit69UpHoqG+tnBZgUKvdEjFB0sCMH4DGFiVNlkhGIAiAOOXAChy/owsAqRyptEAJAEYf3ISgAxdBcCRDaBDNQEYvwZkbcMqZBAuGApgCBqQWADcjmOL5uYkgwaQ2ADpVwA2HCH3/mX7mAZCP9MARQC6QJIlHKDvjLRgV9N1eb5bCUiyRJcAOgDNeDcAhGz/W+yjpsoZ4J5kmY4AjN8AkCuzR59jLQGaAGSBzALM/OXIvO9a/9DcxWhRApgACqCFmVAxcX9XPpoZIFEA6ZcATEtjQkrhx7hid371lNe+bIAkAF2ArrIC9OP7VVeE2Qv2paLfKopDqBOTcc9gpksAHQBqQCuyjgRh1LO7PgcRBpHpKQBQRwAqAFQA4eGEvhu4/1HIOiivJQCqCEuAWHQ+5Y34iR9LrAj4ugSIBlABarGXh5f+Gb6Sgon7Cw2AsgMwASC8G4+e8ue1K6Q0QO9vA+DfXg14d7gouundNE09kKIwBAlAOsIJJEvAq8d8POn7jhQ5kyIsAAnQDZACNC3zS1uuJBESgHQHYAJIwPNu+ywxf24BoAtACjCV634RSAHQKqDiDy7jL6UMoWSLXG0BkHi04cK1G0SBxaMNbQE68XA9G++ZylDO4uHauQDjx3jafrwzicf7xDamJgC9iGz//+0FA3OCXEgQ2YCi+/yK02ELACPgJTYAk+n3l6yJ8J2pE3ggdAB0Cbu2emyoartcbCoFSELwnc0AebFYRL2QRT4DZN/0ZX8OyM0KGmmKC6Av/HufR1gAzucVggugRva+vztsAy5MvwD4qYdF4B0cgPErxAzAG/ADBwjCDcDlYhNWAGGgDl2qw18BooE6dNFTq7cGuFwcwgLg7axzb6g7fAbIBvbBkx19DybCbwAV4OAefdlE+B62IqwCVADsLQ7ftMY++A69fKOD1aD0wm/r+P8P714REZPx0v8AAAAASUVORK5CYII="
    image_data = base64.b64decode(icon_base64)
    
    # Load the image bytes into Pillow
    image = Image.open(io.BytesIO(image_data))
    
    # Optional: Ensure it's scaled to 64x64 if necessary
    if image.size != (64, 64):
        image = image.resize((64, 64), Image.Resampling.LANCZOS)
        
    return image


class WallpaperRotator:
    """Thread-safe background wallpaper rotation manager with Tray controls."""

    def __init__(
        self,
        folder_path: Path,
        interval: int = 10,
        loop: bool = True,
        shuffle: bool = False,
        on_change_callback: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self.folder_path = Path(folder_path)
        self.interval = interval
        self.loop = loop
        self.shuffle = shuffle
        self.on_change_callback = on_change_callback

        self.images: List[Path] = []
        self.current_index: int = 0
        self.current_image: Optional[Path] = None
        self.is_paused: bool = False

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._step_event = threading.Event()
        self._tray_icon: Optional[pystray.Icon] = None # pyright: ignore[reportInvalidTypeForm]

    def _apply_wallpaper(self, index: int) -> bool:
        if not self.images:
            return False
        self.current_index = index % len(self.images)
        img = self.images[self.current_index]

        if set_desktop_wallpaper(img):
            self.current_image = img
            if self.on_change_callback:
                self.on_change_callback(img)
            return True
        return False

    def next_wallpaper(self) -> None:
            """Switch to the next wallpaper immediately."""
            if self.images:
                self.current_index = (self.current_index + 1) % len(self.images)
                self._step_event.set()

    def previous_wallpaper(self) -> None:
        """Switch to the previous wallpaper immediately."""
        if self.images:
            self.current_index = (self.current_index - 1) % len(self.images)
            self._step_event.set()

    def toggle_pause(self) -> None:
        """Toggles rotation pause state."""
        self.is_paused = not self.is_paused
        self._step_event.set()

    def _run(self) -> None:
        """Internal loop executed in a background thread."""
        self.images = get_local_images(self.folder_path)
        if not self.images:
            return

        if self.shuffle:
            random.shuffle(self.images)

        while not self._stop_event.is_set():
            if not self.is_paused:
                self._apply_wallpaper(self.current_index)

                if not self.loop and self.current_index == len(self.images) - 1:
                    break

            # Wait for interval duration, unblocking instantly on stop or manual skip
            signaled = self._step_event.wait(timeout=self.interval)
            self._step_event.clear()

            # Advance index on normal timer expiration (not triggered by manual skip/pause)
            if not signaled and not self.is_paused:
                self.current_index = (self.current_index + 1) % len(self.images)

    def start(self) -> bool:
        """Starts background rotation."""
        if self.is_running():
            return False

        self._stop_event.clear()
        self._step_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stops background rotation and destroys tray icon."""
        self._stop_event.set()
        self._step_event.set()

        if self._tray_icon is not None:
            self._tray_icon.stop()
            self._tray_icon = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_running(self) -> bool:
        """Checks if rotation is currently active."""
        return self._thread is not None and self._thread.is_alive()

    def run_in_tray(self) -> None:
        """Starts the rotator and attaches system tray controls (blocking main thread)."""
        self.start()

        def get_pause_label(item: Any) -> str:
            return "Resume" if self.is_paused else "Pause"

        menu = pystray.Menu(
            pystray.MenuItem(get_pause_label, lambda icon, item: self.toggle_pause()),
            pystray.MenuItem("Next Wallpaper", lambda icon, item: self.next_wallpaper()),
            pystray.MenuItem("Previous Wallpaper", lambda icon, item: self.previous_wallpaper()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.stop()),
        )

        icon = pystray.Icon(
            "TermPaper",
            create_tray_icon_image(),
            "TermPaper Rotator",
            menu=menu,
        )
        self._tray_icon = icon
        icon.run()

    def get_status(self) -> dict[str, Any]:
        """Returns status representation."""
        return {
            "is_running": self.is_running(),
            "is_paused": self.is_paused,
            "interval": self.interval,
            "folder": str(self.folder_path.resolve()),
            "current_image": str(self.current_image.resolve()) if self.current_image else None,
        }
