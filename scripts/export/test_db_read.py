from services.api.db import PostgresConfig, PostgresDocumentStore


def main() -> None:
    store = PostgresDocumentStore(
        PostgresConfig(
            host="127.0.0.1",
            port=15432,
            dbname="ml_radar",
            user="ml_radar",
            password="ml_radar_dev",
        )
    )

    print("Ping:", store.ping())

    docs = store.list_documents(limit=3, offset=0, sort_by="year_desc")
    print("Loaded docs:", len(docs))

    for doc in docs:
        print(doc["canonical_id"], "|", doc["title"], "|", doc["year"])

    total = store.count_documents()
    print("Total docs:", total)

    enriched = store.count_documents(is_open_access=True)
    print("Open access docs:", enriched)


if __name__ == "__main__":
    main()