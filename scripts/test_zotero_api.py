import urllib.request
import json
import ssl

def test_zotero_api(url):
    # This is the endpoint identified by the subagent
    api_url = "https://t0guvf0w17.execute-api.us-east-1.amazonaws.com/Prod/web"
    
    # Try the most common Zotero Translation Server payload
    payload = url.encode('utf-8')
    
    headers = {
        "Content-Type": "text/plain",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    
    print(f"Testing URL: {url}")
    try:
        req = urllib.request.Request(api_url, data=payload, headers=headers)
        with urllib.request.urlopen(req, context=ssl._create_unverified_context()) as response:
            data = response.read().decode('utf-8')
            print("Response success!")
            parsed = json.loads(data)
            print(json.dumps(parsed, indent=2)[:500])
    except Exception as e:
        print(f"Error: {e}")

test_zotero_api("https://journals.openedition.org/histoire-education/837")
