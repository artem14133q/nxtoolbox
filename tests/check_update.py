import installer

url = installer.update_url()
print("update url:", repr(url))
print("installed version:", repr(installer.installed_version()))

import requests
r = requests.get(url, timeout=10)
print("status:", r.status_code)
print(r.text[:300])

print("result:", installer.check_update())