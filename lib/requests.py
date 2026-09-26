"""requests - a minimal requests-like HTTP client for NXToolBox scripts (HTTPS via libcurl).

    import requests

    r = requests.get("https://api.github.com/repos/micropython/micropython")
    if r.ok:
        print(r.json()["stargazers_count"])

    requests.post("https://httpbin.org/post", json={"hello": "switch"})
    requests.download("https://example.com/data.bin", "data.bin")   # straight to a file

HTTPS needs /switch/NXToolBox/cacert.pem (see README); verify=False skips the check.
Responses are kept in memory up to max_size (1 MB); use download() for large files.
Transfers can be stopped with + and - (or Ctrl+C on the computer) like any script.
"""
import http
import json as _json


class Response:
    def __init__(self, status, content, url):
        self.status_code = status
        self.content = content
        self.url = url

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    @property
    def text(self):
        return self.content.decode()

    def json(self):
        return _json.loads(self.content)

    def raise_for_status(self):
        if not self.ok:
            raise OSError("HTTP %d for %s" % (self.status_code, self.url))


def request(method, url, data=None, json=None, headers=None, timeout=30, verify=True,
            max_size=1024 * 1024):
    headers = dict(headers) if headers else {}
    if json is not None:
        data = _json.dumps(json)
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
    if isinstance(data, str):
        data = data.encode()
    status, content = http.request(method, url, data=data, headers=headers or None,
                                   timeout=timeout, verify=verify, max_size=max_size)
    return Response(status, content, url)


def get(url, **kwargs):
    return request("GET", url, **kwargs)


def post(url, data=None, json=None, **kwargs):
    return request("POST", url, data=data, json=json, **kwargs)


def put(url, data=None, json=None, **kwargs):
    return request("PUT", url, data=data, json=json, **kwargs)


def delete(url, **kwargs):
    return request("DELETE", url, **kwargs)


def head(url, **kwargs):
    return request("HEAD", url, **kwargs)


def download(url, path, timeout=300, verify=True):
    """Save the response straight into a file (relative paths are relative to the
    script's folder). Raises OSError unless the status is 2xx."""
    if not path.startswith("/"):
        import os
        path = os.getcwd().rstrip("/") + "/" + path
    status = http.download(url, path, timeout=timeout, verify=verify)
    if not 200 <= status < 300:
        raise OSError("HTTP %d for %s" % (status, url))
    return status