import os
from pathlib import Path
import sqlite3
import webbrowser
from typing import Any, Dict

from PIL import Image, ImageDraw
import pystray
import threading
import base64
import io

from flask import Flask, jsonify, render_template_string, request, Response,cli
import logging
import requests

from core.rotator import set_desktop_wallpaper

app = Flask(__name__)

WALLHAVEN_SEARCH_URL = "https://wallhaven.cc/api/v1/search"
DOWNLOAD_DIR = Path("./wallpapers").resolve()
DB_PATH = Path("./favorites.db").resolve()

# Map UI section names to Wallhaven API sorting parameters
SORT_MAP = {
    "latest": "date_added",
    "hot": "hot",
    "toplist": "toplist",
    "random": "random",
}


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS favorites (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                dimension TEXT NOT NULL,
                thumb_small TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    conn.close()


# Initialize database table on server start
init_db()

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TermPaper Web UI</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            --fav-bg: #ef4444;
            --fav-hover: #dc2626;
            --text: #f8fafc;
            --text-muted: #94a3b8;
        }
        body {
            margin: 0;
            font-family: system-ui, -apple-system, sans-serif;
            background-color: var(--bg-color);
            color: var(--text);
        }
        header {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(15, 23, 42, 0.9);
            backdrop-filter: blur(8px);
            border-bottom: 1px solid #334155;
            padding: 1rem 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .logo { font-size: 1.25rem; font-weight: bold; color: var(--accent); }
        .nav-links { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        .nav-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-muted);
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }
        .nav-btn:hover, .nav-btn.active {
            color: var(--text);
            background: var(--card-bg);
            border-color: #475569;
        }
        .search-box {
            display: flex;
            gap: 0.5rem;
            flex: 1;
            max-width: 360px;
        }
        .search-input {
            width: 100%;
            padding: 0.5rem 0.8rem;
            border-radius: 0.375rem;
            border: 1px solid #334155;
            background: #0f172a;
            color: var(--text);
            font-size: 0.9rem;
            outline: none;
        }
        .search-input:focus { border-color: var(--accent); }
        .search-btn {
            background: var(--accent);
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-weight: 500;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.25rem;
            padding: 2rem;
        }
        .card {
            background: var(--card-bg);
            border-radius: 0.5rem;
            overflow: hidden;
            position: relative;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .card:hover {
            transform: translateY(-4px);
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
        }
        .card img {
            width: 100%;
            height: 220px;
            object-fit: cover;
            display: block;
        }
        .card-info {
            padding: 0.6rem 0.8rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #111827;
        }
        .badge {
            font-size: 0.75rem;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            background: #334155;
            color: var(--text-muted);
        }

        /* Preview Modal */
        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.85);
            backdrop-filter: blur(5px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            padding: 1.5rem;
        }
        .modal-overlay.active { display: flex; }
        .modal-content {
            background: var(--card-bg);
            border-radius: 0.75rem;
            max-width: 90vw;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
            box-shadow: 0 20px 25px -5px rgba(0,0,0,0.7);
        }
        .close-btn {
            position: absolute;
            top: 1rem;
            right: 1rem;
            background: rgba(0,0,0,0.6);
            color: white;
            border: none;
            font-size: 1.5rem;
            border-radius: 50%;
            width: 2.5rem;
            height: 2.5rem;
            cursor: pointer;
            z-index: 10;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .close-btn:hover { background: rgba(239, 68, 68, 0.8); }
        .modal-img-container {
            flex: 1;
            overflow: auto;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #000;
        }
        .modal-img {
            max-width: 100%;
            max-height: 75vh;
            object-fit: contain;
        }
        .modal-footer {
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #111827;
            border-top: 1px solid #334155;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .btn-group {
            display: flex;
            gap: 0.5rem;
        }
        .set-btn {
            background: var(--accent);
            color: white;
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 600;
            transition: background 0.2s;
        }
        .set-btn:hover { background: var(--accent-hover); }
        .fav-btn {
            background: #334155;
            color: #f8fafc;
            border: 1px solid #475569;
            padding: 0.6rem 1.2rem;
            border-radius: 0.375rem;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 600;
            transition: all 0.2s;
        }
        .fav-btn:hover { background: #475569; }
        .fav-btn.active {
            background: var(--fav-bg);
            border-color: #dc2626;
            color: white;
        }
        .fav-btn.active:hover { background: var(--fav-hover); }

        #loader {
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
        }
        .empty-msg {
            grid-column: 1 / -1;
            text-align: center;
            color: var(--text-muted);
            padding: 4rem 1rem;
            font-size: 1.1rem;
        }
        /* Custom Toast Notification Container */
        #toast-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 2000;
            display: flex;
            flex-direction: column;
            gap: 10px;
            pointer-events: none;
        }

        .toast {
            background: #1e293b;
            color: #f8fafc;
            border: 1px solid #334155;
            border-left: 4px solid var(--accent);
            padding: 0.75rem 1.25rem;
            border-radius: 0.375rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
            font-size: 0.9rem;
            font-weight: 500;
            opacity: 0;
            transform: translateY(20px);
            transition: opacity 0.3s ease, transform 0.3s ease;
            pointer-events: auto;
        }

        .toast.show {
            opacity: 1;
            transform: translateY(0);
        }

        .toast.toast-error {
            border-left-color: #ef4444;
        }

        .toast.toast-success {
            border-left-color: #22c55e;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo">🖼 TermPaper</div>
        
        <div class="search-box">
            <input type="text" id="search-input" class="search-input" placeholder="Search wallpapers (e.g. Cyberpunk, Nature)..." onkeyup="handleSearchKey(event)">
            <button class="search-btn" onclick="executeSearch()">Search</button>
        </div>

        <nav class="nav-links">
            <button class="nav-btn active" data-section="latest" onclick="switchSection('latest')">Latest</button>
            <button class="nav-btn" data-section="hot" onclick="switchSection('hot')">Hot</button>
            <button class="nav-btn" data-section="toplist" onclick="switchSection('toplist')">Toplist</button>
            <button class="nav-btn" data-section="random" onclick="switchSection('random')">Random</button>
            <button class="nav-btn" data-section="favorites" onclick="switchSection('favorites')">❤️ Favorites</button>
        </nav>
    </header>

    <div id="wallpaper-grid" class="grid"></div>
    <div id="loader">Loading wallpapers...</div>

    <!-- Wallpaper Detail Modal -->
    <div id="preview-modal" class="modal-overlay" onclick="closeModalOnBackdrop(event)">
        <div class="modal-content">
            <button class="close-btn" onclick="closeModal()">&times;</button>
            <div class="modal-img-container">
                <img id="modal-img" class="modal-img" src="" alt="Wallpaper Preview">
            </div>
            <div class="modal-footer">
                <div>
                    <span id="modal-dim" class="badge"></span>
                    <span id="modal-id" class="badge" style="margin-left: 0.5rem;"></span>
                </div>
                <div class="btn-group">
                    <button id="modal-fav-btn" class="fav-btn">🤍 Favorite</button>
                    <button id="modal-save-btn" class="fav-btn">💾 Save</button>
                    <button id="modal-set-btn" class="set-btn">Set as Wallpaper</button>
                </div>
            </div>
        </div>
    </div>
    <div id="toast-container"></div>
    <script>
        let currentSection = 'latest';
        let searchQuery = '';
        let currentPage = 1;
        let isLoading = false;
        let hasMore = true;
        let currentActiveWallpaper = null;

        // --- SQLITE FAVORITES API CALLS ---
        async function checkIsFavorite(id) {
            try {
                const res = await fetch(`/api/favorites/check?id=${encodeURIComponent(id)}`);
                const data = await res.json();
                return data.is_favorite;
            } catch (e) {
                return false;
            }
        }

        async function toggleFavorite(wp) {
            try {
                const isFav = await checkIsFavorite(wp.id);
                if (isFav) {
                    await fetch('/api/favorites', {
                        method: 'DELETE',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: wp.id })
                    });
                } else {
                    await fetch('/api/favorites', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(wp)
                    });
                }
                updateFavButton(wp.id);

                if (currentSection === 'favorites') {
                    renderFavorites();
                }
            } catch (err) {
                console.error("Failed to toggle favorite:", err);
            }
        }

        async function updateFavButton(id) {
            const favBtn = document.getElementById('modal-fav-btn');
            const isFav = await checkIsFavorite(id);
            if (isFav) {
                favBtn.innerText = '❤️ Saved in Favorites';
                favBtn.classList.add('active');
            } else {
                favBtn.innerText = '🤍 Favorite';
                favBtn.classList.remove('active');
            }
        }

        async function renderFavorites() {
            const grid = document.getElementById('wallpaper-grid');
            grid.innerHTML = '';
            document.getElementById('loader').style.display = 'none';

            try {
                const res = await fetch('/api/favorites');
                const favs = await res.json();

                if (!favs || favs.length === 0) {
                    grid.innerHTML = '<div class="empty-msg">No favorite wallpapers saved in SQLite database yet.<br>Click "Favorite" on any wallpaper preview to save it.</div>';
                    return;
                }

                favs.forEach(wp => {
                    const card = document.createElement('div');
                    card.className = 'card';
                    card.onclick = () => openModal(wp);
                    card.innerHTML = `
                        <img src="${wp.thumbs.small}" loading="lazy" alt="Wallpaper">
                        <div class="card-info">
                            <span class="badge">${wp.dimension}</span>
                            <span class="badge">#${wp.id}</span>
                        </div>
                    `;
                    grid.appendChild(card);
                });
            } catch (e) {
                console.error("Failed to fetch favorites:", e);
                grid.innerHTML = '<div class="empty-msg">Failed to load favorites.</div>';
            }
        }

        // --- WALLPAPER API FETCHING ---
        async function fetchWallpapers() {
            if (isLoading || !hasMore || currentSection === 'favorites') return;
            isLoading = true;
            document.getElementById('loader').style.display = 'block';

            try {
                let url = `/api/wallpapers?sort=${currentSection}&page=${currentPage}`;
                if (searchQuery) {
                    url += `&query=${encodeURIComponent(searchQuery)}`;
                }

                const res = await fetch(url);
                const data = await res.json();
                
                if (!data.wallpapers || data.wallpapers.length === 0) {
                    hasMore = false;
                    document.getElementById('loader').innerText = currentPage === 1 ? 'No wallpapers found.' : 'No more wallpapers.';
                    return;
                }

                const grid = document.getElementById('wallpaper-grid');
                data.wallpapers.forEach(wp => {
                    const card = document.createElement('div');
                    card.className = 'card';
                    card.onclick = () => openModal(wp);
                    card.innerHTML = `
                        <img src="${wp.thumbs.small}" loading="lazy" alt="Wallpaper">
                        <div class="card-info">
                            <span class="badge">${wp.dimension}</span>
                            <span class="badge">#${wp.id}</span>
                        </div>
                    `;
                    grid.appendChild(card);
                });

                currentPage++;
            } catch (err) {
                console.error("Failed to load wallpapers:", err);
            } finally {
                isLoading = false;
                document.getElementById('loader').style.display = 'none';
            }
        }

        function resetGrid() {
            currentPage = 1;
            hasMore = true;
            document.getElementById('wallpaper-grid').innerHTML = '';
        }

        function switchSection(section) {
            currentSection = section;
            searchQuery = '';
            document.getElementById('search-input').value = '';
            resetGrid();
            
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-section') === section);
            });
            
            if (section === 'favorites') {
                hasMore = false;
                renderFavorites();
            } else {
                fetchWallpapers();
            }
        }

        function executeSearch() {
            const val = document.getElementById('search-input').value.trim();
            if (!val) return;
            searchQuery = val;
            currentSection = 'search';
            resetGrid();
            
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            fetchWallpapers();
        }

        function handleSearchKey(event) {
            if (event.key === 'Enter') {
                executeSearch();
            }
        }

        function openModal(wp) {
            currentActiveWallpaper = wp;
            // Route image loading through the backend proxy
            document.getElementById('modal-img').src = `/api/proxy_image?url=${encodeURIComponent(wp.path)}`;
            document.getElementById('modal-dim').innerText = wp.dimension;
            document.getElementById('modal-id').innerText = `ID: ${wp.id}`;
            
            const setBtn = document.getElementById('modal-set-btn');
            setBtn.onclick = () => applyWallpaper(wp.path, wp.id);
            setBtn.innerText = 'Set as Wallpaper';

            const saveBtn = document.getElementById('modal-save-btn');
            saveBtn.onclick = () => downloadWallpaper(wp.path, wp.id);

            const favBtn = document.getElementById('modal-fav-btn');
            favBtn.onclick = () => toggleFavorite(wp);
            updateFavButton(wp.id);

            document.getElementById('preview-modal').classList.add('active');
        }

        // Function to download image directly to user's downloads folder
        async function downloadWallpaper(url, id) {
            const saveBtn = document.getElementById('modal-save-btn');
            saveBtn.innerText = '💾 Saving...';

            try {
                const proxyUrl = `/api/proxy_image?url=${encodeURIComponent(url)}`;
                const response = await fetch(proxyUrl);
                const blob = await response.blob();
                
                // Extract file extension or default to jpg
                const ext = url.split('.').pop().split(/\#|\?/)[0] || 'jpg';
                const filename = `wallpaper_${id}.${ext}`;

                // Create temporary download link
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(link.href);

                saveBtn.innerText = '💾 Saved!';
                setTimeout(() => { saveBtn.innerText = '💾 Save'; }, 2000);
            } catch (err) {
                console.error('Download error:', err);
                showNotification('Failed to download image.', 'error');
                saveBtn.innerText = '💾 Save';
            }
        }

        function closeModal() {
            document.getElementById('preview-modal').classList.remove('active');
            document.getElementById('modal-img').src = '';
        }

        function closeModalOnBackdrop(e) {
            if (e.target.id === 'preview-modal') {
                closeModal();
            }
        }

        async function applyWallpaper(url, id) {
            const setBtn = document.getElementById('modal-set-btn');
            setBtn.innerText = 'Setting...';

            try {
                const res = await fetch('/api/set', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url, id: id })
                });
                const result = await res.json();
                showNotification(result.message, 'success')
                setBtn.innerText = 'Set as Wallpaper';
            } catch (err) {
                showNotification('Failed to set wallpaper.', 'error')
                setBtn.innerText = 'Set as Wallpaper';
            }
        }

        function showNotification(message, type = 'info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            toast.innerText = message;

            container.appendChild(toast);

            // Trigger animation
            requestAnimationFrame(() => {
                toast.classList.add('show');
            });

            // Auto-remove after 3 seconds
            setTimeout(() => {
                toast.classList.remove('show');
                toast.addEventListener('transitionend', () => {
                    toast.remove();
                });
            }, 3000);
        }

        // Infinite Scroll
        window.addEventListener('scroll', () => {
            if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
                fetchWallpapers();
            }
        });

        // Initial Load
        fetchWallpapers();
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/wallpapers")
def api_wallpapers():
    sort_query = request.args.get("sort", "latest")
    page = request.args.get("page", 1, type=int)
    query = request.args.get("query", "").strip()

    sorting_param = SORT_MAP.get(sort_query, "date_added")

    params: Dict[str, Any] = {
        "sorting": sorting_param,
        "page": page,
        "purity": "100",
    }

    if query:
        params["q"] = query

    try:
        res = requests.get(WALLHAVEN_SEARCH_URL, params=params, timeout=10.0)
        res.raise_for_status()
        data = res.json()

        wallpapers = [
            {
                "id": item["id"],
                "path": item["path"],
                "dimension": f"{item['dimension_x']}x{item['dimension_y']}",
                "thumbs": item["thumbs"],
            }
            for item in data.get("data", [])
        ]
        return jsonify({"wallpapers": wallpapers})
    except Exception as e:
        return jsonify({"error": str(e), "wallpapers": []}), 500


@app.route("/api/favorites", methods=["GET"])
def get_favorites():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, path, dimension, thumb_small FROM favorites ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    favorites = [
        {
            "id": row["id"],
            "path": row["path"],
            "dimension": row["dimension"],
            "thumbs": {"small": row["thumb_small"]},
        }
        for row in rows
    ]
    return jsonify(favorites)


@app.route("/api/favorites/check", methods=["GET"])
def check_favorite():
    wp_id = request.args.get("id")
    if not wp_id:
        return jsonify({"is_favorite": False})

    conn = get_db_connection()
    row = conn.execute(
        "SELECT 1 FROM favorites WHERE id = ?", (wp_id,)
    ).fetchone()
    conn.close()

    return jsonify({"is_favorite": row is not None})


@app.route("/api/favorites", methods=["POST"])
def add_favorite():
    data = request.get_json() or {}
    wp_id = data.get("id")
    path = data.get("path")
    dimension = data.get("dimension")
    thumb_small = data.get("thumbs", {}).get("small")

    if not all([wp_id, path, dimension, thumb_small]):
        return jsonify({"status": "error", "message": "Missing wallpaper data"}), 400

    conn = get_db_connection()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO favorites (id, path, dimension, thumb_small)
            VALUES (?, ?, ?, ?)
            """,
            (wp_id, path, dimension, thumb_small),
        )
    conn.close()
    return jsonify({"status": "success", "message": "Saved to favorites"})


@app.route("/api/favorites", methods=["DELETE"])
def remove_favorite():
    data = request.get_json() or {}
    wp_id = data.get("id")

    if not wp_id:
        return jsonify({"status": "error", "message": "Missing wallpaper ID"}), 400

    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM favorites WHERE id = ?", (wp_id,))
    conn.close()
    return jsonify({"status": "success", "message": "Removed from favorites"})

@app.route("/api/proxy_image")
def proxy_image():
    image_url = request.args.get("url")
    if not image_url:
        return "Missing URL", 400
    try:
        # Pass a standard User-Agent and clear referrers
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(image_url, headers=headers, stream=True, timeout=15.0)
        res.raise_for_status()
        return Response(
            res.iter_content(chunk_size=8192),
            content_type=res.headers.get("Content-Type", "image/jpeg"),
        )
    except Exception as e:
        return str(e), 500

@app.route("/api/set", methods=["POST"])
def api_set():
    data = request.get_json()
    image_url = data.get("url")
    wallpaper_id = data.get("id")

    if not image_url or not wallpaper_id:
        return jsonify({"status": "error", "message": "Invalid payload"}), 400

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(image_url).suffix or ".jpg"
    file_path = DOWNLOAD_DIR / f"{wallpaper_id}{ext}"

    try:
        if not file_path.exists():
            with requests.get(image_url, stream=True, timeout=15.0) as r:
                r.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

        if set_desktop_wallpaper(file_path):
            return jsonify({"status": "success", "message": f"Applied wallpaper {file_path.name}!"})
        return jsonify({"status": "error", "message": "Failed to set wallpaper."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



def create_tray_icon():
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


def start_web_ui(host: str = "127.0.0.1", port: int = 5000, tray: bool = False) -> None:
    """Launches the Flask Web UI and opens the browser."""
    # 1. Suppress HTTP request logs (GET, POST, 200, 404, etc.)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # Or log.disabled = True to mute completely

    # 2. Suppress default Flask startup banner ("* Serving Flask app...")
    cli.show_server_banner = lambda *_: None
    url = f"http://{host}:{port}"

    # Standard terminal execution
    if not tray:
        webbrowser.open(url)
        app.run(host=host, port=port, debug=False)
        return

    # System Tray execution
    def on_open_ui(icon, item):
        webbrowser.open(url)

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open TermPaper UI", on_open_ui, default=True),
        pystray.MenuItem("Quit", on_quit)
    )

    icon = pystray.Icon("TermPaper", create_tray_icon(), "TermPaper Web UI", menu)

    # Run Flask in a background daemon thread
    threading.Thread(
        target=app.run,
        kwargs={"host": host, "port": port, "debug": False, "use_reloader": False},
        daemon=True
    ).start()

    webbrowser.open(url)
    icon.run()  # Holds the main thread for system tray events