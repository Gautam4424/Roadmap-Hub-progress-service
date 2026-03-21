import requests
import uuid

url = "http://localhost:8003/api/v1/progress/toggle"
headers = {
    "X-User-ID": "7fbca773-8cb4-4537-8326-d62f4318c30c",
    "Content-Type": "application/json"
}
payload = {
    "node_id": str(uuid.uuid4()), 
    "roadmap_id": "284c3232-02e8-4f10-8f0c-401186716a4e", 
    "completed": True
}

print(f"Sending request to {url}...")
response = requests.post(url, json=payload, headers=headers)
print(f"Response ({response.status_code}): {response.text}")

get_url = f"http://localhost:8003/api/v1/progress/{payload['roadmap_id']}"
print(f"Fetching progress from {get_url}...")
get_response = requests.get(get_url, headers=headers)
print(f"GET Response ({get_response.status_code}): {get_response.text}")
