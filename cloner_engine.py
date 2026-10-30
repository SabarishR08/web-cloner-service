import os
import re
import shutil
import urllib.parse
import zipfile
import requests
from bs4 import BeautifulSoup

class WebsiteCloner:
    def __init__(self, base_url: str, output_dir: str, max_pages: int = 15, log_callback=None):
        parsed = urllib.parse.urlparse(base_url)
        if not parsed.scheme:
            base_url = "https://" + base_url
            parsed = urllib.parse.urlparse(base_url)
        self.base_url = base_url.rstrip('/')
        self.parsed_base = parsed
        self.output_dir = output_dir
        self.max_pages = max_pages
        self.log_callback = log_callback or (lambda msg: print(msg))

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

        self.visited_pages = set()
        self.downloaded_assets = {}  # clean_url -> local_rel_path
        self.pages_count = 0

    def log(self, message: str):
        try:
            self.log_callback(message)
        except Exception:
            pass

    def sanitize_path(self, path: str) -> str:
        parts = [re.sub(r'[\<\>\:\"\/\\\|\?\*]', '_', p) for p in path.strip('/').split('/')]
        # Filter out empty or dot paths
        clean_parts = [p for p in parts if p and p != '.']
        return os.path.join(*clean_parts) if clean_parts else ''

    def get_local_path_for_url(self, url: str, is_page: bool = False) -> tuple[str, str]:
        """
        Returns (relative_path, absolute_path)
        """
        parsed = urllib.parse.urlparse(url)
        rel_path = parsed.path.lstrip('/')
        
        if not rel_path or rel_path.endswith('/'):
            rel_path = os.path.join(rel_path, 'index.html')
        elif is_page and not os.path.splitext(rel_path)[1]:
            rel_path += '.html'
            
        sanitized = self.sanitize_path(rel_path)
        if not sanitized:
            sanitized = 'index.html'

        abs_path = os.path.join(self.output_dir, sanitized)
        return sanitized, abs_path

    def download_file(self, url: str, is_page: bool = False) -> str | None:
        parsed = urllib.parse.urlparse(url)
        clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

        if clean_url in self.downloaded_assets:
            return self.downloaded_assets[clean_url]

        rel_path, abs_path = self.get_local_path_for_url(clean_url, is_page=is_page)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        try:
            self.log(f"Downloading asset: {clean_url}")
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()

            content_type = resp.headers.get('Content-Type', '')
            if 'text/css' in content_type or rel_path.endswith('.css'):
                css_text = resp.text
                def replace_css_url(match):
                    sub_url = match.group(1).strip("'\"")
                    if sub_url.startswith('data:') or sub_url.startswith('#'):
                        return match.group(0)
                    abs_sub_url = urllib.parse.urljoin(url, sub_url)
                    sub_parsed = urllib.parse.urlparse(abs_sub_url)
                    if sub_parsed.netloc == self.parsed_base.netloc or not sub_parsed.netloc:
                        sub_abs_local = self.download_file(abs_sub_url)
                        if sub_abs_local:
                            rel = os.path.relpath(sub_abs_local, os.path.dirname(abs_path)).replace('\\', '/')
                            return f"url('{rel}')"
                    return match.group(0)

                css_text = re.sub(r'url\((.*?)\)', replace_css_url, css_text)
                with open(abs_path, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(css_text)
            else:
                with open(abs_path, 'wb') as f:
                    f.write(resp.content)

            self.downloaded_assets[clean_url] = abs_path
            return abs_path
        except Exception as e:
            self.log(f"⚠️ Failed asset {url}: {e}")
            return None

    def crawl(self, url: str):
        if self.pages_count >= self.max_pages:
            return

        parsed = urllib.parse.urlparse(url)
        clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

        if clean_url in self.visited_pages:
            return
        self.visited_pages.add(clean_url)
        self.pages_count += 1

        self.log(f"🕷️ Crawling page ({self.pages_count}/{self.max_pages}): {clean_url}")
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            self.log(f"❌ Failed to fetch page {url}: {e}")
            return

        soup = BeautifulSoup(resp.text, 'html.parser')
        _, local_page_path = self.get_local_path_for_url(clean_url, is_page=True)
        page_dir = os.path.dirname(local_page_path)
        os.makedirs(page_dir, exist_ok=True)

        # Asset tags to inspect and rewrite
        tags_and_attrs = [
            ('link', 'href'),
            ('script', 'src'),
            ('img', 'src'),
            ('img', 'srcset'),
            ('source', 'src'),
            ('source', 'srcset'),
            ('video', 'src'),
            ('audio', 'src')
        ]

        for tag_name, attr in tags_and_attrs:
            for tag in soup.find_all(tag_name):
                val = tag.get(attr)
                if not val or val.startswith('data:'):
                    continue

                if attr == 'srcset':
                    items = val.split(',')
                    new_items = []
                    for item in items:
                        parts = item.strip().split()
                        if not parts:
                            continue
                        src_url = parts[0]
                        abs_url = urllib.parse.urljoin(url, src_url)
                        sub_parsed = urllib.parse.urlparse(abs_url)
                        if sub_parsed.netloc == self.parsed_base.netloc or not sub_parsed.netloc:
                            saved_path = self.download_file(abs_url)
                            if saved_path:
                                rel_target = os.path.relpath(saved_path, page_dir).replace('\\', '/')
                                parts[0] = rel_target
                        new_items.append(" ".join(parts))
                    tag[attr] = ", ".join(new_items)
                else:
                    abs_url = urllib.parse.urljoin(url, val)
                    sub_parsed = urllib.parse.urlparse(abs_url)
                    if sub_parsed.netloc == self.parsed_base.netloc or not sub_parsed.netloc:
                        saved_path = self.download_file(abs_url)
                        if saved_path:
                            rel_target = os.path.relpath(saved_path, page_dir).replace('\\', '/')
                            tag[attr] = rel_target

        # Internal navigation links
        internal_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
                continue
            abs_url = urllib.parse.urljoin(url, href)
            target_parsed = urllib.parse.urlparse(abs_url)
            if target_parsed.netloc == self.parsed_base.netloc:
                target_clean = urllib.parse.urlunparse((target_parsed.scheme, target_parsed.netloc, target_parsed.path, '', '', ''))
                _, target_local = self.get_local_path_for_url(target_clean, is_page=True)
                rel_target = os.path.relpath(target_local, page_dir).replace('\\', '/')
                if target_parsed.fragment:
                    rel_target += f"#{target_parsed.fragment}"
                a['href'] = rel_target
                internal_links.append(target_clean)

        # Save HTML
        with open(local_page_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(str(soup))
        self.log(f"💾 Saved page: {os.path.basename(local_page_path)}")

        # Recurse if limit not reached
        for next_url in internal_links:
            if self.pages_count >= self.max_pages:
                break
            self.crawl(next_url)

    def create_zip(self, zip_filepath: str) -> str:
        self.log("📦 Packaging cloned site into ZIP...")
        with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(self.output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.output_dir)
                    zipf.write(file_path, rel_path)
        self.log("✨ ZIP creation complete!")
        return zip_filepath

    def run(self, zip_filepath: str):
        os.makedirs(self.output_dir, exist_ok=True)
        self.crawl(self.base_url)
        return self.create_zip(zip_filepath)
