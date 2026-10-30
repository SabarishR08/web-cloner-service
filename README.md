# WebCloner Service

🚀 A web service & API that clones any website along with its static assets (HTML, CSS, JS, images, fonts) into a clean, relative-linked package and serves it as a downloadable **.ZIP** file for offline browsing.

![WebCloner Screenshot](static/screenshot.png) *(Preview via web UI)*

---

## ✨ Features

- **Deep Asset Extraction**: Automatically downloads and rewrites `<a>`, `<img>`, `<link>` (CSS), `<script>` (JS), `<video>`, and `<audio>`.
- **CSS Asset Parsing**: Recursively extracts `url(...)` declarations inside stylesheets (e.g., background images, custom webfonts) and rewrites them to local relative paths.
- **Configurable Crawl Depth**: Single-page mode or multi-page internal crawling.
- **Real-Time Live Logs**: Server-Sent Events (SSE) streaming progress terminal directly to the browser.
- **One-Click Download**: Bundles everything into a clean `.zip` archive on completion.
- **Docker & Cloud Ready**: Ready for deployment on **Render**, **Railway**, **Fly.io**, or any standard VPS.

---

## 🛠️ Tech Stack

- **Backend**: FastAPI & Python 3.11+
- **Parsing & Scraping**: BeautifulSoup4, Requests, urllib
- **Frontend**: Tailwind CSS, HTML5, Vanilla JS (SSE stream)
- **Deployment**: Dockerfile, Render Blueprint (`render.yaml`)

---

## 💻 Local Quickstart

### 1. Clone the repository
```bash
git clone https://github.com/SabarishR08/web-cloner-service.git
cd web-cloner-service
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the server
```bash
python main.py
```
Or with uvicorn directly:
```bash
uvicorn main:app --reload --port 8000
```

Open your browser at `http://localhost:8000`.

---

## 🐳 Docker Deployment

```bash
docker build -t webcloner .
docker run -p 8000:8000 webcloner
```

---

## 🚀 Free Cloud Deployment

### Deploy on Render
1. Push this repository to your GitHub account.
2. Sign in to [Render.com](https://render.com).
3. Click **New +** -> **Web Service** -> Link this repository.
4. Set:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Click **Deploy Web Service**!

### Deploy on Railway
1. Go to [Railway.app](https://railway.app).
2. Choose **Deploy from GitHub repo**.
3. Select this repo — Railway will detect the Dockerfile or Python config automatically!

---

## 📄 License
MIT License
