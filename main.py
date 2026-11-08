import math
import re
from collections import Counter


class SimpleSearchEngine:
    """A lightweight in-memory search engine using TF-IDF and cosine similarity."""

    def __init__(self, documents):
        self.documents = documents
        self.tokens_by_document = [self._tokenize(doc) for doc in documents]
        self.vocabulary = set().union(*self.tokens_by_document) if self.tokens_by_document else set()
        self.doc_count = len(documents)
        self.doc_frequency = {term: 0 for term in self.vocabulary}

        for terms in self.tokens_by_document:
            unique_terms = set(terms)
            for term in unique_terms:
                self.doc_frequency[term] += 1

        self.idf = {
            term: math.log((1 + self.doc_count) / (1 + self.doc_frequency.get(term, 0))) + 1.0
            for term in self.vocabulary
        }

    @staticmethod
    def _tokenize(text):
        return re.findall(r"[a-z0-9]+", text.lower())

    def _document_vector(self, terms):
        counts = Counter(terms)
        vector = {}
        for term, count in counts.items():
            if term in self.idf:
                vector[term] = count * self.idf[term]
        return vector

    def search(self, query, top_k=5):
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        query_counts = Counter(query_terms)
        query_vector = {}
        for term, count in query_counts.items():
            if term in self.idf:
                query_vector[term] = math.log(1 + count) * self.idf[term]

        if not query_vector:
            return []

        query_norm = math.sqrt(sum(value * value for value in query_vector.values()))
        if query_norm == 0:
            return []

        ranked = []
        for index, doc_terms in enumerate(self.tokens_by_document):
            document_vector = self._document_vector(doc_terms)
            if not document_vector:
                continue

            doc_norm = math.sqrt(sum(value * value for value in document_vector.values()))
            if doc_norm == 0:
                continue

            score = 0.0
            shared_terms = set(document_vector).intersection(query_vector)
            for term in shared_terms:
                score += document_vector[term] * query_vector[term]

            score /= doc_norm * query_norm
            if score > 0:
                ranked.append((index, score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:top_k]


def build_demo_documents():
    return [
        "Python is a high-level programming language used for web development and automation.",
        "Data scientists use Python libraries like pandas and scikit-learn for analysis.",
        "Search engines index documents and rank results based on relevance and keywords.",
        "A web backend can be built using Python frameworks such as Flask and Django.",
        "Machine learning models are trained using large datasets and optimization algorithms.",
        "Simple search engines often tokenize text and compute keyword similarity scores.",
    ]


if __name__ == "__main__":
    documents = build_demo_documents()
    engine = SimpleSearchEngine(documents)
    query = "python search engine"
    results = engine.search(query, top_k=5)

    print(f"Searching for: '{query}'\n")
    for index, score in results:
        print(f"{index + 1}. Score: {score:.3f} - {documents[index]}")
