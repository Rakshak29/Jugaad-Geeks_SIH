from github_connector import fetch_github_raw_data


REPOSITORY_URL = "https://github.com/RishiBakshii/mern-ecommerce"


records = fetch_github_raw_data(REPOSITORY_URL)

print(f"\nFetched {len(records)} raw GitHub records\n")

for record in records[:5]:
    print("=" * 60)
    print("SOURCE ID:", record.source_native_id)
    print("PAYLOAD TYPE:", type(record.payload))
    print("PAYLOAD KEYS:", record.payload.keys())