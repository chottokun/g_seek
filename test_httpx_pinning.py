
import httpx
import asyncio
import socket

async def test_dns_pinning():
    hostname = "www.google.com"
    try:
        ip = socket.gethostbyname(hostname)
        print(f"Resolved {hostname} to {ip}")
    except Exception as e:
        print(f"Could not resolve {hostname}: {e}")
        return

    url = f"https://{ip}/"
    headers = {"Host": hostname}

    print("\n1. Testing without sni_hostname extension (should fail SSL):")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=5)
            print(f"Success! Status: {resp.status_code}")
        except Exception as e:
            print(f"Failed: {e}")

    print("\n2. Testing with sni_hostname extension:")
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            req = httpx.Request("GET", url, headers=headers)
            req.extensions["sni_hostname"] = hostname.encode()
            resp = await client.send(req)
            print(f"Success! Status: {resp.status_code}")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_dns_pinning())
