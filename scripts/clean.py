from pathlib import Path
import shutil
import scandir


CUR_DIR = Path(__file__).parent.resolve()
ROOT_DIR = CUR_DIR.parent.resolve()


def get_html_files() -> list:
    html_files = []
    for root, dirs, files in scandir.walk(str(ROOT_DIR)):
        html_files.extend([f for f in files if f.endswith(".html")])

    return html_files


def get_pycache() -> list:
    caches = []
    for root, dirs, files in scandir.walk(str(ROOT_DIR)):
        caches.extend([cache for cache in dirs if cache.count("pycache")])
    return caches


def main():
    htmls = get_html_files()
    msg = "Not found html files."
    if htmls:
        msg = f"Found {len(htmls)} html files, deleted them."
        [Path(html).unlink() for html in htmls]

    print(msg)
    
    pycaches = get_pycache()
    msg = "Not found cache"
    if pycaches:
        msg = f"Found caches, deleted them."
        [shutil.rmtree(cache) for cache in pycaches]
    
    print(msg)


if __name__ == "__main__":
    main()
