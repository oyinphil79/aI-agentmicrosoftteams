"""Create the `policies` index in Azure AI Search and upload data/policies/*.md.

- hybrid: BM25 text + HNSW vectors (text-embedding-3-large)
- integrated vectorizer: Search embeds queries itself using its managed identity
- semantic ranker configuration
- `allowed_groups` for security trimming (filter by the user's Entra groups)
The planted injection doc is uploaded too, so red-team tests also run against the real index.

Run after `azd provision` (azd runs it as a postprovision hook). Requires the developer roles
granted in infra/resources.bicep. No keys used.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ops_copilot.retrieval.search import LocalIndex

EMBED_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-large")
DIMS = 3072


def main() -> None:
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        AzureOpenAIVectorizer,
        AzureOpenAIVectorizerParameters,
        HnswAlgorithmConfiguration,
        SearchableField,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SemanticConfiguration,
        SemanticField,
        SemanticPrioritizedFields,
        SemanticSearch,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )
    from openai import AzureOpenAI

    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    aoai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "policies")
    cred = DefaultAzureCredential()

    index = SearchIndex(
        name=index_name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="source", type=SearchFieldDataType.String),
            SimpleField(name="allowed_groups", type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                        filterable=True),
            SearchField(name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                        searchable=True, vector_search_dimensions=DIMS, vector_search_profile_name="hnsw-aoai"),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="hnsw-aoai", algorithm_configuration_name="hnsw",
                                          vectorizer_name="aoai")],
            vectorizers=[AzureOpenAIVectorizer(vectorizer_name="aoai", parameters=AzureOpenAIVectorizerParameters(
                resource_url=aoai_endpoint, deployment_name=EMBED_DEPLOYMENT, model_name=EMBED_DEPLOYMENT))],
        ),
        semantic_search=SemanticSearch(configurations=[SemanticConfiguration(
            name="default",
            prioritized_fields=SemanticPrioritizedFields(title_field=SemanticField(field_name="title"),
                                                         content_fields=[SemanticField(field_name="content")]),
        )]),
    )
    SearchIndexClient(search_endpoint, cred).create_or_update_index(index)
    print(f"index '{index_name}' ready")

    aoai = AzureOpenAI(azure_endpoint=aoai_endpoint, api_version="2024-10-21",
                       azure_ad_token_provider=get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default"))
    docs = LocalIndex(ROOT / "data" / "policies", ROOT / "data" / "injection").docs
    vectors = aoai.embeddings.create(model=EMBED_DEPLOYMENT, input=[d.content for d in docs]).data
    batch = [{"id": d.id, "title": d.title, "content": d.content, "source": d.source,
              "allowed_groups": list(d.allowed_groups), "content_vector": v.embedding} for d, v in zip(docs, vectors, strict=True)]
    SearchClient(search_endpoint, index_name, cred).upload_documents(batch)
    print(f"uploaded {len(batch)} documents")


if __name__ == "__main__":
    main()
