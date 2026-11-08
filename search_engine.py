import argparse

from search_engine import SimpleSearchEngine


def build_demo_documents():
    return [
        "Python is a high-level programming language used for web development and automation.",
        "Data scientists use Python libraries like pandas and scikit-learn for analysis.",
        "Search engines index documents and rank results based on relevance and keywords.",
        "A web backend can be built using Python frameworks such as Flask and Django.",
        "Machine learning models are trained using large datasets and optimization algorithms.",
        "Simple search engines often tokenize text and compute keyword similarity scores.",
    ]


def main():
    parser = argparse.ArgumentParser(description="Simple Python search engine demo")
    parser.add_argument("query", nargs="?", default="python search", help="Query to search for")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to show")
    args = parser.parse_args()

    documents = build_demo_documents()
    engine = SimpleSearchEngine(documents)
    results = engine.search(args.query, top_k=args.top_k)

    if not results:
        print(f"No relevant matches for: '{args.query}'")
        return

    print(f"Results for: '{args.query}'\n")
    for position, (index, score) in enumerate(results, start=1):
        print(f"{position}. Score: {score:.3f} - {documents[index]}")


if __name__ == "__main__":
    main()

