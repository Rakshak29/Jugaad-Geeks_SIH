"""
Script to create a single 'Project Overview' page in Confluence Cloud REST API v2
as a child of Home page (393394) in space ACMEPAY (393219).
"""

import os
import json
import base64
import ssl
import urllib.request

def main():
    env_path = '.env' if os.path.exists('.env') else '.env.example'
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k.strip()] = v.strip().strip('\"\'')

    url = os.environ.get('JIRA_BASE_URL', '').rstrip('/')
    email = os.environ.get('JIRA_EMAIL', '')
    token = os.environ.get('JIRA_API_TOKEN', '')
    confluence_url = f"{url}/wiki"

    print("=== 1. VERIFYING ENVIRONMENT VARIABLES ===")
    print(f"Base URL: {url}")
    print(f"Email: {email}")
    print(f"API Token Present: {bool(token)}")

    auth_str = base64.b64encode(f'{email}:{token}'.encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_str}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    ctx = ssl._create_unverified_context()

    # 2. Verify target space and parent page
    print("\n=== 2. VERIFYING SPACE AND PARENT PAGE ===")
    req_space = urllib.request.Request(f"{confluence_url}/api/v2/spaces/393219", headers=headers)
    with urllib.request.urlopen(req_space, context=ctx) as resp:
        space_data = json.loads(resp.read().decode())
        print(f"Verified Target Space: '{space_data.get('name')}' (Key: {space_data.get('key')}, ID: {space_data.get('id')})")

    req_parent = urllib.request.Request(f"{confluence_url}/api/v2/pages/393394", headers=headers)
    with urllib.request.urlopen(req_parent, context=ctx) as resp:
        parent_data = json.loads(resp.read().decode())
        print(f"Verified Parent Page: '{parent_data.get('title')}' (ID: {parent_data.get('id')})")

    # 3. Intent Payload
    payload = {
        "spaceId": "393219",
        "status": "current",
        "title": "Project Overview",
        "parentId": "393394",
        "body": {
            "representation": "storage",
            "value": "<h1>Project Overview</h1><p>Documentation for the AcmePay engineering project.</p>"
        }
    }

    print("\n=== 3. INTENDED POST PAYLOAD ===")
    print(json.dumps(payload, indent=2))

    # 4. Perform POST Request
    print("\n=== 4. EXECUTING POST /api/v2/pages ===")
    data_bytes = json.dumps(payload).encode()
    req_post = urllib.request.Request(f"{confluence_url}/api/v2/pages", data=data_bytes, headers=headers, method="POST")
    
    with urllib.request.urlopen(req_post, context=ctx) as resp:
        st = resp.status
        created_page = json.loads(resp.read().decode())
        print(f"POST Status: {st}")

    new_page_id = created_page.get("id")
    print(f"Successfully Created Page ID: {new_page_id}")

    # 5. GET Request Verification
    print("\n=== 5. VERIFYING CREATED PAGE VIA GET ===")
    req_get = urllib.request.Request(f"{confluence_url}/api/v2/pages/{new_page_id}", headers=headers)
    with urllib.request.urlopen(req_get, context=ctx) as resp:
        get_page = json.loads(resp.read().decode())
        print("GET Status: 200")
        print(f"Page ID: {get_page.get('id')}")
        print(f"Title: {get_page.get('title')}")
        print(f"Parent ID: {get_page.get('parentId')}")
        print(f"Status: {get_page.get('status')}")
        webui_link = get_page.get('_links', {}).get('webui')
        if webui_link:
            print(f"Web UI URL: {url}/wiki{webui_link}")

if __name__ == "__main__":
    main()
