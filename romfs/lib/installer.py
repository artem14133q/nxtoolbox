"""installer - downloads scripts into /switch/NXToolBox/scripts from GitHub, plain URLs
and script catalogs. Used by the "Get scripts" screen (lib/store.py), usable from scripts.

GitHub URLs:
    https://github.com/OWNER/REPO                        whole repository (default branch)
    https://github.com/OWNER/REPO/tree/BRANCH/FOLDER     a folder (with subfolders)
    https://github.com/OWNER/REPO/blob/BRANCH/FILE.py    a single file
    https://raw.githubusercontent.com/OWNER/REPO/BRANCH/FILE.py
Any other URL is downloaded as a single file.

A catalog is an index.json on any web server (tools/make_catalog.py creates one):
    {"name": "My scripts",
     "packages": [{"name": "snake", "title": "Snake", "version": "1.0",
                   "description": "...", "files": ["snake/main.py", "snake/board.py"],
                   "main": "snake/main.py"}]}
File paths are relative to the folder of index.json and are installed under scripts/.
"""
import os
import json
import requests

NXToolBox = "/switch/NXToolBox"
SCRIPTS = NXToolBox + "/scripts"
CATALOGS_FILE = NXToolBox + "/catalogs.txt"
INSTALLED_FILE = NXToolBox + "/installed.json"
GITHUB_API = "https://api.github.com/repos/%s/%s/contents/%s"
GITHUB_RAW = "https://raw.githubusercontent.com/%s/%s/%s/%s"


def _quiet(text):
    pass


# ---------- files ----------

def safe_path(rel):
    """True if rel is a relative path without '..', so the file stays inside scripts/."""
    if not rel or rel.startswith("/") or "\\" in rel or ":" in rel:
        return False
    for part in rel.split("/"):
        if part in ("", ".", ".."):
            return False
    return True


def makedirs(path):
    current = ""
    for part in path.strip("/").split("/"):
        current += "/" + part
        try:
            os.mkdir(current)
        except OSError:
            pass                        # already exists


def _url_path(path):
    return path.replace(" ", "%20")


def fetch(url, rel, progress=_quiet):
    """Download url into scripts/<rel>; returns rel."""
    if not safe_path(rel):
        raise ValueError("unsafe file name: %s" % rel)
    dest = SCRIPTS + "/" + rel
    makedirs(dest[:dest.rfind("/")])
    progress("Downloading " + rel)
    requests.download(url, dest)
    return rel


# ---------- GitHub and plain URLs ----------

def parse_github(url):
    """(owner, repo, ref, path, is_file) for GitHub URLs, None for other URLs.
    ref is None for the default branch. Branch names with '/' are not supported."""
    u = url.strip()
    for scheme in ("https://", "http://"):
        if u.startswith(scheme):
            u = u[len(scheme):]
    u = u.split("?")[0].split("#")[0].rstrip("/")
    parts = u.split("/")
    host = parts[0]
    if host == "raw.githubusercontent.com" and len(parts) >= 5:
        return parts[1], parts[2], parts[3], "/".join(parts[4:]), True
    if host in ("github.com", "www.github.com") and len(parts) >= 3:
        owner, repo = parts[1], parts[2]
        if repo.endswith(".git"):
            repo = repo[:-4]
        if len(parts) == 3:
            return owner, repo, None, "", False
        if len(parts) >= 5 and parts[3] in ("tree", "blob"):
            return owner, repo, parts[4], "/".join(parts[5:]), parts[3] == "blob"
    return None


def github_files(owner, repo, ref, path, progress=_quiet):
    """[(path_in_repo, download_url)] for all files under path, recursively."""
    url = GITHUB_API % (owner, repo, _url_path(path))
    if ref:
        url += "?ref=" + ref
    progress("Listing " + (path or repo))
    r = requests.get(url, headers={"Accept": "application/vnd.github+json"})
    if r.status_code == 403:
        raise OSError("GitHub API limit reached (60 requests per hour), try again later")
    if r.status_code == 404:
        raise OSError("not found on GitHub: %s/%s %s" % (owner, repo, path))
    r.raise_for_status()
    entries = r.json()
    if isinstance(entries, dict):       # the path is a single file
        entries = [entries]
    files = []
    for e in entries:
        if e.get("type") == "file" and e.get("download_url"):
            files.append((e["path"], e["download_url"]))
        elif e.get("type") == "dir":
            files.extend(github_files(owner, repo, ref, e["path"], progress))
    return files


def install_url(url, progress=_quiet):
    """Install from a GitHub or plain URL. Returns (installed path relative to scripts/,
    number of files). A folder or repository goes into scripts/<its name>/."""
    gh = parse_github(url)
    if gh is None:
        name = url.split("?")[0].rstrip("/").split("/")[-1] or "download.py"
        return fetch(url, name, progress), 1

    owner, repo, ref, path, is_file = gh
    if is_file:
        name = path.split("/")[-1]
        return fetch(GITHUB_RAW % (owner, repo, ref, _url_path(path)), name, progress), 1

    files = github_files(owner, repo, ref, path, progress)
    if not files:
        raise OSError("nothing to download")
    base = path.split("/")[-1] if path else repo
    prefix = path + "/" if path else ""
    for i, (file_path, download_url) in enumerate(files):
        rel = file_path[len(prefix):] if file_path.startswith(prefix) else file_path.split("/")[-1]
        progress("Downloading %d/%d: %s" % (i + 1, len(files), rel))
        fetch(download_url, base + "/" + rel)
    return base + "/", len(files)


# ---------- catalogs ----------

def load_catalogs():
    """[(name, url)] from catalogs.txt: one catalog per line, "Name | URL" or just "URL"."""
    result = []
    try:
        f = open(CATALOGS_FILE)
    except OSError:
        return result
    with f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                name, url = line.split("|", 1)
                result.append((name.strip(), url.strip()))
            else:
                result.append((line, line))
    return result


def save_catalogs(catalogs):
    with open(CATALOGS_FILE, "w") as f:
        f.write("# Script catalogs: \"Name | URL of index.json\" per line\n")
        for name, url in catalogs:
            f.write("%s | %s\n" % (name, url))


def fetch_catalog(url):
    """Download and check a catalog index; returns the parsed dict."""
    r = requests.get(url)
    r.raise_for_status()
    try:
        index = r.json()
    except ValueError:
        raise OSError("not a catalog (index.json expected): " + url)
    if not isinstance(index, dict) or not isinstance(index.get("packages"), list):
        raise OSError("not a catalog (no \"packages\" list): " + url)
    return index


def add_catalog(url):
    """Check the catalog and add it to catalogs.txt; returns its name."""
    index = fetch_catalog(url)
    name = index.get("name") or url
    catalogs = [c for c in load_catalogs() if c[1] != url]
    catalogs.append((name, url))
    save_catalogs(catalogs)
    return name


def remove_catalog(url):
    save_catalogs([c for c in load_catalogs() if c[1] != url])


def installed():
    """{package name: installed version}"""
    try:
        with open(INSTALLED_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _mark_installed(name, version):
    data = installed()
    data[name] = version
    with open(INSTALLED_FILE, "w") as f:
        json.dump(data, f)


def install_package(catalog_url, package, progress=_quiet):
    """Download all files of a catalog package; returns the path of its main script
    (as Python sees it) or None."""
    base = catalog_url[:catalog_url.rfind("/") + 1]
    files = package.get("files") or []
    for rel in files:
        if not safe_path(rel):
            raise ValueError("unsafe file name in the catalog: %s" % rel)
    for i, rel in enumerate(files):
        progress("Downloading %d/%d: %s" % (i + 1, len(files), rel))
        fetch(base + _url_path(rel), rel)
    _mark_installed(package["name"], package.get("version", ""))
    main = package.get("main") or (files[0] if files else None)
    return SCRIPTS + "/" + main if main else None


# ---------- updates of the app's own Python files ----------

SYS = NXToolBox + "/sys"                           # bundled files (launcher.py, lib/)


def _read_line(path):
    try:
        with open(path) as f:
            return f.readline().strip()
    except OSError:
        return ""


def update_url():
    """URL of update.json: /switch/NXToolBox/update_url.txt overrides the bundled one."""
    return _read_line(NXToolBox + "/update_url.txt") or _read_line(SYS + "/update_url.txt")


def installed_version():
    return _read_line(SYS + "/VERSION")


def check_update(timeout=5):
    """The update manifest if a newer version is available, else None.
    Raises OSError if the check itself fails (no network etc.)."""
    url = update_url()
    if not url:
        return None
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    manifest = r.json()
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise OSError("bad update manifest: " + url)
    version = str(manifest.get("version", ""))
    return manifest if version > installed_version() else None


def install_update(manifest, progress=_quiet):
    """Download the files of an update manifest into sys/. VERSION is written last, so an
    interrupted update is simply retried next time."""
    url = update_url()
    base = url[:url.rfind("/") + 1]
    files = manifest["files"]
    for dest in files:
        if not safe_path(dest):
            raise ValueError("unsafe file name in the update: %s" % dest)
    items = sorted(files.items())
    for i, (dest, src) in enumerate(items):
        progress("Updating %d/%d: %s" % (i + 1, len(items), dest))
        path = SYS + "/" + dest
        makedirs(path[:path.rfind("/")])
        requests.download(base + _url_path(src), path)
    with open(SYS + "/VERSION", "w") as f:
        f.write(str(manifest["version"]) + "\n")