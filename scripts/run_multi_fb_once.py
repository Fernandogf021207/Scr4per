import sys, os, asyncio, json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.services.multi_scrape import multi_scrape_execute

async def main():
    # Use a known-accessible vanity URL by default; can override with FB_TEST_USERNAME
    username = os.environ.get('FB_TEST_USERNAME', 'fernando.garcesflores.asies')
    req = [{
        'platform': 'facebook',
        'username': username,
        'max_photos': 0,
    }]
    print(f"Running multi-scrape for facebook:{username} (followers/followed/friends)")
    try:
        result = await multi_scrape_execute(req)
    except Exception as e:
        print(f"ERROR: {e}")
        raise
    print("\n--- SUMMARY ---")
    print(f"roots: {result.get('root_profiles')}")
    print(f"profiles: {len(result.get('profiles', []))}")
    rels = result.get('relations', [])
    print(f"relations: {len(rels)}")
    # quick breakdown by type
    counts = {}
    for r in rels:
        counts[r.get('type')] = counts.get(r.get('type'), 0) + 1
    print("relations by type:", counts)
    print("meta:", result.get('meta'))
    # Write raw output for inspection
    out_path = os.path.join(os.path.dirname(__file__), '..', 'logs', f"multi_fb_{username}.json")
    out_path = os.path.abspath(out_path)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Saved raw output to {out_path}")

if __name__ == '__main__':
    asyncio.run(main())
